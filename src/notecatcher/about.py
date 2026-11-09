"""Application identity and modal About dialog."""

from html import escape
from dataclasses import dataclass
from importlib.metadata import metadata
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .icons import app_icon

@dataclass(frozen=True)
class AppInfo:
    name: str
    version: str
    url: str
    link_label: str


def read_app_info():
    """Read metadata built from pyproject.toml, including in a frozen app."""
    project = metadata('notecatcher')
    homepage = None
    for entry in project.get_all('Project-URL', []):
        label, separator, url = entry.partition(',')
        if separator and label.strip().lower() == 'homepage':
            homepage = url.strip()
            break
    parsed = urlsplit(homepage or '')
    if not project['Name'] or not project['Version'] or parsed.scheme not in ('https', 'http') or not parsed.netloc:
        raise ValueError('NoteCatcher package metadata requires Name, Version and a valid Homepage URL.')
    return AppInfo(project['Name'], project['Version'], homepage,
                   parsed.netloc + parsed.path.rstrip('/'))


APP_INFO = read_app_info()
APP_NAME = APP_INFO.name
APP_VERSION = APP_INFO.version
ABOUT_URL = APP_INFO.url
ABOUT_LINK_LABEL = APP_INFO.link_label


class AboutDialog(QDialog):
    def __init__(self, parent, link_url, link_label):
        super().__init__(parent)
        self.setWindowTitle(f'About {APP_NAME}')
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)
        icon = QLabel(self)
        icon.setPixmap(app_icon().pixmap(64, 64))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        title = QLabel(f'<h2>{escape(APP_NAME)}</h2>', self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        version_label = QLabel(f'Version {APP_VERSION}', self)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        link = QLabel(f'<a href="{escape(link_url, quote=True)}">{escape(link_label)}</a>', self)
        link.setObjectName('aboutLink')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(link)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
