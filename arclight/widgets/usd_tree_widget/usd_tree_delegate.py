from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtGui import QFont


class UsdTreeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column == 0:
            option.font.setWeight(QFont.bold)
        super().paint(painter, option, index)