"""Best-effort Windows foreground tracking; handles stay pointer-sized."""

import ctypes
from ctypes import wintypes
import os
import sys


def session_id():
    if sys.platform != 'win32':
        return str(os.getuid())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.ProcessIdToSessionId.restype = wintypes.BOOL
    result = wintypes.DWORD()
    if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    return str(result.value)


class FocusController:
    def __init__(self):
        self.previous = None
        self.api = None
        if sys.platform == 'win32':
            self.api = ctypes.WinDLL('user32', use_last_error=True)
            self.api.GetForegroundWindow.argtypes = []
            self.api.GetForegroundWindow.restype = wintypes.HWND
            self.api.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
            ]
            self.api.GetWindowThreadProcessId.restype = wintypes.DWORD
            self.api.IsWindow.argtypes = [wintypes.HWND]
            self.api.IsWindow.restype = wintypes.BOOL
            self.api.SetForegroundWindow.argtypes = [wintypes.HWND]
            self.api.SetForegroundWindow.restype = wintypes.BOOL

    def remember(self):
        if self.api is None:
            return
        handle = self.api.GetForegroundWindow()
        process = wintypes.DWORD()
        self.api.GetWindowThreadProcessId(handle, ctypes.byref(process))
        if handle and process.value and process.value != os.getpid():
            self.previous = handle

    def restore(self):
        handle, self.previous = self.previous, None
        if self.api is not None and handle and self.api.IsWindow(handle):
            return bool(self.api.SetForegroundWindow(handle))
        return False
