"""One process per user/session, with bounded, user-only local activation IPC."""

import getpass
from pathlib import Path
import time

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .focus import session_id
from .diagnostics import logger

COMMANDS = {'open', 'capture'}


def server_name():
    # Windows usernames exclude pipe separators.
    return f'NoteCatcher-v1-{getpass.getuser()}-{session_id()}'


def send_command(name, command, timeout_ms=2000):
    """Short-lived CLI client. Success means the resident accepted the request."""
    if command not in COMMANDS:
        raise ValueError('Unsupported activation command.')
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(min(150, timeout_ms)):
            socket.write((command + '\n').encode('ascii'))
            if socket.bytesToWrite() and not socket.waitForBytesWritten(timeout_ms):
                socket.abort()
                return False
            if socket.bytesAvailable() or socket.waitForReadyRead(timeout_ms):
                accepted = bytes(socket.readAll()).strip() == b'ok'
                socket.abort()
                return accepted
            socket.abort()
            return False
        socket.abort()
        # A first launch may hold the lock briefly before its pipe is listening.
        time.sleep(0.05)
    return False


class SingleInstance(QObject):
    activated = Signal(str)

    def __init__(self, state_dir: Path, name=None, parent=None):
        super().__init__(parent)
        self.name = name or server_name()
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        # Recovery is shared per user, so also exclude writers in another login session.
        self.lock = QLockFile(str(Path(state_dir) / 'instance.lock'))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(8)
        self.server.newConnection.connect(self._accept)
        self.owned = False
        self._clients = {}

    def acquire(self):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise OSError('Cannot create the NoteCatcher instance lock in the state folder.')
            return False
        self.owned = True
        # On Unix only, remove a stale socket after obtaining exclusive ownership.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            error = self.server.errorString()
            self.close()
            raise OSError(f'Cannot listen for NoteCatcher activation: {error}')
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            timer = QTimer(socket)
            # Keep Python wrappers alive until disconnect. abort() is not a Qt slot;
            # connecting it directly makes PySide try to add a dynamic meta-method
            # during the short-lived named-pipe connection's teardown.
            self._clients[socket] = timer
            timer.setSingleShot(True)
            timer.timeout.connect(lambda s=socket: s.abort())
            timer.start(2000)
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._release(s))
            self._read(socket)
            if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                self._release(socket)

    def _release(self, socket):
        timer = self._clients.pop(socket, None)
        if timer is not None:
            timer.stop()
            socket.deleteLater()

    def _read(self, socket):
        if socket.property('handled'):
            return
        if socket.bytesAvailable() > 64:
            socket.abort()
            return
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine()).strip().decode('ascii', errors='replace')
        socket.setProperty('handled', True)
        if command in COMMANDS:
            logger.debug('activation_received command=%s', command)
            self.activated.emit(command)
            socket.write(b'ok\n')
        else:
            socket.write(b'error\n')
        socket.disconnectFromServer()

    def close(self):
        if self.owned:
            self.server.close()
            for socket in list(self._clients):
                socket.abort()
                self._release(socket)
            self.lock.unlock()
            self.owned = False
