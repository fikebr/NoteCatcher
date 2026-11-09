import re

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QPixmap, QTextDocument

from notecatcher.editor import Editor, SafeDocument
from notecatcher.exporter import export_note, image_fragments
from notecatcher.main import Window
from notecatcher.recovery import restore_snapshot, save_snapshot


def bitmap(color):
    mime = QMimeData()
    image = QImage(24, 16, QImage.Format.Format_ARGB32)
    image.fill(color)
    mime.setImageData(image)
    return mime


def test_formatted_text_two_images_roundtrip(qtbot, tmp_path):
    editor = Editor()
    qtbot.addWidget(editor)
    mime = QMimeData()
    mime.setHtml('<h1>Résumé</h1><p><b>Bold</b> <a href="https://example.com">Link</a></p>')
    mime.setText('fallback')
    editor.import_mime(mime, append=True)
    editor.import_mime(bitmap('red'), append=True)
    editor.import_mime(bitmap('blue'), append=True)
    note = export_note(editor.document(), tmp_path)
    markdown = note.read_text(encoding='utf-8')
    assert '# Résumé' in markdown
    assert '**Bold**' in markdown
    assert '[Link](https://example.com)' in markdown
    assert 'fallback' not in markdown
    links = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', markdown)
    assert len(links) == 2
    for link in links:
        assert not QImage(str(tmp_path / link)).isNull()
    reopened = QTextDocument()
    reopened.setBaseUrl(QUrl.fromLocalFile(str(tmp_path) + '/'))
    reopened.setMarkdown(markdown)
    for fragment in image_fragments(reopened):
        resource = reopened.resource(QTextDocument.ResourceType.ImageResource,
                                     QUrl(fragment.charFormat().toImageFormat().name()))
        assert isinstance(resource, (QImage, QPixmap)) and not resource.isNull()
    assert len(list(image_fragments(editor.document()))) == 2


def test_safe_import_append_and_empty(qtbot):
    editor = Editor()
    qtbot.addWidget(editor)
    editor.setPlainText('Keep me')
    editor.import_mime(QMimeData(), append=True)
    mime = QMimeData()
    mime.setHtml('<p>Next<script>danger</script><img src="file:///secret.png"></p>')
    editor.import_mime(mime, append=True)
    assert editor.toPlainText().startswith('Keep me\nNext')
    assert 'danger' not in editor.toPlainText()
    assert not list(image_fragments(editor.document()))


def test_no_overwrite_and_rollback(qtbot, tmp_path, monkeypatch):
    editor = Editor()
    qtbot.addWidget(editor)
    editor.import_mime(bitmap('green'))
    first = export_note(editor.document(), tmp_path)
    content = first.read_bytes()
    second = export_note(editor.document(), tmp_path)
    assert first != second and first.read_bytes() == content
    import notecatcher.exporter as exporter
    real_link = exporter.os.link
    assets_before = set((tmp_path / 'assets').iterdir())

    def fail_note(source, destination):
        if str(destination).endswith('.md'):
            raise OSError('Simulated disk failure')
        return real_link(source, destination)

    monkeypatch.setattr(exporter.os, 'link', fail_note)
    with pytest.raises(OSError):
        export_note(editor.document(), tmp_path)
    assert set((tmp_path / 'assets').iterdir()) == assets_before
    assert len(list(image_fragments(editor.document()))) == 1


def test_recovery_keeps_image(qtbot, tmp_path):
    editor = Editor()
    qtbot.addWidget(editor)
    editor.setPlainText('Unsaved draft')
    editor.import_mime(bitmap('red'), append=True)
    path = tmp_path / 'draft.json'
    save_snapshot(editor.document(), path)
    restored = SafeDocument()
    restore_snapshot(restored, path)
    note = export_note(restored, tmp_path / 'notes')
    assert 'Unsaved draft' in note.read_text()
    assert len(list((note.parent / 'assets').glob('*.png'))) == 1


def test_window_save_and_restart(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def fail_dialog(*args):
        pytest.fail(str(args[1:]))

    monkeypatch.setattr(QMessageBox, 'critical', fail_dialog)
    monkeypatch.setattr(QMessageBox, 'warning', fail_dialog)
    window = Window(tmp_path / 'notes', tmp_path / 'state/draft.json')
    qtbot.addWidget(window)
    window.editor.setPlainText('A saved note')
    window.save()
    assert window.last_note.exists()
    assert window.editor.document().isEmpty()
    window.editor.setPlainText('A recovered note')
    window.close()
    restarted = Window(tmp_path / 'notes', tmp_path / 'state/draft.json')
    qtbot.addWidget(restarted)
    assert restarted.editor.toPlainText() == 'A recovered note'
