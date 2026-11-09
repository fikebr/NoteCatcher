import ctypes
from ctypes import wintypes
import sys

import pytest

from notecatcher.config import load_settings
from notecatcher.hotkeys import WM_HOTKEY, NativeHotkey, parse_capture_shortcut


@pytest.mark.parametrize('text, expected', [
    ('Ctrl+Alt+N', (3, 0x4E)), ('Ctrl+Shift+F23', (6, 0x86)),
    ('Win+Space', (8, 0x20)), ('Alt+9', (1, 0x39)), ('Meta+Home', (8, 0x24)),
])
def test_parse_native_shortcuts(text, expected):
    assert parse_capture_shortcut(text) == expected


@pytest.mark.parametrize('text', [None, 3, '', 'N', 'Shift+N', 'Ctrl+Ctrl+N',
                                       'Ctrl+Alt+F12', 'Ctrl+F25', 'Ctrl+?',
                                       'Ctrl+N, Ctrl+M', 'Ctrl++N'])
def test_reject_unsupported_native_shortcuts(text):
    with pytest.raises(ValueError, match='hotkeys.capture'):
        parse_capture_shortcut(text)


def test_capture_config(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('[hotkeys]\ncapture = "Ctrl+Alt+Shift+J"')
    assert load_settings(path).capture_shortcut == 'Ctrl+Alt+Shift+J'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows message queue integration')
def test_real_registration_native_dispatch_conflict_and_release(qapp, qtbot):
    calls = []
    shortcut = 'Ctrl+Alt+Shift+F23'
    first = NativeHotkey(qapp, shortcut, lambda: calls.append('capture'))
    second = NativeHotkey(qapp, shortcut, lambda: calls.append('duplicate'))
    first.start()
    try:
        assert first.registered
        with pytest.raises(OSError):
            second.start()
        assert not second.registered
        kernel = ctypes.WinDLL('kernel32')
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        api = ctypes.WinDLL('user32', use_last_error=True)
        api.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        api.PostThreadMessageW.restype = wintypes.BOOL
        packed = first.modifiers | (first.vk << 16)
        # Exercise the real Qt native-event filter without injecting keyboard
        # input or reading/modifying the user's system clipboard.
        assert api.PostThreadMessageW(kernel.GetCurrentThreadId(), WM_HOTKEY, first.id, packed)
        qtbot.waitUntil(lambda: calls == ['capture'], timeout=2000)
        first.close()
        first.close()  # aboutToQuit and finally may both close it.
        second.start()  # The registration must be available immediately after exit.
        assert second.registered
    finally:
        first.close()
        second.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows MSG structure')
def test_filter_ignores_unrelated_messages_and_cancelled_callback(qapp):
    calls = []
    hotkey = NativeHotkey(qapp, 'Ctrl+Alt+Shift+F22', lambda: calls.append('capture'))
    hotkey.start()
    try:
        msg = wintypes.MSG()
        msg.message = WM_HOTKEY
        msg.wParam = hotkey.id + 1
        address = ctypes.addressof(msg)
        assert hotkey.nativeEventFilter(b'windows_dispatcher_MSG', address) == (False, 0)
        msg.wParam = hotkey.id
        assert hotkey.nativeEventFilter(b'other_event', address) == (False, 0)
        assert hotkey.nativeEventFilter(b'windows_dispatcher_MSG', address) == (True, 0)
        hotkey.close()
        qapp.processEvents()
        assert not calls
    finally:
        hotkey.close()
