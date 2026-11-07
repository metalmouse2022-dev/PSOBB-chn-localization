"""Display/input regression checks; no live registry/config/save writes."""
import configparser
import unittest
import ctypes
import shutil
import uuid
from pathlib import Path
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from launcher_display import MODES, display_profile, update_dgvoodoo
import launcher_input
import launcher


@contextmanager
def isolated_directory():
    root = Path(launcher.BASE_DIR) / '.ui-review'
    root.mkdir(parents=True, exist_ok=True)
    work = root / ('display-test-' + uuid.uuid4().hex)
    work.mkdir()
    try:
        yield str(work)
    finally:
        assert work.resolve().parent == root.resolve()
        shutil.rmtree(work)


class DisplayTests(unittest.TestCase):
    def test_borderless_uses_window_rendering_and_preserves_4_3(self):
        profile = display_profile('borderless', (1280, 960), (1920, 1080))
        self.assertEqual(profile['render'], (1440, 1080))
        cfg = configparser.ConfigParser()
        cfg.read_string(update_dgvoodoo('', profile))
        self.assertEqual(cfg['General']['FullScreenMode'], 'false')
        self.assertEqual(cfg['GeneralExt']['WindowedAttributes'], 'borderless, fullscreensize')
        self.assertEqual(cfg['General']['ScalingMode'], 'stretched_ar')

    def test_switch_from_borderless_to_window_clears_borderless(self):
        original = '[GeneralExt]\nWindowedAttributes=borderless, fullscreensize\n[Other]\nkeep=yes\n'
        cfg = configparser.ConfigParser()
        cfg.read_string(update_dgvoodoo(original, display_profile('window', (640, 480), (1920, 1080))))
        self.assertEqual(cfg['GeneralExt']['WindowedAttributes'], '')
        self.assertEqual(cfg['DirectX']['Resolution'], 'unforced')
        self.assertEqual(cfg['Other']['keep'], 'yes')

    def test_fullscreen_never_requires_native_client_fullscreen(self):
        profile = display_profile('fullscreen', (640, 480), (2560, 1440))
        self.assertEqual(profile['native_window_mode'], 1)
        self.assertEqual(profile['render'], (1920, 1440))
        cfg = configparser.ConfigParser()
        cfg.read_string(update_dgvoodoo('', profile))
        self.assertEqual(cfg['General']['FullScreenMode'], 'false')
        self.assertEqual(cfg['GeneralExt']['WindowedAttributes'], 'borderless, fullscreensize')

    def test_invalid_mode_falls_back_to_borderless(self):
        self.assertEqual(display_profile('garbage', (1280, 960), (1920, 1080))['mode'], 'borderless')

    def test_window_is_4_3_and_fits_small_desktop(self):
        profile = display_profile('window', (2560, 1920), (1366, 768))
        width, height = profile['render']
        self.assertEqual(width * 3, height * 4)
        self.assertLessEqual(height + 80, 768)

    def test_comments_and_other_sections_survive(self):
        original = '; keep this note\n[General]\nOutputAPI=bestavailable\n[DirectX]\nAntialiasing=4x\n'
        updated = update_dgvoodoo(original, display_profile('borderless', (1280, 960), (1920, 1080)))
        self.assertIn('; keep this note', updated)
        self.assertIn('OutputAPI=bestavailable', updated)
        self.assertIn('Antialiasing=4x', updated)

    def test_internal_size_matches_native_limits_on_tiny_and_huge_displays(self):
        profile = display_profile('window', (640, 480), (640, 480))
        self.assertEqual(profile['render'], (640, 480))
        self.assertLess(profile['viewport'][1], 480)
        huge = display_profile('borderless', (1280, 960), (12000, 9000))
        self.assertEqual(huge['render'], (7680, 5760))


class InputTests(unittest.TestCase):
    def test_windows_input_structures_match_sdk(self):
        self.assertEqual(ctypes.sizeof(launcher_input.XINPUT_STATE), 16)
        self.assertEqual(ctypes.sizeof(launcher_input.JOYINFOEX), 52)
        self.assertEqual(ctypes.sizeof(launcher_input.JOYCAPSW), 728)

    def test_disconnected_xinput_is_reported_without_crashing(self):
        with patch.object(launcher_input, 'xinput_api', return_value=None):
            with self.assertRaises(ConnectionError):
                launcher_input.poll_device({'kind': 'xinput', 'index': 0})

    def test_xinput_button_axes_and_triggers_are_not_converted_to_keys(self):
        class API:
            def XInputGetState(self, index, value):
                pad = value._obj.pad
                pad.buttons, pad.lx, pad.ry = 0x1000, -32768, 32767
                pad.left_trigger, pad.right_trigger = 128, 255
                return 0
        with patch.object(launcher_input, 'xinput_api', return_value=API()):
            state = launcher_input.poll_device({'kind': 'xinput', 'index': 0})
        self.assertEqual(state['buttons'], '0x1000')
        self.assertEqual(state['axes'], (-32768, 0, 0, 32767))
        self.assertEqual(state['triggers'], (128, 255))


