"""Real table validation and isolated persistence/recovery checks."""
from pathlib import Path
import json
import math
import shutil
from contextlib import contextmanager
import uuid
import unittest
from unittest.mock import patch
import launcher_data as data

from project_paths import game_root
ROOT = game_root()


def rates(blob, kind):
    lines = [x.strip() for x in blob.splitlines() if x.strip() and not x.startswith(b'#')]
    step, index = (2, 0) if kind == 'mob' else (3, 1)
    return [(int(lines[i]) if kind == 'box' else i, int(lines[i + index]), lines[i + step - 1])
            for i in range(0, len(lines), step)]


@contextmanager
def temporary_fixture():
    root = (ROOT / '.ui-review').resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = root / ('redbox-test-' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        if not folder.resolve().is_relative_to(root):
            raise ValueError('Unexpected cleanup path')
        shutil.rmtree(folder)


class RedboxTests(unittest.TestCase):
    def test_fixed_twenty_profile_and_section_mapping(self):
        with temporary_fixture() as server:
            folder = server / 'drop'
            folder.mkdir()
            originals = {p.name: p.read_bytes() for p in (ROOT/'Server/drop/redbox-original').glob('ep*_*.txt')}
            self.assertEqual(len(originals), 240)
            for name, blob in originals.items():
                (folder/name).write_bytes(blob)
            for section_id in (0, 6, 9):
                data.apply_drop_profile(server, 20, section_id)
                for name in originals:
                    ep, kind, difficulty, _ = name[:-4].split('_')
                    source = originals[f'{ep}_{kind}_{difficulty}_{section_id}.txt']
                    source_lines = source.splitlines(keepends=True)
                    source_lines[1] = originals[name].splitlines(keepends=True)[1]
                    expected = data.adjust_rare_table(b''.join(source_lines), kind, 20)
                    self.assertEqual((folder/name).read_bytes(), expected, name)
                self.assertEqual(data.get_drop_section_id(server), section_id)
            data.apply_drop_profile(server, 20, None)
            for name, blob in originals.items():
                kind = name.split('_')[1]
                self.assertEqual((folder/name).read_bytes(), data.adjust_rare_table(blob, kind, 20), name)

    def test_all_real_tables(self):
        files = list((ROOT / 'Server/drop').glob('ep*_*.txt'))
        self.assertEqual(len(files), 240)
        for path in files:
            original = path.read_bytes()
            kind = path.name.split('_')[1]
            self.assertEqual(data.adjust_rare_table(original, kind, 0), original)
            previous = rates(original, kind)
            for level in (1, 15, 30):
                updated = rates(data.adjust_rare_table(original, kind, level), kind)
                for old, new in zip(previous, updated):
                    self.assertEqual(old[::2], new[::2])
                    self.assertGreaterEqual(data.rare_probability(new[1]), data.rare_probability(old[1]))
                    if not old[1] or old[2] == b'000000' or data.rare_probability(old[1]) >= .30:
                        self.assertEqual(old, new)
                    else:
                        self.assertLessEqual(data.rare_probability(new[1]), .30)
                previous = updated
            if kind == 'box':
                def totals(entries):
                    groups = {}
                    for area, code, item in entries:
                        if code and item != b'000000':
                            groups.setdefault(area, []).append(data.rare_probability(code))
                    return {a: 1 - math.prod(1-p for p in ps) for a, ps in groups.items()}
                before, after = totals(rates(original, kind)), totals(previous)
                for area, probability in before.items():
                    self.assertLessEqual(after[area], max(probability, .30) + 1e-12)

    def test_rounding_and_zero(self):
        sample = b'# test\r\n209\r\n000902\r\n0\r\n000903\r\n255\r\n000904\r\n'
        last = 0
        for level in range(31):
            new = data.adjust_rare_table(sample, 'mob', level)
            entries = rates(new, 'mob')
            probability = data.rare_probability(entries[0][1])
            self.assertGreaterEqual(probability, last)
            last = probability
            self.assertEqual(entries[1][1], 0)
            self.assertEqual(entries[2][1], 255)
            self.assertIn(b'\r\n', new)
        self.assertEqual(last, .28125)
        for bad in (-1, 31, True, 1.5):
            with self.assertRaises(ValueError):
                data.adjust_rare_table(sample, 'mob', bad)

    def test_persistence_recovery_and_foreign_edits(self):
        with temporary_fixture() as temp:
            server = Path(temp)
            folder = server / 'drop'
            folder.mkdir()
            original = {p.name: p.read_bytes() for p in (ROOT/'Server/drop').glob('ep*_*.txt')}
            for name, blob in original.items():
                (folder/name).write_bytes(blob)
            data.apply_redbox_level(server, 30)
            expected = {n: (folder/n).read_bytes() for n in original}
            data.apply_redbox_level(server, 30)
            self.assertEqual(expected, {n: (folder/n).read_bytes() for n in original})
            self.assertEqual(data.get_redbox_level(server), 30)
            real_write = data.atomic_write
            count = 0
            def interrupted(path, blob):
                nonlocal count
                if Path(path).suffix == '.txt':
                    count += 1
                    if count == 5:
                        raise OSError('simulated interruption')
                real_write(path, blob)
            with patch.object(data, 'atomic_write', interrupted):
                with self.assertRaises(OSError):
                    data.apply_redbox_level(server, 15)
            data.apply_redbox_level(server, 0)
            self.assertEqual(original, {n: (folder/n).read_bytes() for n in original})
            name = next(iter(original))
            (folder/name).write_bytes(original[name] + b'# external edit\n')
            with self.assertRaises(ValueError):
                data.apply_redbox_level(server, 30)
            self.assertEqual((folder/name).read_bytes(), original[name] + b'# external edit\n')


if __name__ == '__main__':
    unittest.main()
