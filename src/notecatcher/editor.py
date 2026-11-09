"""Clipboard import with no automatic external resource loading."""

from html import escape
from html.parser import HTMLParser
from uuid import uuid4

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QImage, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

MAX_TEXT = 5_000_000
MAX_PIXELS = 40_000_000


class SafeDocument(QTextDocument):
    def loadResource(self, resource_type, name):
        # All images must be explicitly registered; never load pasted paths/URLs.
        return None


class CleanHTML(HTMLParser):
    allowed = {'p', 'div', 'br', 'b', 'strong', 'i', 'em', 'u', 'h1', 'h2', 'h3',
               'ul', 'ol', 'li', 'a', 'blockquote', 'pre', 'code', 'span'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = 0
        self.omitted = False

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'iframe', 'object'}:
            self.blocked += 1
        if self.blocked:
            return
        if tag == 'img':
            self.parts.append('[Image omitted; paste bitmap separately]')
            self.omitted = True
        elif tag in self.allowed:
            href = dict(attrs).get('href', '')
            attr = ''
            if tag == 'a' and QUrl(href).scheme().lower() in {'http', 'https', 'mailto'}:
                attr = f' href="{escape(href, quote=True)}"'
            self.parts.append(f'<{tag}{attr}>')

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'iframe', 'object'}:
            self.blocked = max(0, self.blocked - 1)
            return
        if not self.blocked and tag in self.allowed:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(escape(data))


class Editor(QTextEdit):
    notice = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocument(SafeDocument(self))
        self.setPlaceholderText('Capture the clipboard or start typing…')

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasHtml() or source.hasText()

    def insertFromMimeData(self, source):
        self.import_mime(source)

    def import_mime(self, source, append=False):
        html = source.html() if source.hasHtml() else ''
        plain = source.text() if source.hasText() else ''
        if len(html) + len(plain) > MAX_TEXT:
            self.notice.emit('Clipboard content exceeds the 5 MB text limit.')
            return
        image = QImage(source.imageData()) if source.hasImage() else QImage()
        if not image.isNull() and image.width() * image.height() > MAX_PIXELS:
            self.notice.emit('Clipboard image exceeds the 40 megapixel limit.')
            return
        cleaner = CleanHTML()
        cleaner.feed(html)
        cleaned = ''.join(cleaner.parts)
        probe = SafeDocument()
        probe.setHtml(cleaned)
        meaningful_html = bool(probe.toPlainText().strip())
        if not (meaningful_html or plain or not image.isNull()):
            self.notice.emit('Clipboard has no supported content.')
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if append:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if not self.document().isEmpty():
                cursor.insertBlock()
        # HTML wins over other representations, except an image-only HTML payload.
        if meaningful_html and (not cleaner.omitted or plain.strip()):
            cursor.insertHtml(cleaned)
        elif not image.isNull():
            name = f'capture:{uuid4().hex}'
            self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
            cursor.insertImage(name)
        elif meaningful_html:
            cursor.insertHtml(cleaned)
        else:
            cursor.insertText(plain)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        if cleaner.omitted:
            self.notice.emit('HTML images omitted; paste bitmap images separately.')
