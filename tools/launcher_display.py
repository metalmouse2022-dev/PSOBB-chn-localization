"""4:3 display policy shared by config writing and window placement."""
import ctypes
from ctypes import wintypes

MODES = {
    '无边框全屏 (4:3 黑边，推荐)': 'borderless',
    '普通窗口 (4:3)': 'window',
    '全屏模式 (兼容全屏，4:3 黑边)': 'fullscreen',
}
DEFAULT_MODE = next(iter(MODES))


def mode_code(value):
    code = MODES.get(value, value)
    return code if code in MODES.values() else 'borderless'


def display_profile(mode, requested, desktop):
    mode = mode_code(mode)
    sw, sh = desktop
    if sw < 640 or sh < 480:
        sw, sh = 1280, 960
    if mode == 'window':
        width, height = requested
        # Room for title bar, taskbar and resize frame on small displays.
        units = max(80, min(width // 4, height // 3, (sw - 48) // 4, (sh - 80) // 3))
    else:
        units = min(sw // 4, sh // 3)
    viewport = (units * 4, units * 3)
    units = max(160, min(units, 1920))  # Match the native patch's validation bounds.
    return {'mode': mode, 'render': (units * 4, units * 3), 'viewport': viewport,
            'desktop': (sw, sh), 'native_window_mode': 1}


def update_ini(text, changes):
    """Update keys by section, insert missing keys, preserve other lines/comments."""
    remaining = {section.lower(): dict(values) for section, values in changes.items()}
    names = {section.lower(): section for section in changes}
    lines, section = [], None

    def flush():
        if section in remaining:
            for key, value in remaining[section].items():
                lines.append(f'{key} = {value}\n')
            remaining[section].clear()

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            flush()
            section = stripped[1:-1].lower()
        elif section in remaining and '=' in stripped and not stripped.startswith((';', '#')):
            key = stripped.split('=', 1)[0].strip()
            match = next((name for name in remaining[section] if name.lower() == key.lower()), None)
            if match:
                line = f'{match} = {remaining[section].pop(match)}\n'
        lines.append(line if line.endswith('\n') else line + '\n')
    flush()
    for name, values in remaining.items():
        if values:
            lines.append(f'\n[{names[name]}]\n')
            lines.extend(f'{key} = {value}\n' for key, value in values.items())
    return ''.join(lines)


def update_dgvoodoo(text, profile):
    mode = profile['mode']
    return update_ini(text, {
        'General': {'FullScreenMode': 'false',
                    'ScalingMode': 'stretched_ar', 'KeepWindowAspectRatio': 'true',
                    'CenterAppWindow': 'true'},
        'GeneralExt': {'WindowedAttributes': 'borderless, fullscreensize' if mode != 'window' else '',
                       'FullscreenAttributes': ''},
        # The patched client supplies the actual 4:3 backbuffer size itself.
        'DirectX': {'Resolution': 'unforced'},
    })


def desktop_size():
    # EnumDisplaySettings returns physical pixels even for a DPI-virtualized launcher.
    class DEVMODEW(ctypes.Structure):
        _fields_ = [('dmDeviceName', wintypes.WCHAR * 32),
                    ('dmSpecVersion', wintypes.WORD), ('dmDriverVersion', wintypes.WORD),
                    ('dmSize', wintypes.WORD), ('dmDriverExtra', wintypes.WORD),
                    ('dmFields', wintypes.DWORD), ('display', ctypes.c_byte * 16),
                    ('dmColor', ctypes.c_short), ('dmDuplex', ctypes.c_short),
                    ('dmYResolution', ctypes.c_short), ('dmTTOption', ctypes.c_short),
                    ('dmCollate', ctypes.c_short), ('dmFormName', wintypes.WCHAR * 32),
                    ('dmLogPixels', wintypes.WORD), ('dmBitsPerPel', wintypes.DWORD),
                    ('dmPelsWidth', wintypes.DWORD), ('dmPelsHeight', wintypes.DWORD),
                    ('tail', wintypes.DWORD * 10)]
    value = DEVMODEW()
    value.dmSize = ctypes.sizeof(value)
    if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(value)):
        return int(value.dmPelsWidth), int(value.dmPelsHeight)
    return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


def position_window(hwnd, profile):
    """Only ordinary windows get a frame. dgVoodoo owns fullscreen placement."""
    if profile['mode'] != 'window':
        return
    api = ctypes.windll.user32
    api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
    style = (api.GetWindowLongW(hwnd, -16) & ~0x80000000) | 0x00CF0000
    api.SetWindowLongW(hwnd, -16, style)
    width, height = profile['viewport']
    rect = wintypes.RECT(0, 0, width, height)
    api.AdjustWindowRectEx(ctypes.byref(rect), style, False, api.GetWindowLongW(hwnd, -20))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    sw, sh = profile['desktop']
    api.SetWindowPos(hwnd, None, max(0, (sw - width) // 2), max(0, (sh - height) // 2),
                     width, height, 0x0024)
