"""Resident tray lifecycle and explicit activation operations."""

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .focus import FocusController
from .diagnostics import logger


class TrayController(QObject):
    def __init__(self, window, focus=None):
        super().__init__(window)
        self.window = window
        self.focus = focus or FocusController()
        self.tray = QSystemTrayIcon(window)
        self.tray.setIcon(window.windowIcon())
        self.tray.setToolTip(f'NoteCatcher — {window.settings.capture_shortcut}')
        self.menu = QMenu(window)
        self.add_action('Open', lambda: self.activate('open'))
        self.add_action('Capture clipboard', lambda: self.activate('capture'))
        self.save_action = self.add_action('Save note', self.save)
        self.add_action('Preview last saved note', self.preview)
        self.add_action('Discard draft…', self.discard)
        self.menu.addSeparator()
        self.add_action('Exit', self.exit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._clicked)
        self.window.editor.document().contentsChanged.connect(self._update_save)
        self.window.note_saved.connect(self._saved)
        self.window.resident = True
        self._update_save()

    def add_action(self, title, callback):
        action = QAction(title, self.menu)
        action.triggered.connect(callback)
        self.menu.addAction(action)
        return action

    def start(self):
        self.tray.show()

    def activate(self, command):
        self.focus.remember()
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        if command == 'capture':
            self.window.capture()
        self.window.editor.setFocus()

    def _clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.activate('open')

    def _update_save(self):
        self.save_action.setEnabled(not self.window.editor.document().isEmpty())

    def _saved(self, path):
        if self.window.settings.after_save == 'hide':
            self.window.hide()
            if self.window.settings.restore_focus:
                if not self.focus.restore():
                    logger.info('foreground_restore_not_granted')

    def save(self):
        # Ensure failure messages are visible even when Save is used from the tray.
        self.activate('open')
        self.window.save()

    def preview(self):
        self.activate('open')
        self.window.preview()

    def exit(self):
        self.window.exit_app()

    def discard(self):
        self.activate('open')
        self.window.discard_draft()
