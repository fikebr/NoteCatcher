"""Export a cloned document and publish files without overwriting user data."""

from datetime import datetime
import os
from pathlib import Path
import tempfile
from urllib.parse import quote
from uuid import uuid4

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage, QPixmap, QTextCursor, QTextDocument

from .config import validate_storage
from .diagnostics import log_failure


def image_fragments(document):
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                yield fragment
            iterator += 1
        block = block.next()


def export_note(document, directory: Path, assets_dir='assets', filename_pattern='%Y-%m-%d_%H%M%S'):
    validate_storage(assets_dir, filename_pattern)
    if document.isEmpty():
        raise ValueError('There is no note to save.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    assets = directory / assets_dir
    assets.mkdir(exist_ok=True)
    if assets.is_symlink() or assets.resolve().parent != directory.resolve():
        raise ValueError('The assets folder must be inside the notes directory.')
    stamp = datetime.now().strftime(filename_pattern)
    clone = document.clone()
    resources = {}
    created = []
    try:
        with tempfile.TemporaryDirectory(
            prefix='.notecatcher-', dir=directory, ignore_cleanup_errors=True
        ) as staging:
            staging = Path(staging)
            for fragment in image_fragments(clone):
                fmt = fragment.charFormat().toImageFormat()
                name = fmt.name()
                if name not in resources:
                    resource = document.resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
                    image = resource.toImage() if isinstance(resource, QPixmap) else resource
                    if not isinstance(image, QImage) or image.isNull():
                        raise ValueError('An inline image could not be resolved.')
                    filename = f'{stamp}_{uuid4().hex}.png'
                    if not image.save(str(staging / filename), 'PNG'):
                        raise OSError('Could not encode an inline image.')
                    resources[name] = filename
                fmt.setName(quote(f'{assets_dir}/{resources[name]}', safe='/'))
                cursor = QTextCursor(clone)
                cursor.setPosition(fragment.position())
                cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
            markdown = clone.toMarkdown()
            staged_note = staging / 'note.md'
            staged_note.write_text(markdown, encoding='utf-8')
            for staged in staging.iterdir():
                with staged.open('rb+') as handle:
                    os.fsync(handle.fileno())
            for filename in resources.values():
                target = assets / filename
                os.link(staging / filename, target)  # Atomic publish, fails if target exists.
                created.append(target)
            suffix = 0
            while True:
                note = directory / f'{stamp}{"_" + str(suffix) if suffix else ""}.md'
                try:
                    os.link(staged_note, note)
                    break
                except FileExistsError:
                    suffix += 1
            return note
    except Exception:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                log_failure('asset_rollback_failed', cleanup_error)
        raise
    finally:
        clone.deleteLater()
