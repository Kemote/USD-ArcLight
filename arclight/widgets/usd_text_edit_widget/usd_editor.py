import re
import sys
from style.app_colors import color_palette
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QTextCharFormat, QFont, QSyntaxHighlighter, QTextCursor, QPainter
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit


class USDSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, colors={}):
        super().__init__(parent)
        self.colors = colors
        self.rules = []

        prim_format = QTextCharFormat()
        prim_format.setForeground(self.colors["prim_def"])  # Pink for prim definitions
        prim_format.setFontWeight(QFont.Weight.Bold)

        prop_format = QTextCharFormat()
        prop_format.setForeground(self.colors["properties_attributes"])  # Green for properties/attributes

        type_format = QTextCharFormat()
        type_format.setForeground(self.colors["types"])  # Cyan for types (token, float, etc.)

        string_format = QTextCharFormat()
        string_format.setForeground(self.colors["string_paths"])  # Yellow for strings/paths

        comment_format = QTextCharFormat()
        comment_format.setForeground(self.colors["comment"])  # Muted blue for comments

        # 1. Prims (e.g., def Xform "mesh")
        self.rules.append((re.compile(r'\b(def|over|class)\b\s+\w+\s+"[^"]+"'), prim_format))
        self.rules.append((re.compile(r'\b(def|over|class)\b'), prim_format))
        
        # 2. Data Types
        types = r'\b(token|string|float|int|double|bool|matrix4d|rel|asset)\b'
        self.rules.append((re.compile(types), type_format))

        # 3. Properties / Attributes (e.g., float3 xformOp:translate)
        self.rules.append((re.compile(r'\b[\w:]+(?=\s*=)'), prop_format))

        # 4. Strings & References
        self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
        self.rules.append((re.compile(r'@[^@]*@'), string_format)) # USD Asset Paths

        # 5. Comments
        self.rules.append((re.compile(r'#.*'), comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class USDEditorWidget(QPlainTextEdit):
    def __init__(self, parent=None, color_palette_name="light"):
        super().__init__(parent)
        self.colors = color_palette[color_palette_name]
        self.line_number_area = LineNumberArea(self)

        # UI Initialization
        self.setup_font()
        self.highlighter = USDSyntaxHighlighter(self.document(), colors=self.colors)
        
        # Signals for line numbering
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def setup_font(self):
        font = QFont()
        font.setFamily("Courier New" if sys.platform.startswith("win") else "Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(11)
        self.setFont(font)

    def set_usd_string(self, usd_str: str):
        """Receives the string directly from Usd.Stage.ExportToString() and populates the editor."""
        self.setPlainText(usd_str)

    def line_number_area_width(self):
        digits = 1
        max_blocks = max(1, self.blockCount())
        while max_blocks >= 10:
            max_blocks /= 10
            digits += 1
        space = 15 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = self.colors["hihglighted_line"]
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self.colors["sidebar_bg"]) 

        font_metrics = self.fontMetrics()
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(self.colors["line_num_tex"])
                painter.drawText(0, top, self.line_number_area.width() - 5, font_metrics.height(),
                                 Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
