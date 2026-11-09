import logging
from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtWidgets import QMessageBox

from notecatcher.config import load_settings
from notecatcher.diagnostics import configure_logging, logger, log_failure
from notecatcher.editor import SafeDocument
from notecatcher.exporter import export_note
from notecatcher.main import Window
from notecatcher.recovery import restore_snapshot
from notecatcher.tray import TrayController
from test_capture import bitmap
from test_resident import FakeFocus


def test_config_and_custom_export(qtbot, tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('''[storage]
notes_dir = "~/Notes"
assets_dir = "Captured Images"
filename_pattern = "note_%Y%m%d"
[hotkeys]
save = "Ctrl+Shift+S"
[behavior]
after_save = "stay_open"
restore_focus = false
[recovery]
debounce_ms = 250
[logging]
level = "WARNING"
''')
    settings = load_settings(path)
    assert settings.notes_dir == Path.home() / 'Notes'
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json', settings)
    qtbot.addWidget(window)
    focus = FakeFocus()
    tray = TrayController(window, focus)
    tray.activate('open')
    assert window.timer.interval() == 250
    window.editor.import_mime(bitmap('red'))
    window.save()
    assert window.isVisible() and focus.restored == 0
    assert window.last_note.name.startswith('note_')
    assert 'Captured%20Images/' in window.last_note.read_text()
    assert len(list((tmp_path / 'notes/Captured Images').glob('*.png'))) == 1
    window.resident = False


@pytest.mark.parametrize('text, message', [
    ('[storage]\nassets_dir = "../escape"', 'assets_dir'),
    ('[storage]\nassets_dir = "CON"', 'assets_dir'),
    ('[storage]\nfilename_pattern = "%Y/escape"', 'filename_pattern'),
    ('[storage]\nfilename_pattern = "%Q"', 'filename_pattern'),
    ('[storage]\nimage_format = "jpeg"', 'image_format'),
    ('[storage]\nnotes_dir = 10', 'notes_dir'),
    ('[storage]\nnotes_dr = "typo"', 'notes_dr'),
    ('[behavior]\nrestore_focus = "false"', 'restore_focus'),
    ('[behavior]\nafter_save = "exit"', 'after_save'),
    ('[recovery]\ndebounce_ms = true', 'debounce_ms'),
    ('[logging]\nlevel = "TRACE"', 'logging.level'),
    ('[hotkeys]\nsave = "nonsense"', 'hotkeys.save'),
    ('[hotkeys]\ncapture = "Shift+N"', 'hotkeys.capture'),
    ('[unexpected]', 'section'),
    ('[storage', 'valid TOML'),
])
def test_config_errors_are_actionable(tmp_path, text, message):
    path = tmp_path / 'config.toml'
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        load_settings(path)


def test_discard_cancel_confirm_and_failure(qtbot, tmp_path, monkeypatch):
    from notecatcher import main

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.editor.setPlainText('Keep unless confirmed')
    window.snapshot()
    previous = window.recovery_path.read_bytes()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    window.discard_draft()
    assert window.recovery_path.read_bytes() == previous
    assert window.editor.toPlainText() == 'Keep unless confirmed'
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Discard)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[1]))
    real_save = main.save_snapshot

    def fail(*args):
        raise PermissionError('secret note text must not appear in logs')

    monkeypatch.setattr(main, 'save_snapshot', fail)
    window.discard_draft()
    assert errors and window.editor.toPlainText() == 'Keep unless confirmed'
    assert window.recovery_path.read_bytes() == previous
    monkeypatch.setattr(main, 'save_snapshot', real_save)
    window.discard_draft()
    restored = SafeDocument()
    restore_snapshot(restored, window.recovery_path)
    assert restored.isEmpty() and window.editor.document().isEmpty()
    assert not window.editor.document().isUndoAvailable()


def test_damaged_recovery_preserved(qtbot, tmp_path, monkeypatch):
    snapshot = tmp_path / 'draft.json'
    snapshot.write_bytes(b'broken data')
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[1]))
    window = Window(tmp_path / 'notes', snapshot)
    qtbot.addWidget(window)
    assert warnings and not window.recovery_blocked
    assert next(tmp_path.glob('draft.corrupt-*.json')).read_bytes() == b'broken data'
    window.editor.setPlainText('New recoverable draft')
    window.snapshot()
    restored = SafeDocument()
    restore_snapshot(restored, snapshot)
    assert restored.toPlainText() == 'New recoverable draft'


def test_failed_recovery_clear_keeps_saved_draft_visible(qtbot, tmp_path, monkeypatch):
    from notecatcher import main

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    tray = TrayController(window, FakeFocus())
    tray.activate('open')
    window.editor.setPlainText('Already saved')
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[1]))
    real_save = main.save_snapshot

    def fail(*args):
        raise OSError('Disk full')

    monkeypatch.setattr(main, 'save_snapshot', fail)
    window.save()
    assert warnings and window.last_note.read_text().strip() == 'Already saved'
    assert window.isVisible() and window.editor.toPlainText() == 'Already saved'
    monkeypatch.setattr(main, 'save_snapshot', real_save)
    window.resident = False


def test_blocked_corrupt_backup_requires_explicit_discard(qtbot, tmp_path, monkeypatch):
    snapshot = tmp_path / 'draft.json'
    snapshot.write_bytes(b'important damaged snapshot')
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[1]))

    def fail_rename(*args):
        raise PermissionError('File is locked')

    monkeypatch.setattr(Path, 'rename', fail_rename)
    window = Window(tmp_path / 'notes', snapshot)
    qtbot.addWidget(window)
    assert window.recovery_blocked
    window.editor.setPlainText('New work')
    window.snapshot()
    assert snapshot.read_bytes() == b'important damaged snapshot'
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Discard)
    window.discard_draft()
    assert not window.recovery_blocked
    assert window.editor.document().isEmpty()
    restored = SafeDocument()
    restore_snapshot(restored, snapshot)
    assert restored.isEmpty()


