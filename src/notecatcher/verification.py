"""Isolated packaged-build verification; never touches the user's clipboard/state."""

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QMenuBar

from .about import ABOUT_LINK_LABEL, ABOUT_URL, APP_NAME, APP_VERSION, AboutDialog
from .editor import SafeDocument
from .exporter import export_note, image_fragments
from .hotkeys import NativeHotkey, WM_HOTKEY
from .ipc import SingleInstance
from .main import Window
from .recovery import restore_snapshot
from .tray import TrayController


def verify_bundle(report_file):
    path = Path(report_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.parent / f'verification-{uuid4().hex}'
    work.mkdir()
    report = {'name': APP_NAME, 'version': APP_VERSION,
              'homepage': ABOUT_URL, 'frozen': bool(getattr(sys, 'frozen', False))}
    instance = None
    hotkey = None
    try:
        app = QApplication([])

        def wait_for(condition, timeout=3):
            deadline = time.monotonic() + timeout
            while not condition() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
            assert condition(), 'Packaged operation timed out'

        window = Window(work / 'notes', work / 'draft.json')
        assert not window.windowIcon().pixmap(16, 16).isNull()
        window.grab().save(str(work / 'editor.png'))
        report['icon'] = True
        dialog = AboutDialog(window, ABOUT_URL, ABOUT_LINK_LABEL)
        assert dialog.isModal() and isinstance(dialog, QDialog)
        assert dialog.windowTitle() == f'About {APP_NAME}'
        dialog.grab().save(str(work / 'about.png'))
        report['about'] = True
        assert len(window.findChildren(QMenuBar)) == 2

        class Focus:
            def remember(self):
                pass

            def restore(self):
                return True

        tray = TrayController(window, Focus())
        tray.start()
        assert tray.tray.isVisible()
        report['tray'] = True
        mime = QMimeData()
        mime.setHtml('<h1>Packaged note</h1><p><b>Bold</b> <a href="https://example.com">Link</a></p>')
        window.editor.import_mime(mime, append=True)
        for color in ('red', 'blue'):
            image = QImage(32, 24, QImage.Format.Format_ARGB32)
            image.fill(color)
            data = QMimeData()
            data.setImageData(image)
            window.editor.import_mime(data, append=True)
        window.snapshot()
        recovered = SafeDocument()
        restore_snapshot(recovered, work / 'draft.json')
        assert len(list(image_fragments(recovered))) == 2
        report['recovery'] = True

        hotkey_calls = []

        def synthetic_capture():
            hotkey_calls.append(True)
            item = QMimeData()
            item.setText('Native hotkey append')
            window.editor.import_mime(item, append=True)

        hotkey = NativeHotkey(app, 'Ctrl+Alt+Shift+F23', synthetic_capture)
        hotkey.start()
        kernel = ctypes.WinDLL('kernel32')
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        api = ctypes.WinDLL('user32')
        api.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        api.PostThreadMessageW.restype = wintypes.BOOL
        assert api.PostThreadMessageW(kernel.GetCurrentThreadId(), WM_HOTKEY, hotkey.id,
                                      hotkey.modifiers | (hotkey.vk << 16))
        wait_for(lambda: hotkey_calls)
        hotkey.close()
        report['native_hotkey'] = True

        instance = SingleInstance(work / 'state', f'notecatcher-packaged-{uuid4().hex}')
        assert instance.acquire()
        second = SingleInstance(work / 'state', instance.name)
        assert not second.acquire()
        commands = []
        instance.activated.connect(commands.append)
        client = QLocalSocket()
        client.connectToServer(instance.name)
        wait_for(lambda: client.state() == QLocalSocket.LocalSocketState.ConnectedState)
        client.write(b'open\n')
        client.flush()
        wait_for(lambda: commands == ['open'])
        client.abort()
        instance.close()
        report['single_instance_ipc'] = True

        window.save()
        markdown = window.last_note.read_text(encoding='utf-8')
        assert '**Bold**' in markdown and '[Link](https://example.com)' in markdown
        assert 'Native hotkey append' in markdown
        assert len(list((work / 'notes/assets').glob('*.png'))) == 2
        doc = QTextDocument()
        doc.setBaseUrl(QUrl.fromLocalFile(str(work / 'notes') + '/'))
        doc.setMarkdown(markdown)
        assert len(list(image_fragments(doc))) == 2
        report['markdown_images'] = True
        assert window.editor.document().isEmpty() and not window.isVisible()
        window.editor.setPlainText('Discard this packaged draft')
        window.cancel_draft()
        assert window.editor.document().isEmpty()
        report['save_and_cancel'] = True
        blocked = work / 'unavailable'
        blocked.write_text('Existing file')
        recovered.setPlainText('Retain this draft')
        try:
            export_note(recovered, blocked)
        except OSError:
            assert recovered.toPlainText() == 'Retain this draft'
        else:
            raise AssertionError('Unavailable output was not rejected')
        report['failure_preserves_draft'] = True
        tray.tray.hide()
        window.timer.stop()
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        if hotkey is not None:
            hotkey.close()
        if instance is not None:
            instance.close()
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise SystemExit(0 if report['passed'] else 1)
