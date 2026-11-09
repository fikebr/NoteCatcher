"""Shared vector icon with raster sizes for Windows window and tray surfaces."""

from pathlib import Path

from PySide6.QtGui import QIcon


def app_icon():
    source = QIcon(str(Path(__file__).parent / 'assets' / 'notecatcher.svg'))
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(source.pixmap(size, size))
    return icon
