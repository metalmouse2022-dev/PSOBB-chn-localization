"""Read-only Windows controller diagnostics. Never remap or inject input."""
import ctypes
from ctypes import wintypes
from functools import lru_cache
import subprocess
import tkinter as tk
from tkinter import ttk


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [('buttons', wintypes.WORD), ('left_trigger', wintypes.BYTE),
                ('right_trigger', wintypes.BYTE), ('lx', ctypes.c_short),
                ('ly', ctypes.c_short), ('rx', ctypes.c_short), ('ry', ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('packet', wintypes.DWORD), ('pad', XINPUT_GAMEPAD)]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [('mid', wintypes.WORD), ('pid', wintypes.WORD), ('name', wintypes.WCHAR * 32)] + [
        (name, wintypes.UINT) for name in ('xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax',
                                          'buttons', 'period_min', 'period_max', 'rmin', 'rmax',
                                          'umin', 'umax', 'vmin', 'vmax', 'caps', 'max_axes',
                                          'axes', 'max_buttons')
    ] + [('reg_key', wintypes.WCHAR * 32), ('oem_vxd', wintypes.WCHAR * 260)]


class JOYINFOEX(ctypes.Structure):
    _fields_ = [(name, wintypes.DWORD) for name in
                ('size', 'flags', 'x', 'y', 'z', 'r', 'u', 'v', 'buttons',
                 'button_number', 'pov', 'reserved1', 'reserved2')]


@lru_cache(maxsize=1)
def xinput_api():
    for name in ('xinput1_4.dll', 'xinput1_3.dll', 'xinput9_1_0.dll'):
        try:
            api = ctypes.WinDLL(name)
            api.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
            api.XInputGetState.restype = wintypes.DWORD
            return api
        except OSError:
            continue
    return None


def poll_device(device):
    kind, index = device['kind'], device['index']
    if kind == 'xinput':
        api = xinput_api()
        state = XINPUT_STATE()
        if api is None or api.XInputGetState(index, ctypes.byref(state)) != 0:
            raise ConnectionError('设备未连接，请连接后重新检测。')
        pad = state.pad
        return {'buttons': f'0x{pad.buttons:04X}', 'axes': (pad.lx, pad.ly, pad.rx, pad.ry),
                'triggers': (pad.left_trigger, pad.right_trigger)}
    state = JOYINFOEX()
    state.size, state.flags = ctypes.sizeof(state), 0xFF  # JOY_RETURNALL
    result = ctypes.windll.winmm.joyGetPosEx(index, ctypes.byref(state))
    if result != 0:
        raise ConnectionError(f'设备未连接或不可读取（系统代码 {result}），请重新检测。')
    return {'buttons': f'0x{state.buttons:08X}', 'axes': (state.x, state.y, state.z, state.r, state.u, state.v),
            'pov': '居中' if state.pov == 65535 else str(state.pov)}


def scan_devices():
    """XInput plus Windows legacy joystick API; a device may appear in both."""
    devices, errors = [], []
    api = xinput_api()
    if api is None:
        errors.append('系统 XInput 接口不可用')
    for index in range(4):
        device = {'kind': 'xinput', 'index': index, 'name': f'XInput 手柄 {index + 1}'}
        try:
            poll_device(device)
            devices.append(device)
        except ConnectionError:
            pass
    api = ctypes.windll.winmm
    api.joyGetDevCapsW.argtypes = [ctypes.c_size_t, ctypes.POINTER(JOYCAPSW), wintypes.UINT]
    for index in range(min(api.joyGetNumDevs(), 16)):
        caps = JOYCAPSW()
        if api.joyGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
            continue
        device = {'kind': 'winmm', 'index': index,
                  'name': f'Windows 控制器 {index + 1} · {caps.name}'}
        try:
            poll_device(device)
            devices.append(device)
        except ConnectionError:
            pass
    return devices, errors


def keyboard_count():
    class RAWINPUTDEVICELIST(ctypes.Structure):
        _fields_ = [('device', wintypes.HANDLE), ('kind', wintypes.DWORD)]
    api = ctypes.windll.user32
    api.GetRawInputDeviceList.argtypes = [ctypes.POINTER(RAWINPUTDEVICELIST),
                                        ctypes.POINTER(wintypes.UINT), wintypes.UINT]
    api.GetRawInputDeviceList.restype = wintypes.UINT
    count = wintypes.UINT()
    size = ctypes.sizeof(RAWINPUTDEVICELIST)
    if api.GetRawInputDeviceList(None, ctypes.byref(count), size) == 0xFFFFFFFF:
        return None
    if count.value == 0:
        return 0
    values = (RAWINPUTDEVICELIST * count.value)()
    result = api.GetRawInputDeviceList(values, ctypes.byref(count), size)
    if result == 0xFFFFFFFF:
        return None
    return sum(item.kind == 1 for item in values[:result])


def open_system_controller_settings():
    subprocess.Popen(['control.exe', 'joy.cpl'])


class InputDiagnostics:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title('手柄与键盘 · 识别和测试')
        self.window.geometry('760x570')
        self.window.minsize(640, 510)
        self.window.configure(bg='#131f30')
        self.timer = None
        self.devices = []
        buttons = tk.Frame(self.window, bg='#131f30', padx=24, pady=16)
        buttons.pack(side='bottom', fill='x')
        ttk.Button(buttons, text='Windows 手柄设置', command=open_system_controller_settings).pack(side='left')
        ttk.Button(buttons, text='关闭', command=self.close).pack(side='right')
        body = tk.Frame(self.window, bg='#131f30')
        body.pack(fill='both', expand=True)
        canvas = tk.Canvas(body, bg='#131f30', highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        frame = tk.Frame(canvas, bg='#131f30', padx=24, pady=20)
        item = canvas.create_window(0, 0, window=frame, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        frame.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        self.window.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.frame = frame
        self.note('输入设备检测', 18, True)
        self.note('这里只检测和测试设备，不会修改游戏内键位或安装驱动。')
        self.summary = self.note('正在检测…')
        row = tk.Frame(frame, bg='#131f30')
        row.pack(fill='x', pady=(12, 8))
        self.selection = tk.StringVar()
        self.combo = ttk.Combobox(row, textvariable=self.selection, state='readonly')
        self.combo.pack(side='left', fill='x', expand=True)
        self.combo.bind('<<ComboboxSelected>>', lambda _e: self.tick_once())
        ttk.Button(row, text='重新检测', command=self.refresh).pack(side='right', padx=(12, 0))
        self.readout = self.note('选择设备后，按下按钮或转动摇杆。')
        self.readout.configure(font=('Consolas', 12), height=5)
        self.note('键盘测试', 14, True)
        self.key = self.note('点击此窗口后按键；只在本窗口内读取，不记录到日志。')
        self.window.bind('<KeyPress>', self.on_key, add='+')
        self.note('XInput 测试正常 ≠ 游戏已经兼容。此客户端使用 DirectInput；Xbox 类手柄可能仍需兼容方案。'
                  '\nWindows 控制器检测使用 WinMM，不能覆盖所有 DirectInput 设备；同一手柄可能显示两次。'
                  '\n建议在启动游戏前接好手柄，并在游戏内 Options → Pad / Keyboard Config 设置键位。')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.tick()

    def note(self, text, size=11, bold=False):
        label = tk.Label(self.frame, text=text, bg='#131f30', fg='#edf3fa',
                         justify='left', anchor='nw', font=('Microsoft YaHei UI', size, 'bold' if bold else 'normal'))
        label.pack(fill='x', pady=(4, 4))
        label.bind('<Configure>', lambda e: label.configure(wraplength=max(100, e.width)))
        return label

    def on_key(self, event):
        self.key.configure(text=f'已收到：{event.keysym}    键码：{event.keycode}')

    def refresh(self):
        previous = self.selection.get()
        try:
            self.devices, errors = scan_devices()
            keyboards = keyboard_count()
            self.summary.configure(text=f'检测到 {len(self.devices)} 个手柄接口；键盘设备：'
                                   f'{keyboards if keyboards is not None else "未知，可按键测试"}'
                                   + ('；' + '，'.join(errors) if errors else ''))
        except OSError as error:
            self.devices = []
            self.summary.configure(text=f'检测失败：{error}')
        names = [device['name'] for device in self.devices]
        self.combo.configure(values=names)
        self.selection.set(previous if previous in names else (names[0] if names else '未检测到已连接手柄'))
        self.tick_once()

    def tick_once(self):
        index = self.combo.current()
        if index < 0 or index >= len(self.devices):
            self.readout.configure(text='未检测到手柄。请检查连接，并点击“重新检测”。')
            return
        try:
            state = poll_device(self.devices[index])
            lines = [f'按钮位图：{state["buttons"]}', f'摇杆轴：{state["axes"]}']
            if 'triggers' in state:
                lines.append(f'左右扳机（0—255）：{state["triggers"]}')
            else:
                lines.append(f'方向帽：{state["pov"]}')
            self.readout.configure(text='\n'.join(lines))
        except (ConnectionError, OSError) as error:
            self.readout.configure(text=str(error))

    def tick(self):
        self.tick_once()
        self.timer = self.window.after(100, self.tick)

    def close(self):
        if self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None
        self.window.destroy()


def open_diagnostics(parent):
    existing = getattr(parent, '_input_diagnostics', None)
    if existing and existing.window.winfo_exists():
        existing.window.lift()
        return existing
    dialog = InputDiagnostics(parent)
    parent._input_diagnostics = dialog
    return dialog
