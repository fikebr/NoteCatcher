"""Resident NoteCatcher startup and rich-text editor window."""

import argparse
from datetime import datetime
from pathlib import Path
import sys
from uuid import uuid4

from platformdirs import user_state_path
from PySide6.QtCore import QMimeData, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QAction, QFont, QImageReader, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QInputDialog, QMainWindow, QMessageBox,
    QTextBrowser, QVBoxLayout, QSystemTrayIcon, QMenuBar,
)

from .editor import Editor, SafeDocument
from .config import Settings, default_config_path, load_settings
from .diagnostics import configure_logging, logger, log_failure, error_detail
from .exporter import export_note
from .recovery import restore_snapshot, save_snapshot
from .icons import app_icon
from .about import ABOUT_LINK_LABEL, ABOUT_URL, APP_VERSION, AboutDialog


class Window(QMainWindow):
    note_saved = Signal(str)

    def __init__(self, notes_dir, recovery_path, settings=None):
        super().__init__()
        self.notes_dir = Path(notes_dir)
        self.settings = settings or Settings()
        self.recovery_path = recovery_path
        self.recovery_blocked = False
        self.last_assets_dir = self.settings.assets_dir
        self.last_note = None
        self.resident = False
        self.setWindowTitle('NoteCatcher')
        self.setWindowIcon(app_icon())
        self.resize(760, 560)
        self.editor = Editor(self)
        self.setCentralWidget(self.editor)
        self.editor.notice.connect(self.statusBar().showMessage)
        file_menu = self.menuBar().addMenu('&File')
        self.add_action(file_menu, 'Save Markdown', self.save, self.settings.save_shortcut)
        self.add_action(file_menu, 'Reload Saved Note', self.preview)
        self.add_action(file_menu, 'Output Folder', self.choose_folder)
        file_menu.addSeparator()
        discard = QAction('Discard draft…', self)
        discard.triggered.connect(self.discard_draft)
        file_menu.addAction(discard)
        cancel = QAction('Clear draft and hide', self)
        cancel.setShortcut(QKeySequence(self.settings.cancel_shortcut))
        cancel.triggered.connect(self.cancel_draft)
        file_menu.addAction(cancel)
        file_menu.addSeparator()
        self.add_action(file_menu, 'Exit', self.exit_app)
        insert_menu = self.menuBar().addMenu('&Insert')
        self.add_action(insert_menu, 'Import Clipboard', self.capture, 'Ctrl+Shift+V')
        self.add_action(insert_menu, 'Link', self.link)
        self.add_action(insert_menu, 'Image', self.insert_image)
        self.add_action(insert_menu, 'Timestamp', self.insert_timestamp)
        help_bar = QMenuBar(self.menuBar())
        help_bar.setNativeMenuBar(False)
        help_menu = help_bar.addMenu('&Help')
        self.add_action(help_menu, 'About', self.show_about)
        self.menuBar().setCornerWidget(help_bar, Qt.Corner.TopRightCorner)
        # Preserve familiar formatting shortcuts without adding menu or toolbar chrome.
        self.add_action(self, 'Bold', self.bold, 'Ctrl+B')
        self.add_action(self, 'Italic', lambda: self.editor.setFontItalic(
            not self.editor.fontItalic()), 'Ctrl+I')
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.settings.recovery_debounce_ms)
        self.timer.timeout.connect(self.snapshot)
        if recovery_path.exists():
            try:
                restore_snapshot(self.editor.document(), recovery_path)
                if not self.editor.document().isEmpty():
                    self.statusBar().showMessage('Recovered your previous draft.')
                    logger.info('draft_restored')
            except Exception as error:
                log_failure('recovery_restore_failed', error)
                backup = recovery_path.with_name(f'draft.corrupt-{uuid4().hex}.json')
                try:
                    recovery_path.rename(backup)
                    message = f'The damaged recovery file was preserved as {backup.name}. You can start a new draft.'
                except OSError as backup_error:
                    log_failure('recovery_backup_failed', backup_error)
                    self.recovery_blocked = True
                    message = ('The damaged recovery file could not be backed up. Autosave is blocked to '
                               'protect it. Back up the file manually, or use Discard draft to reset it.')
                QMessageBox.warning(self, 'Recovery failed', message)
        else:
            self.statusBar().showMessage(f'Notes folder: {self.notes_dir}')
        self.editor.document().contentsChanged.connect(lambda: self.timer.start())

    def add_action(self, container, title, callback, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        container.addAction(action)

    def capture(self):
        self.editor.import_mime(QApplication.clipboard().mimeData(), append=True)
        self.editor.setFocus()

    def show_about(self):
        AboutDialog(self, ABOUT_URL, ABOUT_LINK_LABEL).exec()

    def bold(self):
        self.editor.setFontWeight(QFont.Weight.Normal if self.editor.fontWeight() >=
                                  QFont.Weight.Bold else QFont.Weight.Bold)

    def insert_timestamp(self):
        self.editor.insertPlainText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.editor.setFocus()

    def insert_image(self):
        from .editor import MAX_PIXELS

        filename, _ = QFileDialog.getOpenFileName(
            self, 'Insert image', '', 'Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)')
        if not filename:
            return
        reader = QImageReader(filename)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.width() * size.height() > MAX_PIXELS:
            self.statusBar().showMessage('Image exceeds the 40 megapixel limit.')
            return
        image = reader.read()
        if image.isNull():
            QMessageBox.warning(self, 'Cannot insert image',
                                'The file could not be read as an image. Choose a supported image file.')
            return
        mime = QMimeData()
        mime.setImageData(image)
        self.editor.import_mime(mime)
        self.editor.setFocus()

    def link(self):
        url, accepted = QInputDialog.getText(self, 'Insert link', 'URL (https/http/mailto):')
        if not accepted:
            return
        if QUrl(url).scheme().lower() not in {'http', 'https', 'mailto'}:
            self.statusBar().showMessage('Use an https, http or mailto URL.')
            return
        cursor = self.editor.textCursor()
        fmt = cursor.charFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            cursor.insertText(url, fmt)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose notes folder', str(self.notes_dir))
        if folder:
            self.notes_dir = Path(folder)
            self.statusBar().showMessage(f'Notes folder: {folder} (this session)')

    def save(self):
        if self.editor.document().isEmpty():
            self.statusBar().showMessage('There is no note to save.')
            return
        try:
            self.last_note = export_note(self.editor.document(), self.notes_dir,
                                         self.settings.assets_dir, self.settings.filename_pattern)
            self.last_assets_dir = self.settings.assets_dir
        except Exception as error:
            log_failure('note_save_failed', error)
            QMessageBox.critical(self, 'Could not save; draft retained', error_detail(error))
            return
        logger.info('note_saved')
        # Clear recovery durably before clearing the editor. Never silently leave
        # an old draft on disk that would be resurrected after a successful save.
        try:
            if self.recovery_blocked:
                raise ValueError('Recovery is blocked.')
            save_snapshot(SafeDocument(), self.recovery_path)
        except Exception as error:
            log_failure('saved_draft_clear_failed', error)
            self.timer.stop()
            QMessageBox.warning(self, 'Note saved; recovery needs attention',
                                'The note was saved, but its recovery snapshot could not be cleared. '
                                'The draft remains visible. Fix storage access, then use Discard draft '
                                'to clear it; saving again would create another note.')
            return
        self.timer.stop()
        self.editor.clear()
        self.timer.stop()
        self.statusBar().showMessage(f'Saved {self.last_note.name}')
        self.note_saved.emit(str(self.last_note))

    def snapshot(self):
        try:
            if self.recovery_blocked:
                raise ValueError('Recovery is blocked until the damaged snapshot is backed up or discarded.')
            save_snapshot(self.editor.document(), self.recovery_path)
        except Exception as error:
            log_failure('recovery_snapshot_failed', error)
            self.statusBar().showMessage('Autosave failed; keep NoteCatcher open. ' + error_detail(error))

    def discard_draft(self):
        if self.editor.document().isEmpty() and not self.recovery_blocked:
            return
        answer = QMessageBox.question(self, 'Discard draft?',
                                      'Permanently discard this draft and its recovery snapshot? '
                                      'Saved notes will be kept.',
                                      QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Discard:
            return
        self._clear_draft()

    def cancel_draft(self):
        """Explicit quick-cancel shortcut: no save and no confirmation dialog."""
        if self._clear_draft():
            self.hide()

    def _clear_draft(self):
        try:
            save_snapshot(SafeDocument(), self.recovery_path)
        except Exception as error:
            log_failure('draft_discard_failed', error)
            QMessageBox.critical(self, 'Could not discard; draft retained', error_detail(error))
            return False
        self.timer.stop()
        self.editor.clear()
        self.timer.stop()
        self.recovery_blocked = False
        logger.info('draft_discarded')
        self.statusBar().showMessage('Draft discarded.')
        return True

    def preview(self):
        if not self.last_note:
            self.statusBar().showMessage('Save a note first to preview it.')
            return
        try:
            markdown = self.last_note.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as error:
            log_failure('preview_failed', error)
            QMessageBox.warning(self, 'Preview failed', error_detail(error))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.last_note.name)
        dialog.resize(700, 520)
        browser = QTextBrowser(dialog)
        browser.setOpenLinks(False)
        # Use explicitly loaded local assets; preview cannot fetch arbitrary resources.
        from PySide6.QtGui import QImage, QTextDocument
        doc = SafeDocument(browser)
        browser.setDocument(doc)
        doc.setMarkdown(markdown)
        from .exporter import image_fragments
        for fragment in image_fragments(doc):
            name = fragment.charFormat().toImageFormat().name()
            path = (self.last_note.parent / QUrl.fromPercentEncoding(name.encode())).resolve()
            if path.is_relative_to((self.last_note.parent / self.last_assets_dir).resolve()):
                doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), QImage(str(path)))
        doc.markContentsDirty(0, doc.characterCount())
        QVBoxLayout(dialog).addWidget(browser)
        dialog.exec()

    def persist_draft(self):
        self.timer.stop()
        try:
            if self.recovery_blocked:
                raise ValueError('Recovery snapshot is protected.')
            save_snapshot(self.editor.document(), self.recovery_path)
        except Exception as error:
            log_failure('draft_preserve_failed', error)
            QMessageBox.critical(self, 'Draft could not be preserved', error_detail(error))
            return False
        return True

    def exit_app(self):
        if self.persist_draft():
            QApplication.instance().quit()

    def closeEvent(self, event):
        if not self.persist_draft():
            event.ignore()
        elif self.resident:
            event.ignore()
            self.hide()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser(description='NoteCatcher rich text capture')
    parser.add_argument('--notes-dir', type=Path)
    parser.add_argument('--config', type=Path, help='TOML file (default: local config.toml, then app config)')
    parser.add_argument('--show', action='store_true', help='Show the editor instead of starting in the tray')
    parser.add_argument('--capture', action='store_true', help='Show the editor and append the clipboard')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('NoteCatcher')
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    from .ipc import SingleInstance, send_command
    from .tray import TrayController
    from .hotkeys import NativeHotkey

    state_dir = user_state_path('NoteCatcher')
    try:
        instance = SingleInstance(state_dir)
        if not instance.acquire():
            if not send_command(instance.name, 'capture' if args.capture else 'open'):
                parser.exit(1, 'NoteCatcher is already running but could not be reached. '
                            'Check for an instance in another Windows session.\n')
            return
    except OSError as error:
        parser.exit(1, f'{error}\n')
    config_path = args.config
    if config_path is None:
        config_path = default_config_path()
    try:
        settings = load_settings(config_path, required=args.config is not None)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        instance.close()
        parser.exit(1, f'Cannot read NoteCatcher configuration: {error}\n')
    hotkey = None
    tray = None
    try:
        try:
            configure_logging(state_dir / 'logs', settings.log_level)
        except OSError:
            QMessageBox.warning(None, 'Logging unavailable',
                                'Cannot write diagnostic logs. Check the NoteCatcher state folder permissions.')
        window = Window(args.notes_dir or settings.notes_dir, state_dir / 'draft.json', settings)
        if QSystemTrayIcon.isSystemTrayAvailable():
            app.setQuitOnLastWindowClosed(False)
            tray = TrayController(window)
            instance.activated.connect(tray.activate)
            activate = tray.activate
            tray.start()
            if args.show or args.capture:
                tray.activate('capture' if args.capture else 'open')
        else:
            # Never leave an inaccessible background process if no tray is available.
            def activate(command):
                window.showNormal()
                window.raise_()
                window.activateWindow()
                if command == 'capture':
                    window.capture()
            instance.activated.connect(activate)
            activate('capture' if args.capture else 'open')
            window.statusBar().showMessage('System tray unavailable; running as a normal window.')
        hotkey = NativeHotkey(app, settings.capture_shortcut, lambda: activate('capture'))
        try:
            hotkey.start()
            app.aboutToQuit.connect(hotkey.close)
            logger.info('native_hotkey_registered')
        except OSError as error:
            log_failure('native_hotkey_registration_failed', error)
            if tray is not None:
                tray.tray.setToolTip('NoteCatcher — capture shortcut unavailable')
            window.showNormal()
            message = (f'Could not register {settings.capture_shortcut}. Another application may '
                       'already use it. Exit the old NoteCatcher AutoHotkey script if it is running, '
                       'or change hotkeys.capture in the TOML file and restart NoteCatcher. '
                       'You can still use Insert → Import Clipboard or the tray menu.')
            window.statusBar().showMessage('Global capture shortcut unavailable.')
            QMessageBox.warning(window, 'Capture shortcut unavailable', message)
        result = app.exec()
    finally:
        if hotkey is not None:
            hotkey.close()
        logger.info('application_stopped')
        instance.close()
    sys.exit(result)
