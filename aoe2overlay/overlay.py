"""Overlay window: frameless, always on top, semi-transparent, movable."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QTextBrowser,
                               QVBoxLayout, QWidget)

from .analysis import TeamPlan, plan
from .config import Config
from .counters import CivCounters
from .icons import IconCache
from .maps import MapInfo, find_map
from .navbar import NavBar
from .match import Match, Player

APP_NAME = "AoE2 Counter Overlay"
FONT_MIN, FONT_MAX = 8, 22

C_TEXT = "#ece8e1"
C_DIM = "#9aa0a6"
C_ACCENT = "#f2c063"   # counters
C_DANGER = "#ff8f7f"   # dangers
C_GOOD = "#9fdc9f"     # enemy weaknesses = your chances
C_HEAD = "#8fb8ff"     # enemy civ names
C_OWN = "#b9a7ff"      # own civ
C_MAP = "#7fd6c9"      # map notes


def _e(s: str) -> str:
    return escape(s or "")


def _ul(items: list[str], color: str = C_TEXT) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_e(i)}</li>" for i in items)
    return f'<ul style="margin:0 0 0 -22px; color:{color};">{lis}</ul>'


def _anchor(name: str) -> str:
    return f'<a name="{name}"></a>'


def _short_units(unique_units: list[str]) -> str:
    """'Konnik (Cavalry)' -> 'Konnik'; heroes are left out."""
    return ", ".join(u.split("(")[0].strip() for u in unique_units if "(Hero)" not in u)


class Overlay(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.match: Match | None = None
        self.compact = config.compact
        self.status_text = "Waiting for game start …"

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(260, 120)

        # header
        self.title = QLabel()
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.btn_mode = QPushButton()
        self.btn_hide = QPushButton("×")
        for b in (self.btn_mode, self.btn_hide):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFlat(True)
        self.btn_hide.setToolTip("Hide")
        self.btn_mode.clicked.connect(self.toggle_mode)
        self.btn_hide.clicked.connect(self.hide)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.title, 1)
        head.addWidget(self.btn_mode)
        head.addWidget(self.btn_hide)

        # link bar: Map · enemies | You · allies – click jumps to the section (detail view)
        self.nav = NavBar()
        self.nav.jump.connect(self.jump_to)
        self.nav.hide()

        # content (QTextBrowser for anchors; read-only, no text selection, drag moves the window)
        self.content = QTextBrowser()
        self.content.setOpenLinks(False)
        self.content.setFrameShape(QFrame.NoFrame)
        self.content.setTextInteractionFlags(Qt.NoTextInteraction)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content.setFocusPolicy(Qt.NoFocus)
        self.content.viewport().setAutoFillBackground(False)
        self.content.viewport().installEventFilter(self)
        self.content.viewport().setCursor(Qt.ArrowCursor)
        self.scroll = self.content

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self.grip = QSizeGrip(self)
        grip_row.addWidget(self.grip, 0, Qt.AlignBottom | Qt.AlignRight)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 6, 4)
        lay.setSpacing(4)
        lay.addLayout(head)
        lay.addWidget(self.nav)
        lay.addWidget(self.scroll, 1)
        lay.addLayout(grip_row)

        self._apply_style()

        x, y, w, h = self.cfg.geometry
        self.setGeometry(x, y, w, h)

        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self._save_geometry)

        self.icons = IconCache(self)
        self.icons.ready.connect(self.render)
        self.nav.installEventFilter(self)

        self.locked = False
        if self.cfg.locked:
            self.set_locked(True)
        self.render()

    # ------------------------------------------------------------------ lock / font
    def set_locked(self, locked: bool) -> None:
        """Click-through mode: mouse clicks go to the game. Hotkeys keep working."""
        self.locked = locked
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, locked)
        self.grip.setVisible(not locked)
        if visible:
            self.show()   # changing window flags hides the window
        if self.cfg.locked != locked:
            self.cfg.locked = locked
            self.cfg.save()
        self.render()

    def toggle_lock(self) -> None:
        self.set_locked(not self.locked)

    def change_font(self, step: int) -> None:
        size = max(FONT_MIN, min(FONT_MAX, self.cfg.font_size + step))
        if size == self.cfg.font_size:
            return
        self.cfg.font_size = size
        self._apply_style()
        self.render()
        self._save_timer.start()   # saves config (incl. font size) shortly after

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.ControlModifier:
            self.change_font(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)

    # ------------------------------------------------------------------ rendering
    def _apply_style(self) -> None:
        fs = self.cfg.font_size
        self.setStyleSheet(f"""
            QWidget {{ color: {C_TEXT}; font-family: 'Segoe UI'; font-size: {fs}pt; }}
            QTextBrowser {{ background: transparent; border: none; }}
            QLabel#navlink {{ padding: 1px 5px; border-radius: 4px; }}
            QLabel#navlink:hover {{ background: rgba(255,255,255,40); }}
            QPushButton {{ color: {C_DIM}; border: none; padding: 0 6px; font-size: {fs + 2}pt; }}
            QPushButton:hover {{ color: {C_TEXT}; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: rgba(255,255,255,60); border-radius: 4px; min-height: 20px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        alpha = max(0, min(255, int(self.cfg.opacity * 255)))
        p.fillPath(path, QColor(16, 18, 24, alpha))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawPath(path)

    def set_match(self, match: Match | None, status: str | None = None) -> None:
        self.match = match
        if status:
            self.status_text = status
        self.render()

    def set_status(self, text: str) -> None:
        self.status_text = text
        if not self.match:
            self.render()

    def toggle_mode(self) -> None:
        self.compact = not self.compact
        self.cfg.compact = self.compact
        self.cfg.save()
        self.render()

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def render(self) -> None:
        compact = self.compact
        self.btn_mode.setText("Detail" if compact else "Compact")
        self.btn_mode.setToolTip(f"Switch view ({self.cfg.hotkey_mode})")
        m = self.match
        if not m:
            self.nav.hide()
            self.title.setText(f'<b>AoE2 Counter</b>{self._lock_mark()} '
                               f'<span style="color:{C_DIM}">· {_e(self.status_text)}</span>')
            self.content.setHtml(
                f'<p style="color:{C_DIM}">{_e(self.cfg.hotkey_toggle)}: show/hide · '
                f'{_e(self.cfg.hotkey_mode)}: compact/detail · {_e(self.cfg.hotkey_lock)}: lock (click-through)'
                f'<br>Ctrl+mouse wheel: font size'
                f'<br>The overlay is only visible when AoE2 runs in '
                f'"Full Screen (Windowed)" / borderless mode.</p>')
            return

        opps = m.opponents
        allies = m.allies
        me = m.me
        own_civ = me.civ if me else None
        tp = plan(opps, own_civ)
        counters = {id(p): cc for p, cc in tp.per_enemy}
        mp = find_map(m.map_name, m.map_enum)

        self.title.setText(f'<b>{_e(m.title)}</b>{self._lock_mark()} <span style="color:{C_DIM}">· '
                           f'{len(opps)} {"enemy" if len(opps) == 1 else "enemies"}</span>')
        self._render_nav(m, mp)

        parts = [_anchor("map") + self._map_section(mp, compact)]
        for i, p in enumerate(opps):
            cc = counters.get(id(p))
            body = self._compact_player(p, cc) if compact else self._detail_player(p, cc, m)
            parts.append(_anchor(f"e{i}") + body)
        parts.append(self._team_section(tp, compact))
        if own_civ:
            parts.append(_anchor("you") + (self._own_compact(own_civ) if compact else self._own_detail(own_civ)))
        if allies and not compact:
            parts.append(self._ally_section(allies, m))
        if not compact:
            # empty space at the end so the last sections can also be scrolled to the top
            line_px = self.content.fontMetrics().lineSpacing() or 18
            lines = max(0, self.content.viewport().height() // line_px - 2)
            parts.append("<br>" * lines + "&nbsp;")
        self.content.setHtml("".join(parts))

    def _render_nav(self, m: Match, mp: MapInfo | None) -> None:
        def item(anchor: str, label: str, color: str | None = None) -> tuple[str, str]:
            dot = f'<span style="color:{color}">●</span> ' if color else ""
            return (f"{dot}{label}", anchor)

        groups: list[list[tuple[str, str]]] = []
        if mp and (mp.has_notes or mp.official):
            groups.append([item("map", f'<span style="color:{C_MAP}">Map</span>')])
        groups.append([item(f"e{i}", self._civ_name(p, m, icon=False), p.color_hex)
                       for i, p in enumerate(m.opponents)])
        team = []
        if m.me:
            team.append(item("you", f'<span style="color:{C_OWN}">You</span>', m.me.color_hex))
        team += [item(f"a{i}", self._civ_name(p, m, icon=False), p.color_hex) for i, p in enumerate(m.allies)]
        groups.append(team)

        spec: list[tuple[str, str | None]] = []
        for g in (g for g in groups if g):
            if spec:
                spec.append((f'<span style="color:{C_DIM}">|</span>', None))
            spec += g
        self.nav.set_items(spec)
        self.nav.show()

    def jump_to(self, href: str) -> None:
        anchor = href.lstrip("#")
        if self.compact:
            # the compact view has no full sections – switch to detail for this jump (not saved)
            self.compact = False
            self.render()
        # scroll now (forcing the document layout first) and once more after Qt has laid out
        # the new content – right after a view switch the first attempt can land too early
        self._scroll_to(anchor)
        QTimer.singleShot(40, lambda: self._scroll_to(anchor))

    def _scroll_to(self, anchor: str) -> None:
        self.content.document().documentLayout().documentSize()
        self.content.scrollToAnchor(anchor)

    def eventFilter(self, obj, event) -> bool:
        # Ctrl+wheel anywhere on the overlay changes the font size
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            self.change_font(1 if event.angleDelta().y() > 0 else -1)
            return True
        # drag the window by its content; plain wheel events still scroll
        if obj is self.content.viewport() and event.type() == QEvent.MouseButtonPress \
                and event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()
            return True
        return super().eventFilter(obj, event)

    def _lock_mark(self) -> str:
        if not self.locked:
            return ""
        return (f' <span style="color:{C_DIM}" title="Locked">🔒 locked '
                f'({_e(self.cfg.hotkey_lock)} to unlock)</span>')

    def _civ_name(self, p: Player, m: Match, icon: bool = True) -> str:
        if p.civ:
            img = ""
            if icon:
                url = self.icons.get(p.civ.key.lower(), p.civ_image_url)
                if url:
                    s = round(self.cfg.font_size * 1.6)
                    img = f'<img src="{url}" width="{s}" height="{s}" style="vertical-align:middle"> '
            return img + _e(p.civ.name)
        return "Civ hidden" if m.hide_civs or not p.civ_enum else _e(p.civ_enum)

    def _who(self, p: Player) -> str:
        """Color dot + player name + rating."""
        dot = f'<span style="color:{p.color_hex}">●</span> ' if p.color_hex else ""
        rating = f' <span style="color:{C_DIM}">({p.rating})</span>' if p.rating else ""
        return f'{dot}<span style="color:{C_DIM}">{_e(p.display_name)}</span>{rating}'

    # ---- allies
    def _ally_section(self, allies: list[Player], m: Match) -> str:
        rows = ['<hr>', f'<div style="color:{C_OWN}"><b>Your team</b></div>']
        for i, p in enumerate(allies):
            civ = p.civ
            rows.append(_anchor(f"a{i}") + f'<div style="margin-top:4px;"><b style="color:{C_OWN}">'
                        f'{self._civ_name(p, m)}</b> {self._who(p)}</div>')
            if civ:
                rows.append(f'<div style="color:{C_DIM}">{_e(civ.kind)} · {_e(_short_units(civ.unique_units))}</div>')
                if civ.team_bonus:
                    rows.append(f'<div><b>Team bonus (you get it too):</b> {_e(civ.team_bonus)}</div>')
        return "".join(rows)

    # ---- map
    def _map_section(self, mp: MapInfo | None, compact: bool) -> str:
        if not mp or not (mp.has_notes or mp.official):
            return ""
        if compact:
            bits = mp.tips[:2] or ([mp.extra] if mp.extra else [])
            if not bits:
                return ""
            return (f'<div style="margin-bottom:5px;"><b style="color:{C_MAP}">Map:</b> '
                    f'{_e(" · ".join(bits))}</div>')
        rows = [f'<div><b style="color:{C_MAP}; font-size:{self.cfg.font_size + 2}pt">{_e(mp.name)}</b></div>']
        if mp.official:
            rows.append(f'<div style="color:{C_DIM}"><i>{_e(mp.official)}</i></div>')
        if mp.resources:
            rows.append(f'<div><b>Start:</b> {_e(mp.resources)}</div>')
        if mp.extra:
            rows.append(f'<div><b>Also:</b> {_e(mp.extra)}</div>')
        rows.append(_ul(mp.tips, C_MAP))
        if mp.sources:
            rows.append(f'<div style="color:{C_DIM}; font-size:{self.cfg.font_size - 2}pt">Source: wiki</div>')
        return "".join(rows) + '<hr style="border:0; height:1px; background:#444;">'

    # ---- enemies
    def _compact_player(self, p: Player, cc: CivCounters | None) -> str:
        head = f'<b style="color:{C_HEAD}">{self._civ_name(p, self.match)}</b> {self._who(p)}'
        if not cc:
            return f'<div style="margin-bottom:5px;">{head}</div>'
        lines = []
        for t in cc.threats[:2]:
            ans = t.answers[0] if t.answers else "no direct counter"
            lines.append(f'{_e(t.name)} → <span style="color:{C_ACCENT}">{_e(ans)}</span>')
        return f'<div style="margin-bottom:5px;">{head}<br>{" · ".join(lines)}</div>'

    def _detail_player(self, p: Player, cc: CivCounters | None, m: Match) -> str:
        civ = p.civ
        head = (f'<div style="margin-top:6px;"><b style="color:{C_HEAD}; font-size:{self.cfg.font_size + 2}pt">'
                f'{self._civ_name(p, m)}</b> {self._who(p)}</div>')
        if not civ or not cc:
            return head
        t = civ.tips
        rows = [f'<div style="color:{C_DIM}">{_e(civ.kind)}</div>']
        if t.get("profile"):
            rows.append(f'<div>{_e(t["profile"])}</div>')
        if t.get("dangers"):
            rows.append(f'<div style="color:{C_DANGER}"><b>Watch out</b></div>{_ul(t["dangers"], C_DANGER)}')
        rows.append(f'<div style="color:{C_ACCENT}"><b>Their key units → your answer</b></div>')
        items = []
        for th in cc.threats:
            star = "★ " if th.unique else ""
            ans = ", ".join(th.answers) if th.answers else "no direct counter in your tech tree"
            items.append(f'{star}<b>{_e(th.name)}</b> – {_e(th.blurb)}<br>'
                         f'<span style="color:{C_DIM}">weak vs {_e(", ".join(th.weak_vs))}</span><br>'
                         f'<span style="color:{C_ACCENT}">you: {_e(ans)}</span>')
        rows.append('<ul style="margin:0 0 0 -22px;">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        if civ.gaps:
            rows.append(f'<div style="color:{C_GOOD}"><b>They lack</b></div>{_ul(civ.gaps, C_GOOD)}')
        rows.append(f'<div style="color:{C_DIM}"><b>Team bonus:</b> {_e(civ.team_bonus)}</div>')
        return head + "".join(rows)

    # ---- team plan
    def _team_section(self, tp: TeamPlan, compact: bool) -> str:
        items = []
        for unit, vs in tp.build:
            items.append(f'<b>{_e(unit)}</b> <span style="color:{C_DIM}">vs {_e(", ".join(vs))}</span>')
        for pk in tp.picks:
            items.append(f'Good pick: <b>{_e(pk.unit)}</b> <span style="color:{C_DIM}">– {_e(pk.reason)}</span>')
        if tp.shared_gaps:
            gaps = ", ".join(f"{g} ({n}/{tp.enemy_count})" for g, n in tp.shared_gaps[: 2 if compact else 4])
            items.append(f'<span style="color:{C_GOOD}">Enemy team lacks: {_e(gaps)}</span>')
        if tp.no_answer and not compact:
            items.append(f'<span style="color:{C_DANGER}">No direct counter for: {_e(", ".join(tp.no_answer))}</span>')
        if not items:
            return ""
        return (f'<hr style="border:0; height:1px; background:#444;">'
                f'<div style="color:{C_ACCENT}"><b>Build</b></div>'
                '<ul style="margin:0 0 0 -22px;">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>")

    # ---- own civ
    def _own_compact(self, civ) -> str:
        gaps = ", ".join(g.removeprefix("no ") for g in civ.gaps[:4])
        tail = f' · <span style="color:{C_DIM}">lack: {_e(gaps)}</span>' if gaps else ""
        return (f'<div style="margin-top:4px;"><b style="color:{C_OWN}">You: {_e(civ.name)}</b> '
                f'{_e(_short_units(civ.unique_units))}{tail}</div>')

    def _own_detail(self, civ) -> str:
        t = civ.tips
        return (f'<hr style="border:0; height:1px; background:#444;">'
                f'<div><b style="color:{C_OWN}; font-size:{self.cfg.font_size + 2}pt">You: {_e(civ.name)}</b>'
                f' <span style="color:{C_DIM}">{_e(civ.kind)}</span></div>'
                + (f'<div>{_e(t.get("profile", ""))}</div>' if t.get("profile") else "")
                + f'<div><b>Unique:</b> {_e("; ".join(civ.unique_units))}</div>'
                + f'<div style="color:{C_OWN}"><b>Bonuses</b></div>{_ul(civ.bonuses)}'
                + f'<div style="color:{C_DIM}"><b>You lack</b></div>{_ul(civ.gaps, C_DIM)}')

    # ------------------------------------------------------------------ move/save
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def moveEvent(self, e) -> None:
        self._save_timer.start()
        super().moveEvent(e)

    def resizeEvent(self, e) -> None:
        self._save_timer.start()
        super().resizeEvent(e)

    def _save_geometry(self) -> None:
        g = self.geometry()
        self.cfg.geometry = [g.x(), g.y(), g.width(), g.height()]
        self.cfg.save()
