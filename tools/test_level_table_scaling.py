"""Check native client level-table pointers without touching live data or saves."""
from pathlib import Path
import struct
import unittest
import shutil
import uuid
from unittest.mock import patch

import launcher

DEFAULT = Path(launcher.BASE_DIR) / 'Client/data/PlyLevelTbl.bin.default'


def client_threshold(data, player_class, next_level):
    # Native client's .rel root points to the per-class level table array.
    root = struct.unpack_from('<I', data, len(data) - 16)[0]
    pointers = struct.unpack_from('<I', data, root + 4)[0]
    table = struct.unpack_from('<I', data, pointers + player_class * 4)[0]
    return struct.unpack_from('<I', data, table + next_level * 12 + 8)[0]


class LevelTableTests(unittest.TestCase):
    def setUp(self):
        self.original = DEFAULT.read_bytes()

    def test_four_times_keeps_native_humar_level_two_at_50_exp(self):
        scaled = launcher.ConfigManager.scale_ply_level_tbl(self.original, 4, 4, 4)
        self.assertEqual(client_threshold(scaled, 0, 1), 50)
        self.assertEqual(client_threshold(scaled, 1, 1), 50)

    def test_all_class_pointers_and_rel_footer_are_unchanged(self):
        for multipliers in [(1, 1, 1), (4, 4, 4), (10, 10, 10), (2, 6, 10)]:
            with self.subTest(multipliers=multipliers):
                scaled = launcher.ConfigManager.scale_ply_level_tbl(self.original, *multipliers)
                self.assertEqual(scaled[0x7158:], self.original[0x7158:])
                for player_class in range(12):
                    for level in range(200):
                        self.assertEqual(client_threshold(scaled, player_class, level),
                                         client_threshold(self.original, player_class, level))

    def test_valid_growth_rows_scale_and_placeholders_stay_unchanged(self):
        scaled = launcher.ConfigManager.scale_ply_level_tbl(self.original, 4, 4, 4)
        for player_class in range(12):
            start = 0xD8 + player_class * 2400
            self.assertEqual(scaled[start:start + 12], self.original[start:start + 12])
            for level in range(1, 200):
                offset = start + level * 12
                for field in (0, 1, 3, 4):
                    self.assertEqual(scaled[offset + field], min(255, self.original[offset + field] * 4))
                self.assertEqual(scaled[offset + 8:offset + 12], self.original[offset + 8:offset + 12])

    def test_corrupted_default_table_is_rejected(self):
        broken = bytearray(self.original)
        struct.pack_into('<I', broken, 0x7158, 0xFF)
        with self.assertRaises(ValueError):
            launcher.ConfigManager.scale_ply_level_tbl(bytes(broken), 4, 4, 4)

    def test_one_times_restores_the_exact_original(self):
        self.assertEqual(launcher.ConfigManager.scale_ply_level_tbl(self.original, 1, 1, 1), self.original)

    def test_apply_repairs_all_copies_and_preserves_param_suffix(self):
        work = Path(launcher.BASE_DIR) / '.ui-review' / ('level-test-' + uuid.uuid4().hex)
        client, server = work / 'Client', work / 'Server'
        try:
            (client / 'data').mkdir(parents=True)
            (server / 'param').mkdir(parents=True)
            (client / 'data/PlyLevelTbl.bin.default').write_bytes(self.original)
            suffix = b'preserve server-specific suffix'
            (server / 'param/PlyLevelTbl.bin').write_bytes(self.original + suffix)
            with patch.object(launcher, 'CLIENT_DIR', str(client)), patch.object(launcher, 'SERVER_DIR', str(server)), patch.object(launcher, 'write_log'):
                launcher.ConfigManager.apply_stats_multipliers(4, 4, 4)
            expected = launcher.ConfigManager.scale_ply_level_tbl(self.original, 4, 4, 4)
            for folder in (client / 'data', server):
                self.assertEqual((folder / 'PlyLevelTbl.bin').read_bytes(), expected)
                self.assertEqual(launcher.prs_decompress((folder / 'PlyLevelTbl.prs').read_bytes()), expected)
            self.assertEqual((server / 'param/PlyLevelTbl.bin').read_bytes(), expected + suffix)
            self.assertEqual((client / 'data/PlyLevelTbl.bin.default').read_bytes(), self.original)
        finally:
            assert work.resolve().parent == (Path(launcher.BASE_DIR) / '.ui-review').resolve()
            if work.exists():
                shutil.rmtree(work)


if __name__ == '__main__':
    unittest.main(verbosity=2)
