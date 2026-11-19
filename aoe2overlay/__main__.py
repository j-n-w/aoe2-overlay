"""Entry point: python -m aoe2overlay [--demo | --last-match]"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import Config, user_dir
from .hotkeys import HotkeyListener
from .live import LiveFeed, ReplayFeed
from .logs import setup_logging
from .match import demo_match, fetch_last_match
from . import autostart
from .overlay import Overlay

log = logging.getLogger("aoe2overlay")


class Bridge(QObject):
    """Forwards hotkey events from the hook thread to the GUI thread."""
    toggle = Signal()
    mode = Signal()
    lock = Signal()


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#f2c063"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor("#101218"))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(36)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "C")
    p.end()
    return QIcon(pm)


def main() -> int:
    ap = argparse.ArgumentParser(prog="aoe2overlay", description="AoE2 Counter Overlay")
    ap.add_argument("--demo", action="store_true", help="show sample match (3v3 Rage Forest)")
    ap.add_argument("--last-match", action="store_true", help="show last real match via API")
    ap.add_argument("--screenshot", metavar="PNG", help="(test) save window as image and quit")
    ap.add_argument("--detail", action="store_true", help="start in detail view")
    ap.add_argument("--replay", metavar="JSONL", help="(test) replay a websocket capture instead of going live")
    args = ap.parse_args()

    setup_logging()
    cfg = Config.load()
    log.info("start (%s), config in %s", " ".join(sys.argv[1:]) or "live", user_dir())

    if not args.screenshot and not single_instance():
        print("AoE2 Counter Overlay is already running (see the tray icon).")
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon = make_icon()
    app.setWindowIcon(icon)

    win = Overlay(cfg)
    if args.detail:
        win.compact = False  # only for this run, not saved

    feed = None
    if args.demo:
        win.set_match(demo_match(cfg.profile_id))
    elif args.last_match:
        try:
            m = fetch_last_match(cfg.profile_id)
            win.set_match(m, None if m else "No match found")
        except Exception as e:  # show network errors instead of crashing
            win.set_status(f"API error: {e}")
    else:
        feed = ReplayFeed(cfg.profile_id, args.replay) if args.replay else LiveFeed(cfg.profile_id)
        feed.match_started.connect(lambda m: on_started(win, m), Qt.QueuedConnection)
        feed.match_ended.connect(lambda mid: on_ended(win, cfg.hide_after_game_s), Qt.QueuedConnection)
        feed.status.connect(win.set_status, Qt.QueuedConnection)
        feed.start()
        # show briefly so it's clear the app runs, then wait hidden for the game start
        QTimer.singleShot(4000, lambda: win.hide() if win.match is None else None)
    win.show()

    if args.screenshot:
        def shoot():
            win.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(800, shoot)
        return app.exec()

    # tray menu (the overlay has no taskbar entry)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("AoE2 Counter Overlay")
    menu = QMenu()
    act_show = QAction(f"Show/hide ({cfg.hotkey_toggle})", menu, triggered=win.toggle_visible)
    act_mode = QAction(f"Compact/detail ({cfg.hotkey_mode})", menu, triggered=win.toggle_mode)
    act_lock = QAction(f"Lock – clicks go to the game ({cfg.hotkey_lock})", menu, checkable=True,
                       checked=win.locked, triggered=lambda checked: win.set_locked(checked))
    act_demo = QAction("Show demo match", menu, triggered=lambda: on_started(win, demo_match(cfg.profile_id)))
    act_last = QAction("Show last match", menu, triggered=lambda: show_last_match(win, cfg.profile_id))
    act_folder = QAction("Open settings folder", menu, triggered=lambda: os.startfile(user_dir()))
    act_auto = QAction("Start with Windows", menu, checkable=True)
    act_auto.setEnabled(autostart.available())
    act_auto.toggled.connect(lambda on: autostart.set_enabled(on))
    act_quit = QAction("Quit", menu, triggered=app.quit)

    def before_menu():
        act_lock.setChecked(win.locked)
        act_auto.blockSignals(True)
        act_auto.setChecked(autostart.is_enabled())
        act_auto.blockSignals(False)
    menu.aboutToShow.connect(before_menu)
    menu.addActions([act_show, act_mode, act_lock])
    menu.addSeparator()
    menu.addActions([act_demo, act_last])
    menu.addSeparator()
    menu.addActions([act_folder, act_auto])
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: win.toggle_visible() if r == QSystemTrayIcon.Trigger else None)
    tray.show()

    bridge = Bridge()
    bridge.toggle.connect(win.toggle_visible, Qt.QueuedConnection)
    bridge.mode.connect(win.toggle_mode, Qt.QueuedConnection)
    bridge.lock.connect(win.toggle_lock, Qt.QueuedConnection)
    try:
        hk = HotkeyListener({cfg.hotkey_toggle: bridge.toggle.emit, cfg.hotkey_mode: bridge.mode.emit,
                             cfg.hotkey_lock: bridge.lock.emit})
        hk.start()
        if hk.errors:
            win.set_status("Hotkey problem: " + "; ".join(hk.errors))
            log.warning("hotkeys: %s", hk.errors)
    except ValueError as e:
        win.set_status(f"Hotkey error: {e}")
        hk = None

    rc = app.exec()
    if hk:
        hk.stop()
    if feed:
        feed.stop()
    return rc


_mutex = None


def single_instance() -> bool:
    """True if no other overlay instance runs (named Windows mutex, released when the process exits)."""
    global _mutex
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, "Local\\aoe2-counter-overlay")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


_hide_timer: QTimer | None = None


def on_started(win: Overlay, match) -> None:
    if _hide_timer:
        _hide_timer.stop()
    win.set_match(match)
    win.show()
    win.raise_()


def on_ended(win: Overlay, delay_s: int) -> None:
    """Keep the info readable on the score screen for a moment, then hide."""
    global _hide_timer

    def hide():
        win.set_match(None, "Game over – waiting for next game …")
        win.hide()
    if _hide_timer is None:
        _hide_timer = QTimer(win, singleShot=True)
        _hide_timer.timeout.connect(hide)
    win.set_status("Game over")
    _hide_timer.start(max(0, delay_s) * 1000)


def show_last_match(win: Overlay, profile_id: int) -> None:
    try:
        m = fetch_last_match(profile_id)
    except Exception as e:
        log.warning("last match: %r", e)
        win.set_status(f"API error: {e}")
        win.show()
        return
    if m:
        on_started(win, m)
    else:
        win.set_status("No match found")
        win.show()


if __name__ == "__main__":
    sys.exit(main())
