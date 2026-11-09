"""Native Windows hotkey registration and Qt message-loop integration."""

import ctypes
from ctypes import wintypes
from itertools import count
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


def parse_capture_shortcut(shortcut):
    """Return Win32 modifiers/VK without loading Windows DLLs."""
    error = ('hotkeys.capture must be Ctrl/Alt/Win plus a letter, digit, F1–F24 '
             '(except reserved F12), or a supported navigation key; e.g. Ctrl+Alt+N.')
    if not isinstance(shortcut, str):
        raise ValueError(error)
    tokens = [token.strip().upper() for token in shortcut.split('+')]
    if len(tokens) < 2 or any(not token for token in tokens):
        raise ValueError(error)
    modifiers = 0
    bits = {'CTRL': 2, 'ALT': 1, 'SHIFT': 4, 'WIN': 8, 'META': 8}
    for token in tokens[:-1]:
        bit = bits.get(token, 0)
        if not bit or modifiers & bit:
            raise ValueError(error)
        modifiers |= bit
    if not modifiers & (1 | 2 | 8):
        raise ValueError(error)
    key = tokens[-1]
    keys = {'SPACE': 0x20, 'TAB': 9, 'RETURN': 13, 'ENTER': 13, 'ESC': 27,
            'ESCAPE': 27, 'INSERT': 0x2D, 'DELETE': 0x2E, 'HOME': 0x24,
            'END': 0x23, 'PAGEUP': 0x21, 'PAGEDOWN': 0x22, 'LEFT': 0x25,
            'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28}
    if len(key) == 1 and key in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        vk = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        if int(key[1:]) == 12:
            raise ValueError('hotkeys.capture cannot use F12, which Windows reserves for debuggers.')
        vk = 0x70 + int(key[1:]) - 1
    elif key in keys:
        vk = keys[key]
    else:
        raise ValueError(error)
    return modifiers, vk


class NativeHotkey(QAbstractNativeEventFilter):
    _ids = count(0x4E00)

    def __init__(self, app, shortcut, callback):
        super().__init__()
        self.app = app
        self.shortcut = shortcut
        self.callback = callback
        self.modifiers, self.vk = parse_capture_shortcut(shortcut)
        self.id = next(self._ids)
        self.registered = False
        self.api = None

    def start(self):
        if self.registered:
            return
        if sys.platform != 'win32':
            raise OSError('Native global shortcuts are supported only on Windows.')
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                           wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        if not self.api.RegisterHotKey(None, self.id, self.modifiers | MOD_NOREPEAT, self.vk):
            code = ctypes.get_last_error()
            raise OSError(code, 'Windows could not register the capture shortcut.')
        self.registered = True
        try:
            self.app.installNativeEventFilter(self)
        except Exception:
            self.close()
            raise

    def nativeEventFilter(self, event_type, message):
        if (self.registered and bytes(event_type) in
                (b'windows_generic_MSG', b'windows_dispatcher_MSG')):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self.id and not msg.hWnd:
                # Run GUI/clipboard work after returning from the native message filter.
                QTimer.singleShot(0, self._activate)
                return True, 0
        return False, 0

    def _activate(self):
        if self.registered:
            self.callback()

    def close(self):
        if self.registered:
            self.app.removeNativeEventFilter(self)
            self.api.UnregisterHotKey(None, self.id)
            self.registered = False