def test_recovery_replace_failure_keeps_previous_snapshot(qapp, tmp_path, monkeypatch):
    from notecatcher.recovery import save_snapshot

    path = tmp_path / 'draft.json'
    document = SafeDocument()
    document.setPlainText('Original durable draft')
    save_snapshot(document, path)
    previous = path.read_bytes()
    document.setPlainText('New changes')

    def fail_replace(*args):
        raise PermissionError('Replacement failed')

    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(PermissionError):
        save_snapshot(document, path)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob('.draft-*.tmp'))


def test_disable_focus_restore_still_hides(qtbot, tmp_path):
    from notecatcher.config import Settings

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json', Settings(restore_focus=False))
    qtbot.addWidget(window)
    focus = FakeFocus()
    tray = TrayController(window, focus)
    tray.activate('open')
    window.editor.setPlainText('No focus restore requested')
    window.save()
    assert not window.isVisible() and focus.restored == 0
    window.resident = False


def test_recovery_survives_abrupt_process_exit(qapp, tmp_path):
    path = tmp_path / 'draft.json'
    code = '''import os, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument
from notecatcher.recovery import save_snapshot
app = QApplication([])
doc = QTextDocument()
doc.setPlainText('Persisted before a forced exit')
save_snapshot(doc, Path(sys.argv[1]))
os._exit(0)
'''
    subprocess.run([sys.executable, '-c', code, str(path)], check=True, timeout=10)
    restored = SafeDocument()
    restore_snapshot(restored, path)
    assert restored.toPlainText() == 'Persisted before a forced exit'


def test_limits_preserve_existing_draft(qtbot, tmp_path, monkeypatch):
    from notecatcher import editor
    from PySide6.QtCore import QMimeData

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.editor.setPlainText('Retain me')
    monkeypatch.setattr(editor, 'MAX_TEXT', 5)
    data = QMimeData()
    data.setText('Too much content')
    window.editor.import_mime(data, append=True)
    monkeypatch.setattr(editor, 'MAX_PIXELS', 2)
    window.editor.import_mime(bitmap('blue'), append=True)
    assert window.editor.toPlainText() == 'Retain me'
    unavailable = tmp_path / 'file-not-folder'
    unavailable.write_text('Existing user data')
    with pytest.raises(OSError):
        export_note(window.editor.document(), unavailable)
    assert unavailable.read_text() == 'Existing user data'


def test_logs_rotate_and_exclude_exception_text(tmp_path):
    old_handlers, old_level = logger.handlers[:], logger.level
    logger.handlers = []
    try:
        configure_logging(tmp_path)
        logger.handlers[0].maxBytes = 150
        for _ in range(20):
            log_failure('note_save_failed', ValueError('PRIVATE CLIPBOARD CONTENT'))
        for handler in logger.handlers:
            handler.flush()
        logs = list(tmp_path.glob('notecatcher.log*'))
        assert 1 < len(logs) <= 4
        text = ''.join(path.read_text() for path in logs)
        assert 'PRIVATE CLIPBOARD CONTENT' not in text
        assert 'exception_type=ValueError' in text
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = old_handlers or [logging.NullHandler()]
        logger.setLevel(old_level)


def test_escape_clears_recovery_hides_and_never_exports(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from notecatcher import main

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.editor.setPlainText('Throw away this draft')
    window.snapshot()

    def forbidden(*args):
        pytest.fail('Quick cancel must not confirm or export a note')

    monkeypatch.setattr(QMessageBox, 'question', forbidden)
    monkeypatch.setattr(main, 'export_note', forbidden)
    window.show()
    QApplication.setActiveWindow(window)
    window.editor.setFocus()
    QApplication.processEvents()
    qtbot.keyClick(window.editor, Qt.Key.Key_Escape)
    assert not window.isVisible()
    assert window.editor.document().isEmpty()
    assert not window.editor.document().isUndoAvailable()
    assert not window.timer.isActive()
    restored = SafeDocument()
    restore_snapshot(restored, window.recovery_path)
    assert restored.isEmpty()
    assert not (tmp_path / 'notes').exists()


def test_quick_cancel_retains_draft_when_recovery_clear_fails(qtbot, tmp_path, monkeypatch):
    from notecatcher import main

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.show()
    window.editor.setPlainText('Retain this draft')
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[1]))
    real_save = main.save_snapshot

    def fail(*args):
        raise PermissionError('Locked recovery file')

    monkeypatch.setattr(main, 'save_snapshot', fail)
    window.cancel_draft()
    assert errors and window.isVisible()
    assert window.editor.toPlainText() == 'Retain this draft'
    monkeypatch.setattr(main, 'save_snapshot', real_save)


def test_cancel_config_validation(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('[hotkeys]\ncancel = "Ctrl+Shift+Q"')
    assert load_settings(path).cancel_shortcut == 'Ctrl+Shift+Q'
    for value in ('nonsense', 'Ctrl+Return'):
        path.write_text(f'[hotkeys]\ncancel = "{value}"')
        with pytest.raises(ValueError, match='hotkeys.cancel'):
            load_settings(path)


def test_shared_window_and_tray_icon(qtbot, tmp_path):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    tray = TrayController(window, FakeFocus())
    assert not window.windowIcon().isNull()
    assert tray.tray.icon().cacheKey() == window.windowIcon().cacheKey()
    for size in (16, 32, 256):
        assert not window.windowIcon().pixmap(size, size).isNull()
    window.resident = False
