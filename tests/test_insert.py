from datetime import datetime

from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import QFileDialog, QMessageBox

from notecatcher import main
from notecatcher.main import Window


def test_insert_local_image_exports_independent_asset(qtbot, tmp_path, monkeypatch):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    image = QImage(24, 16, QImage.Format.Format_ARGB32)
    image.fill('blue')
    source = tmp_path / 'source.png'
    image.save(str(source))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source), ''))
    window.editor.setPlainText('BeforeAfter')
    cursor = window.editor.textCursor()
    cursor.setPosition(6)
    window.editor.setTextCursor(cursor)
    window.insert_image()
    # The document owns the bitmap; removing the source must not break export.
    source.unlink()
    window.save()
    markdown = window.last_note.read_text()
    assert markdown.index('Before') < markdown.index('![') < markdown.index('After')
    assets = list((tmp_path / 'notes/assets').glob('*.png'))
    assert len(assets) == 1 and not QImage(str(assets[0])).isNull()


def test_image_cancel_and_bad_file_preserve_draft(qtbot, tmp_path, monkeypatch):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.editor.setPlainText('Preserve me')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: ('', ''))
    window.insert_image()
    bad_file = tmp_path / 'bad.png'
    bad_file.write_text('Not an image')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(bad_file), ''))
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args[1]))
    window.insert_image()
    assert errors and window.editor.toPlainText() == 'Preserve me'


def test_timestamp_inserts_at_selection(qtbot, tmp_path, monkeypatch):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)

    class Clock:
        @staticmethod
        def now():
            return datetime(2026, 11, 9, 14, 30, 5)

    monkeypatch.setattr(main, 'datetime', Clock)
    window.editor.setPlainText('Before [time] After')
    cursor = window.editor.textCursor()
    cursor.setPosition(7)
    cursor.setPosition(13, QTextCursor.MoveMode.KeepAnchor)
    window.editor.setTextCursor(cursor)
    window.insert_timestamp()
    assert window.editor.toPlainText() == 'Before 2026-11-09 14:30:05 After'
