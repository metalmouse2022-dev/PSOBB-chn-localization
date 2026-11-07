"""Regression checks against isolated copies; never modify live saves."""
import importlib.util
import pathlib
import shutil
import struct
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('launcher', SOURCE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
ROOT = pathlib.Path(launcher.BASE_DIR)


class Fixes(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / '.ui-review' / ('regression-' + uuid.uuid4().hex)
        self.work.mkdir(parents=True)
        self.server = self.work / 'Server'
        (self.server / 'param').mkdir(parents=True)
        self.backup = self.work / 'Saves_Backup'
        self.patches = [patch.object(launcher, 'SERVER_DIR', str(self.server)),
                        patch.object(launcher, 'SAVES_BACKUP_DIR', str(self.backup)),
                        patch.object(launcher, 'ACCOUNT_DAT_PATH', str(self.server / 'account.dat')),
                        patch.object(launcher, 'write_log', lambda *a, **k: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        assert self.work.resolve().parent == (ROOT / '.ui-review').resolve()
        shutil.rmtree(self.work)

    def test_meseta_scales_enemy_and_box_ranges_without_compounding(self):
        path = self.server / 'param' / 'ItemPT.gsl'
        original = (ROOT / 'Server/param/ItemPT.gsl').read_bytes()
        path.write_bytes(original)
        launcher.ConfigManager.set_meseta_mult(10)
        scaled = path.read_bytes()
        self.assertTrue(original != scaled, 'quantity multiplier silently does nothing')
        expected = bytearray(original)
        for index in range(160):
            sector, size = struct.unpack_from('>II', original, index * 48 + 32)
            self.assertEqual(size, 0x9e0)
            for start, count in [(0x6ac, 200), (0x8a0, 20)]:
                for field in range(count):
                    offset = sector * 0x800 + start + field * 2
                    value = struct.unpack_from('>H', original, offset)[0]
                    struct.pack_into('>H', expected, offset, min(65535, value * 10))
        self.assertEqual(scaled, bytes(expected))
        self.assertEqual(launcher.ConfigManager.get_meseta_mult(), 10)
        launcher.ConfigManager.set_meseta_mult(10)
        self.assertEqual(path.read_bytes(), scaled)
        launcher.ConfigManager.set_meseta_mult(1)
        self.assertEqual(path.read_bytes(), original)

    def test_character_change_creates_backup_when_account_unchanged(self):
        for name, data in [('account.dat', b'a' * 392), ('character.dat', b'first character'), ('bank.dat', b'bank')]:
            (self.server / name).write_bytes(data)
        launcher.ConfigManager.backup_account('prelaunch')
        (self.server / 'character.dat').write_bytes(b'new character progress')
        launcher.ConfigManager.backup_account('exit')
        copies = list(self.backup.glob('character_exit_*.dat'))
        self.assertTrue(copies, 'account-only dedup loses character progress')
        self.assertEqual(copies[-1].read_bytes(), b'new character progress')

    def test_event_ids_match_client_protocol(self):
        self.assertIn('圣诞', launcher.EVENT_MAP[1])
        self.assertIn('情人', launcher.EVENT_MAP[3])
        self.assertIn('万圣', launcher.EVENT_MAP[5])
        self.assertNotIn(2, launcher.EVENT_MAP)  # Reserved ID; no decoration.

    def test_launch_restarts_server_to_reload_saved_settings(self):
        app = object.__new__(launcher.PSOBBLauncherApp)
        app.log = lambda *a, **k: None
        app.root = SimpleNamespace(after=lambda *a: None)
        order = []
        with patch.object(launcher.ServerProcessManager, 'is_server_running', side_effect=[True, False, False]), \
             patch.object(launcher.ServerProcessManager, 'kill_all_servers', side_effect=lambda: order.append('stop')), \
             patch.object(launcher.ServerProcessManager, 'start_all_servers', side_effect=lambda *a, **k: order.append('start') or False):
            app._worker_launch_all(False, False, False, meseta_mult=10)
        self.assertEqual(order, ['stop', 'start'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
