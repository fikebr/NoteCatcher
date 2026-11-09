"""Resident integration checks do not modify the real system clipboard."""

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from notecatcher.focus import FocusController
from notecatcher.ipc import SingleInstance
from notecatcher.main import Window
from notecatcher.tray import TrayController


class FakeFocus:
    def __init__(self):
        self.remembered = 0
        self.restored = 0

    def remember(self):
        self.remembered += 1

    def restore(self):
        self.restored += 1


def client_process(name, command):
    return subprocess.Popen(
        [sys.executable, '-c',
         'import sys; from PySide6.QtCore import QCoreApplication; '
         'from notecatcher.ipc import send_command; app = QCoreApplication([]); '
         'sys.exit(0 if send_command(sys.argv[1], sys.argv[2]) else 1)', name, command],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_process_lock_ipc_and_reacquire(qtbot, tmp_path):
    name = f'notecatcher-test-{uuid4().hex}'
    first = SingleInstance(tmp_path, name)
    second = SingleInstance(tmp_path, name)
    received = []
    first.activated.connect(received.append)
    assert first.acquire()
    assert not second.acquire()
    assert first.server.socketOptions() == QLocalServer.SocketOption.UserAccessOption
    try:
        for command in ('open', 'capture', 'capture'):
            client = client_process(name, command)
            try:
                qtbot.waitUntil(lambda: client.poll() is not None, timeout=5000)
                assert client.returncode == 0, client.communicate()
            finally:
                if client.poll() is None:
                    client.kill()
                client.communicate()
        assert received == ['open', 'capture', 'capture']
    finally:
        first.close()
    assert second.acquire()
    second.close()


def test_ipc_rejects_bad_commands_and_large_messages(qtbot, tmp_path):
    instance = SingleInstance(tmp_path, f'notecatcher-test-{uuid4().hex}')
    commands = []
    instance.activated.connect(commands.append)
    assert instance.acquire()
    try:
        for payload in (b'delete\n', b'x' * 100, b'open\ncapture\n'):
            socket = QLocalSocket()
            socket.connectToServer(instance.name)
            assert socket.waitForConnected(1000)
            socket.write(payload)
            socket.flush()
            qtbot.waitUntil(lambda: socket.state() == QLocalSocket.LocalSocketState.UnconnectedState,
                            timeout=3000)
            socket.abort()
        # One connection can activate at most once.
        assert commands == ['open']
    finally:
        instance.close()


def test_short_lived_connections_release_wrappers_without_warnings(qtbot, tmp_path, capfd):
    instance = SingleInstance(tmp_path, f'notecatcher-test-{uuid4().hex}')
    received = []
    instance.activated.connect(received.append)
    assert instance.acquire()
    try:
        for index in range(20):
            # A separate process lets the server's event loop accept the pipe
            # while the client flushes, just as with a command-line activation request.
            code = (
                'import sys; from PySide6.QtCore import QCoreApplication; '
                'from PySide6.QtNetwork import QLocalSocket; app=QCoreApplication([]); '
                's=QLocalSocket(); s.connectToServer(sys.argv[1]); '
                'assert s.waitForConnected(1000); s.write(b"capture\\n"); '
                's.waitForBytesWritten(1000) if s.bytesToWrite() else None; '
                'assert not s.bytesToWrite(); s.abort()'
            )
            client = subprocess.Popen([sys.executable, '-c', code, instance.name],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                qtbot.waitUntil(lambda: client.poll() is not None, timeout=5000)
                assert client.returncode == 0, client.communicate()
            finally:
                if client.poll() is None:
                    client.kill()
                client.communicate()
            qtbot.waitUntil(lambda: len(received) == index + 1, timeout=3000)
            qtbot.waitUntil(lambda: not instance._clients, timeout=3000)
        assert 'No Wrapper found' not in capfd.readouterr().err
    finally:
        instance.close()


def test_capture_append_save_hide_and_close_preserve(qtbot, tmp_path, monkeypatch):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    focus = FakeFocus()
    controller = TrayController(window, focus)
    clipboard = QMimeData()
    clipboard.setText('First item')

    class Clipboard:
        def mimeData(self):
            return clipboard

    monkeypatch.setattr(QApplication, 'clipboard', staticmethod(lambda: Clipboard()))
    controller.activate('capture')
    assert window.isVisible()
    clipboard.setText('Second item')
    controller.activate('capture')
    assert window.editor.toPlainText() == 'First item\nSecond item'
    assert clipboard.text() == 'Second item'
    assert controller.save_action.isEnabled()
    window.save()
    assert not window.isVisible()
    assert focus.restored == 1
    assert not controller.save_action.isEnabled()
    assert 'First item' in window.last_note.read_text()
    controller.activate('open')
    assert window.editor.document().isEmpty()  # Open never imports clipboard.
    window.editor.setPlainText('Keep this hidden draft')
    window.close()
    assert not window.isVisible()
    assert window.editor.toPlainText() == 'Keep this hidden draft'
    reopened = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(reopened)
    assert reopened.editor.toPlainText() == 'Keep this hidden draft'
    window.resident = False


def test_failed_save_and_exit_preserve_visible_draft(qtbot, tmp_path, monkeypatch):
    from notecatcher import main

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    focus = FakeFocus()
    controller = TrayController(window, focus)
    controller.activate('open')
    window.editor.setPlainText('Do not lose this')
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[1]))

    def fail(*args):
        raise OSError('Disk unavailable')

    monkeypatch.setattr(main, 'export_note', fail)
    window.save()
    assert window.isVisible()
    assert window.editor.toPlainText() == 'Do not lose this'
    assert focus.restored == 0
    monkeypatch.setattr(main, 'save_snapshot', fail)
    controller.exit()
    window.close()
    assert window.isVisible()
    assert len(errors) == 3
    monkeypatch.undo()
    window.resident = False


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows foreground API')
def test_focus_keeps_external_target_when_editor_is_active(monkeypatch):
    focus = FocusController()

    class API:
        foreground = 123
        pid = os.getpid() + 1
        restored = None

        def GetForegroundWindow(self):
            return self.foreground

        def GetWindowThreadProcessId(self, handle, process):
            process._obj.value = self.pid

        def IsWindow(self, handle):
            return True

        def SetForegroundWindow(self, handle):
            self.restored = handle
            return True

    focus.api = API()
    focus.remember()
    focus.api.pid = os.getpid()
    focus.api.foreground = 456
    focus.remember()
    assert focus.previous == 123
    assert focus.restore()
    assert focus.api.restored == 123
    assert focus.previous is None
