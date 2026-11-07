"""Hold a query-only process handle so an exit code survives window teardown."""
import ctypes
from ctypes import wintypes


class ExitProbe:
    def __init__(self, hwnd):
        self.api = ctypes.windll.kernel32
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        pid = wintypes.DWORD()
        user = ctypes.windll.user32
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        self.handle = self.api.OpenProcess(0x1000, False, pid.value) if pid.value else None

    def finish(self):
        if not self.handle:
            return None
        value = wintypes.DWORD()
        try:
            if self.api.GetExitCodeProcess(self.handle, ctypes.byref(value)) and value.value != 259:
                return value.value
            return None
        finally:
            self.api.CloseHandle(self.handle)
            self.handle = None
