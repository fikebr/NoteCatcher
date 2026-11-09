import pytest
from email.message import Message
from pathlib import Path
import tomllib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMenuBar

from notecatcher.about import APP_VERSION, AboutDialog
from notecatcher.main import Window


def test_about_metadata_matches_pyproject():
    from notecatcher.about import APP_INFO

    with (Path(__file__).parents[1] / 'pyproject.toml').open('rb') as handle:
        project = tomllib.load(handle)['project']
    assert APP_INFO.name == project['name']
    assert APP_INFO.version == project['version']
    assert APP_INFO.url == project['urls']['Homepage']


def test_about_reads_packaged_metadata_without_source_toml(monkeypatch, tmp_path):
    from notecatcher import about

    packaged = Message()
    packaged['Name'] = 'Packaged NoteCatcher'
    packaged['Version'] = '2.3.4'
    packaged['Project-URL'] = 'Homepage, https://example.com/project'
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(about, 'metadata', lambda name: packaged)
    info = about.read_app_info()
    assert info.name == 'Packaged NoteCatcher'
    assert info.version == '2.3.4'
    assert info.url == 'https://example.com/project'
    assert info.link_label == 'example.com/project'


def test_menu_alt_access_keys(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.show()
    with pytest.deprecated_call():
        QApplication.setActiveWindow(window)
    window.editor.setFocus()
    QApplication.processEvents()
    help_bar = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    menus = [(Qt.Key.Key_F, window.menuBar().actions()[0].menu()),
             (Qt.Key.Key_I, window.menuBar().actions()[1].menu()),
             (Qt.Key.Key_H, help_bar.actions()[0].menu())]
    for key, menu in menus:
        qtbot.keyClick(window.editor, key, Qt.KeyboardModifier.AltModifier)
        qtbot.waitUntil(menu.isVisible)
        qtbot.keyClick(menu, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not menu.isVisible())


def test_help_stays_at_right_after_resize(qtbot, tmp_path):
    window = Window(tmp_path / 'notes', tmp_path / 'draft.json')
    qtbot.addWidget(window)
    window.show()
    help_bar = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    assert isinstance(help_bar, QMenuBar)
    for width in (500, 1000):
        window.resize(width, 560)
        window.layout().activate()
        qtbot.waitUntil(lambda: abs(help_bar.geometry().right() -
                                   window.menuBar().width()) < 12)
    help_menu = help_bar.actions()[0].menu()
    assert help_menu.title() == '&Help'
    assert [action.text() for action in help_menu.actions()] == ['About']


def test_about_modal_identity_and_external_link(qtbot):
    dialog = AboutDialog(None, 'https://example.com/?a=1&b=2', 'Project website')
    qtbot.addWidget(dialog)
    assert dialog.isModal()
    assert dialog.windowTitle() == 'About NoteCatcher'
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any('NoteCatcher' in text for text in labels)
    assert f'Version {APP_VERSION}' in labels
    link = dialog.findChild(QLabel, 'aboutLink')
    assert link.openExternalLinks()
    assert 'https://example.com/?a=1&amp;b=2' in link.text()
    assert 'Project website' in link.text()
