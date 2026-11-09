"""Atomic recovery snapshots include embedded image bytes."""

import base64
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QImage, QTextDocument

from .exporter import image_fragments


def save_snapshot(document, path: Path):
    images = {}
    for fragment in image_fragments(document):
        name = fragment.charFormat().toImageFormat().name()
        image = document.resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
        if not isinstance(image, QImage) or image.isNull():
            raise ValueError('Unable to preserve an inline image in recovery.')
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise OSError('Unable to encode recovery image.')
        images[name] = base64.b64encode(bytes(buffer.data())).decode('ascii')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.draft-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({'html': document.toHtml(), 'images': images}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_snapshot(document, path: Path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or not isinstance(data.get('html'), str) or
            not isinstance(data.get('images'), dict)):
        raise ValueError('Recovery snapshot has an invalid structure.')
    images = {}
    for name, encoded in data['images'].items():
        if not isinstance(name, str) or not isinstance(encoded, str):
            raise ValueError('Recovery snapshot has invalid image metadata.')
        image = QImage.fromData(base64.b64decode(encoded, validate=True), 'PNG')
        if image.isNull():
            raise ValueError('Recovery image is damaged.')
        images[name] = image
    for name, image in images.items():
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
    document.setHtml(data['html'])
