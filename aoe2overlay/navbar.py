"""Link bar: one clickable widget per entry (whole area incl. color dot is the button),
laid out in a wrapping flow layout. Clicks never fall through to the window drag."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QLabel, QLayout, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Lays out children left to right and wraps to the next line when the width runs out."""

    def __init__(self, parent=None, hspacing: int = 2, vspacing: int = 2):
        super().__init__(parent)
        self._items = []
        self._h, self._v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _do_layout(self, rect: QRect, test: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line_h > 0:
                x, y = rect.x(), y + line_h + self._v
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class NavItem(QLabel):
    clicked = Signal(str)

    def __init__(self, html: str, anchor: str | None, parent=None):
        super().__init__(html, parent)
        self.anchor = anchor
        self.setTextFormat(Qt.RichText)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if anchor:
            self.setObjectName("navlink")
            self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        e.accept()   # never let a click on the bar start a window move

    def mouseReleaseEvent(self, e):
        e.accept()
        if self.anchor and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.anchor)


class NavBar(QWidget):
    jump = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = FlowLayout(self, hspacing=2, vspacing=2)
        self._spec: list[tuple[str, str | None]] = []
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def set_items(self, spec: list[tuple[str, str | None]]) -> None:
        """spec: [(html, anchor or None for plain separators)]. Unchanged spec = no rebuild,
        so a re-render during a click can't swallow it."""
        if spec == self._spec:
            return
        self._spec = spec
        while (it := self._layout.takeAt(0)) is not None:
            if it.widget():
                it.widget().deleteLater()
        for html, anchor in spec:
            item = NavItem(html, anchor, self)
            item.clicked.connect(self.jump)
            self._layout.addWidget(item)
            item.show()
        self.updateGeometry()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout.heightForWidth(w)

    def mousePressEvent(self, e):
        e.accept()   # gaps between items: do nothing instead of moving the window