class ConfigTests(unittest.TestCase):
    def test_launch_stops_before_spawning_any_process_when_display_save_fails(self):
        app = object.__new__(launcher.PSOBBLauncherApp)
        app.is_game_running = False
        app.get_ui_config = lambda: ({}, {})
        app.log = unittest.mock.Mock()
        app.save_ui_state = unittest.mock.Mock()
        with patch.object(launcher, 'is_psobb_process_alive', return_value=False), \
             patch.object(launcher.ConfigManager, 'save_server_config'), \
             patch.object(launcher.ConfigManager, 'save_client_settings', side_effect=OSError('write denied')), \
             patch.object(launcher, 'write_log'), \
             patch.object(launcher.messagebox, 'showerror') as error, \
             patch.object(launcher.messagebox, 'askyesno') as ask, \
             patch.object(launcher.threading, 'Thread') as thread:
            app.on_click_launch()
        error.assert_called_once()
        ask.assert_not_called()
        thread.assert_not_called()
        app.save_ui_state.assert_not_called()

    def test_required_registry_failure_is_not_reported_as_saved(self):
        with isolated_directory() as work, ExitStack() as stack:
            stack.enter_context(patch.object(launcher, 'CLIENT_DIR', work))
            stack.enter_context(patch.object(launcher, 'DGVOODOO_CONF_PATH', str(Path(work) / 'dgVoodoo.conf')))
            stack.enter_context(patch.object(launcher.winreg, 'CreateKey', side_effect=OSError('write denied')))
            stack.enter_context(patch.object(launcher.ConfigManager, 'save_widescreen_cfg'))
            stack.enter_context(patch.object(launcher, 'write_log'))
            with self.assertRaises(OSError):
                launcher.ConfigManager.save_client_settings({})

    def test_modes_persist_native_window_and_preserve_existing_ctrlbuf_tail(self):
        tail = b'preserve-existing-options'
        for mode in MODES:
            with self.subTest(mode=mode), isolated_directory() as work, ExitStack() as stack:
                writes = {}
                stack.enter_context(patch.object(launcher, 'CLIENT_DIR', work))
                stack.enter_context(patch.object(launcher, 'DGVOODOO_CONF_PATH', str(Path(work) / 'dgVoodoo.conf')))
                key = unittest.mock.MagicMock()
                stack.enter_context(patch.object(launcher.winreg, 'CreateKey', return_value=key))
                stack.enter_context(patch.object(launcher.winreg, 'CloseKey'))
                stack.enter_context(patch.object(launcher.winreg, 'EnumValue', side_effect=OSError()))
                stack.enter_context(patch.object(launcher.winreg, 'QueryValueEx', return_value=(b'\x00'*4 + tail, launcher.winreg.REG_BINARY)))
                stack.enter_context(patch.object(launcher.winreg, 'SetValueEx', side_effect=lambda key, name, reserved, kind, data: writes.update({name: data})))
                stack.enter_context(patch.object(launcher.ConfigManager, 'save_widescreen_cfg'))
                stack.enter_context(patch.object(launcher, 'desktop_size', return_value=(1920, 1080)))
                stack.enter_context(patch.object(launcher, 'write_log'))
                launcher.ConfigManager.save_client_settings({'screen_mode': mode, 'antialiasing': '4x'})
                self.assertEqual(writes['WINDOW_MODE'], 1)
                self.assertEqual(writes['CTRLBUF'][4:], tail)
                cfg = configparser.ConfigParser()
                cfg.read(Path(work) / 'launcher_display.ini')
                self.assertEqual(cfg.get('Display', 'Mode'), MODES[mode])
                self.assertEqual(cfg.getint('Display', 'Width') * 3, cfg.getint('Display', 'Height') * 4)
                self.assertTrue((Path(work) / 'dgVoodoo.conf').exists())
                graphics = configparser.ConfigParser()
                graphics.read(Path(work) / 'dgVoodoo.conf')
                self.assertEqual(graphics.get('DirectX', 'Antialiasing'), '4x' if MODES[mode] == 'window' else 'off')


if __name__ == '__main__':
    unittest.main(verbosity=2)
