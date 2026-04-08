"""
XDM1041 bench GUI — loads Qt Designer UI at runtime and reads/writes XDM_GUI.ini.
All use of pyserial (open/read/write/close) runs on a dedicated QThread.
"""

from __future__ import annotations

import atexit
import configparser
import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any

import serial
from PySide6.QtCore import QCoreApplication, QFile, QThread, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QPalette, QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QLCDNumber,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
)

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None  # type: ignore[misc, assignment]

APP_DIR = Path(__file__).resolve().parent
INI_PATH = APP_DIR / "XDM_GUI.ini"
UI_PATH = APP_DIR / "XDM1041_GUI.ui"
ABOUT_HARDWARE_IMAGE = APP_DIR / "XDM1041.png"

APP_VERSION = "1.0"
AUTHOR_EMAIL = "jsmith.carlsbad@gmail.com"

INI_SECTION = "instrument"
DEFAULTS: dict[str, str] = {
    "port": "",
    "baudrate": "115200",
    "databits": "8",
    "parity": "N",
    "stopbits": "1",
}

GUI_SECTION = "gui"
GUI_DEFAULTS: dict[str, str] = {
    # qt-material theme file name; default is a dark scheme
    "theme": "dark_blue.xml",
}

# PySerial does not expose a per-port baud list on Windows; USB-serial / XDM1041 use standard rates.
STANDARD_BAUD_RATES: tuple[int, ...] = (
    1200,
    2400,
    4800,
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    460800,
    921600,
)


def _com_port_sort_key(device: str) -> tuple[int, str]:
    m = re.match(r"COM(\d+)$", device, re.IGNORECASE)
    if m:
        return (int(m.group(1)), device.lower())
    return (9999, device.lower())


def _is_bluetooth_port(info: Any) -> bool:
    blob = f"{getattr(info, 'device', '')} {getattr(info, 'name', '')} "
    blob += f"{getattr(info, 'description', '')} {getattr(info, 'hwid', '')}"
    return "bluetooth" in blob.lower()


def list_windows_com_ports_excluding_bluetooth() -> list[Any]:
    if list_ports is None:
        return []
    out: list[Any] = []
    try:
        for info in list_ports.comports():
            if sys.platform == "win32" and _is_bluetooth_port(info):
                continue
            out.append(info)
    except OSError:
        pass
    out.sort(key=lambda i: _com_port_sort_key(i.device))
    return out


def _parity_from_ini(value: str) -> int:
    key = (value or "N").strip().upper()[:1]
    mapping = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    return mapping.get(key, serial.PARITY_NONE)


def _bytesize_from_ini(value: str) -> int:
    try:
        n = int((value or "8").strip())
    except ValueError:
        return serial.EIGHTBITS
    return {5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}.get(
        n, serial.EIGHTBITS
    )


def _stopbits_from_ini(value: str) -> float:
    s = (value or "1").strip()
    if s == "2":
        return serial.STOPBITS_TWO
    return serial.STOPBITS_ONE


def _scpi_read_line(ser: serial.Serial) -> str:
    """Read one SCPI response line (CRLF-terminated) on the serial thread only."""
    buf = bytearray()
    while True:
        chunk = ser.read(64)
        if not chunk:
            raise serial.SerialTimeoutException("Timeout waiting for meter response")
        buf.extend(chunk)
        if len(buf) >= 2 and buf[-2:] == b"\r\n":
            break
        if len(buf) > 4096:
            raise serial.SerialException("Response too long or malformed")
    line = buf.decode("ascii", errors="replace").strip()
    return line


def _scpi_query(ser: serial.Serial, cmd: str) -> str:
    ser.write((cmd.strip() + "\n").encode("ascii", errors="replace"))
    return _scpi_read_line(ser)


def apply_xdm_lcd_style(lcd: QLCDNumber) -> None:
    """Black background, amber segments, flat (not 3D) digit style."""
    lcd.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
    lcd.setFrameShape(QFrame.Shape.NoFrame)
    lcd.setAutoFillBackground(True)

    amber = QColor(255, 176, 0)
    black = QColor(0, 0, 0)
    pal = lcd.palette()
    pal.setColor(QPalette.ColorRole.Window, black)
    pal.setColor(QPalette.ColorRole.WindowText, amber)
    pal.setColor(QPalette.ColorRole.Base, black)
    pal.setColor(QPalette.ColorRole.Text, amber)
    pal.setColor(QPalette.ColorRole.Light, amber)
    pal.setColor(QPalette.ColorRole.Dark, black)
    pal.setColor(QPalette.ColorRole.Mid, amber)
    lcd.setPalette(pal)

    lcd.setStyleSheet("QLCDNumber { background-color: #000000; border: none; }")


def list_qt_material_themes() -> list[str]:
    """Return installed qt-material theme resource names (e.g. dark_blue.xml)."""
    try:
        from qt_material import list_themes

        return sorted(list_themes())
    except ImportError:
        return []


def resolve_stored_gui_theme(cfg: configparser.ConfigParser) -> str:
    """Pick a valid qt-material theme from INI, falling back to default dark."""
    want = (cfg.get(GUI_SECTION, "theme", fallback=GUI_DEFAULTS["theme"]) or "").strip()
    available = list_qt_material_themes()
    if want in available:
        return want
    dark_first = sorted(t for t in available if t.startswith("dark_"))
    if dark_first:
        return dark_first[0]
    return available[0] if available else ""


def apply_qt_material_theme(app: QApplication, theme: str) -> bool:
    """
    Apply a qt-material stylesheet. Import runs after PySide6 is loaded.
    See https://pypi.org/project/qt-material/
    """
    if not theme:
        return False
    try:
        from qt_material import apply_stylesheet
    except ImportError:
        return False
    apply_stylesheet(app, theme=theme)
    return True


def theme_menu_label(theme_file: str) -> str:
    base = theme_file.replace(".xml", "").replace("_", " ").strip()
    return base.title()


def show_about_dialog(parent: QMainWindow) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("About XDM1041 GUI")
    layout = QVBoxLayout(dlg)

    if ABOUT_HARDWARE_IMAGE.is_file():
        pix = QPixmap(str(ABOUT_HARDWARE_IMAGE))
        if not pix.isNull():
            img_lbl = QLabel()
            img_lbl.setPixmap(
                pix.scaledToWidth(440, Qt.TransformationMode.SmoothTransformation)
            )
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(img_lbl)

    html = (
        f"<h3>XDM1041 bench GUI</h3>"
        f"<p><b>Version</b> {APP_VERSION}</p>"
        f"<p>Desktop control and readout for the OWON XDM1041 multimeter "
        f"(USB serial / SCPI).</p>"
        f"<p><b>Third-party</b></p>"
        f"<ul>"
        f"<li><a href='https://www.qt.io/'>Qt</a> and "
        f"<a href='https://wiki.qt.io/Qt_for_Python'>Qt for Python (PySide6)</a></li>"
        f"<li><a href='https://github.com/pyserial/pyserial'>pyserial</a></li>"
        f"<li><a href='https://pypi.org/project/qt-material/'>qt-material</a> "
        f"(Material Design themes for Qt)</li>"
        f"</ul>"
        f"<p>Copyright © 2025. Licensed under the "
        f"<a href='https://opensource.org/licenses/MIT'>MIT License</a>.</p>"
        f"<p>Author: <a href='mailto:{AUTHOR_EMAIL}'>{AUTHOR_EMAIL}</a></p>"
    )
    if not ABOUT_HARDWARE_IMAGE.is_file():
        html = (
            "<p><i>Place <code>XDM1041.png</code> next to the application "
            "to show the hardware photo.</i></p>"
            + html
        )

    text = QTextBrowser()
    text.setOpenExternalLinks(True)
    text.setHtml(html)
    text.setMinimumWidth(460)
    text.setMaximumHeight(260)
    layout.addWidget(text)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)

    dlg.exec()


class MeterSerialService(QThread):
    """
    Dedicated thread: sole owner of serial.Serial. GUI enqueues open/close via queue.
    Emits results and errors to the GUI thread.
    """

    open_finished = Signal(bool, str)
    closed = Signal()
    comm_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cmd_q: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._ser: serial.Serial | None = None
        self._alive = True

    def request_open(self, params: dict[str, Any]) -> None:
        self._cmd_q.put(("open", params))

    def request_close(self) -> None:
        self._cmd_q.put(("close",))

    def request_shutdown(self) -> None:
        self._cmd_q.put(("shutdown",))

    def _close_port(self) -> None:
        if self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            except OSError as e:
                self.comm_error.emit(f"Close port: {e}")
            self._ser = None

    def _do_open(self, params: dict[str, Any]) -> None:
        self._close_port()
        try:
            self._ser = serial.Serial(
                port=params["port"],
                baudrate=int(params["baudrate"]),
                bytesize=int(params["bytesize"]),
                parity=params["parity"],
                stopbits=float(params["stopbits"]),
                timeout=float(params.get("timeout", 1.0)),
            )
        except (serial.SerialException, ValueError, TypeError) as e:
            self._ser = None
            self.open_finished.emit(False, str(e))
            return

        try:
            idn = _scpi_query(self._ser, "*IDN?")
        except (serial.SerialException, UnicodeError) as e:
            self._close_port()
            self.open_finished.emit(False, f"Meter did not respond: {e}")
            return

        self.open_finished.emit(True, idn)

    def _do_close(self) -> None:
        self._close_port()
        self.closed.emit()

    def run(self) -> None:
        try:
            while self._alive:
                try:
                    msg = self._cmd_q.get(timeout=0.25)
                except queue.Empty:
                    continue
                kind = msg[0]
                try:
                    if kind == "open":
                        self._do_open(msg[1])
                    elif kind == "close":
                        self._do_close()
                    elif kind == "shutdown":
                        self._alive = False
                        self._do_close()
                        break
                except Exception as e:
                    self._close_port()
                    if kind == "open":
                        # GUI shows one dialog from open_finished(False)
                        self.open_finished.emit(False, str(e))
                    else:
                        self.comm_error.emit(f"Serial thread error: {e}")
        finally:
            self._close_port()

    def shutdown_join(self, timeout_ms: int = 5000) -> None:
        self.request_shutdown()
        if not self.wait(timeout_ms):
            self.comm_error.emit("Serial thread did not stop cleanly; terminating.")
            self.terminate()
            self.wait(1000)


class RuntimeResources:
    """Tracks background threads; clean shutdown for meter serial service."""

    def __init__(self) -> None:
        self._shutdown_done = False
        self.bg_threads: list[threading.Thread | QThread] = []
        self.meter_serial: MeterSerialService | None = None

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True

        if self.meter_serial is not None:
            self.meter_serial.shutdown_join()
            self.meter_serial = None

        for t in self.bg_threads:
            try:
                if isinstance(t, QThread):
                    t.quit()
                    t.wait(3000)
                elif isinstance(t, threading.Thread) and t.is_alive():
                    t.join(timeout=3.0)
            except RuntimeError:
                pass
        self.bg_threads.clear()


class XdmGuiApplication(QApplication):
    """QApplication with a stable handle to RuntimeResources for window code."""

    def __init__(self, argv: list[str], runtime: RuntimeResources) -> None:
        super().__init__(argv)
        self.runtime = runtime


class MainWindowController:
    """Wires Designer widgets: COM list, baud list, connect toggle, status bar."""

    def __init__(
        self,
        window: QMainWindow,
        app: XdmGuiApplication,
        cfg: configparser.ConfigParser,
    ) -> None:
        self._window = window
        self._app = app
        self._cfg = cfg
        self._serial_svc: MeterSerialService | None = None
        self._connected = False
        self._user_requested_disconnect = False

        self._combo_port = window.findChild(QComboBox, "comboBox_XDM1041_ComPort")
        self._combo_baud = window.findChild(QComboBox, "comboBox_XDM1041_BaudRate")
        self._btn_connect = window.findChild(QPushButton, "pushButton_XDM1041_Connect")
        self._lcd = window.findChild(QLCDNumber, "lcdNumber_XDM1041_MeasuredValue")
        self._theme_group: QActionGroup | None = None
        self._status = window.statusBar()
        if self._status is None:
            sb = window.findChild(QStatusBar, "statusbar")
            if sb is not None:
                window.setStatusBar(sb)
                self._status = sb

    def setup(self) -> None:
        if self._combo_port is None or self._combo_baud is None or self._btn_connect is None:
            raise RuntimeError("UI is missing expected widgets (port/baud/connect).")

        self._serial_svc = MeterSerialService()
        self._serial_svc.open_finished.connect(self._on_serial_open_finished)
        self._serial_svc.closed.connect(self._on_serial_closed)
        self._serial_svc.comm_error.connect(self._on_serial_comm_error)
        self._serial_svc.start()
        self._app.runtime.meter_serial = self._serial_svc

        self._fill_baud_combo(preferred_baud=self._ini_baud_int())
        self._refresh_port_combo()
        self._combo_port.currentIndexChanged.connect(self._on_port_changed)
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        self._set_connected_ui(False)

        if self._lcd is not None:
            apply_xdm_lcd_style(self._lcd)

        self._wire_theme_and_help_menus()

        if self._status is not None:
            n = self._combo_port.count()
            if n:
                self._status.showMessage(f"Found {n} serial port(s). Ready.", 5000)
            else:
                self._status.showMessage("No serial ports found (Bluetooth excluded).", 0)
        else:
            QMessageBox.warning(
                self._window,
                "Status bar",
                "No QStatusBar found; add one in Qt Designer for connection messages.",
            )

    def _wire_theme_and_help_menus(self) -> None:
        menu_theme = self._window.findChild(QMenu, "menuTheme")
        if menu_theme is not None:
            menu_theme.clear()
            themes = list_qt_material_themes()
            if not themes:
                na = QAction("(install qt-material — pip install qt-material)", menu_theme)
                na.setEnabled(False)
                menu_theme.addAction(na)
            else:
                self._theme_group = QActionGroup(self._window)
                self._theme_group.setExclusive(True)
                current = resolve_stored_gui_theme(self._cfg)
                ordered = sorted(themes, key=lambda x: (0 if x.startswith("dark_") else 1, x))
                for t in ordered:
                    act = QAction(theme_menu_label(t), self._window)
                    act.setData(t)
                    act.setCheckable(True)
                    act.setChecked(t == current)
                    self._theme_group.addAction(act)
                    menu_theme.addAction(act)
                self._theme_group.triggered.connect(self._on_theme_selected)

        menu_help = self._window.findChild(QMenu, "menuHelp")
        if menu_help is not None:
            menu_help.clear()
            about = QAction("About", menu_help)
            about.triggered.connect(lambda: show_about_dialog(self._window))
            menu_help.addAction(about)

    def _on_theme_selected(self, action: QAction) -> None:
        theme = action.data()
        if not isinstance(theme, str):
            return
        if not apply_qt_material_theme(self._app, theme):
            QMessageBox.warning(
                self._window,
                "Theme",
                "qt-material is not installed. Run: pip install qt-material",
            )
            return
        self._cfg.set(GUI_SECTION, "theme", theme)
        save_settings(self._cfg)
        if self._lcd is not None:
            apply_xdm_lcd_style(self._lcd)

    def _on_serial_open_finished(self, ok: bool, detail: str) -> None:
        if ok:
            self._connected = True
            self._set_connected_ui(True)
            self._cfg.set(INI_SECTION, "port", self._current_port_device())
            self._cfg.set(INI_SECTION, "baudrate", str(self._current_baud()))
            save_settings(self._cfg)
            if self._status is not None:
                self._status.showMessage(f"Connected: {detail}", 0)
        else:
            self._connected = False
            self._set_connected_ui(False)
            if self._status is not None:
                self._status.showMessage(f"Connect failed: {detail}", 8000)
            QMessageBox.critical(self._window, "Serial error", detail)

    def _on_serial_closed(self) -> None:
        was_connected = self._connected
        user_disconnect = self._user_requested_disconnect
        self._user_requested_disconnect = False
        self._connected = False
        self._set_connected_ui(False)
        if self._status is not None:
            self._status.showMessage("Disconnected from XDM1041.", 5000)
        if (
            was_connected
            and not user_disconnect
            and not QCoreApplication.closingDown()
        ):
            QMessageBox.critical(
                self._window,
                "Connection lost",
                "The serial link to the XDM1041 closed unexpectedly.\n\n"
                "Check the USB cable, port, and meter power.",
            )

    def _on_serial_comm_error(self, message: str) -> None:
        if self._status is not None:
            self._status.showMessage(message, 8000)
        if not QCoreApplication.closingDown():
            QMessageBox.critical(self._window, "Communication error", message)

    def _ini_baud_int(self) -> int:
        try:
            return int(self._cfg.get(INI_SECTION, "baudrate", fallback="115200"))
        except ValueError:
            return 115200

    def _fill_baud_combo(self, preferred_baud: int | None = None) -> None:
        assert self._combo_baud is not None
        prev = preferred_baud
        if prev is None:
            text = self._combo_baud.currentText().strip()
            if text.isdigit():
                prev = int(text)
        self._combo_baud.clear()
        for rate in STANDARD_BAUD_RATES:
            self._combo_baud.addItem(str(rate), rate)
        target = prev if prev is not None else self._ini_baud_int()
        ix = self._combo_baud.findText(str(target))
        if ix >= 0:
            self._combo_baud.setCurrentIndex(ix)
        else:
            self._combo_baud.setCurrentIndex(max(0, self._combo_baud.findText("115200")))

    def _on_port_changed(self, _index: int) -> None:
        self._fill_baud_combo()

    def _refresh_port_combo(self) -> None:
        assert self._combo_port is not None
        ports = list_windows_com_ports_excluding_bluetooth()
        saved = (self._cfg.get(INI_SECTION, "port", fallback="") or "").strip()

        self._combo_port.clear()
        for info in ports:
            label = f"{info.device}"
            desc = (getattr(info, "description", None) or "").strip()
            if desc:
                label = f"{info.device} — {desc}"
            self._combo_port.addItem(label, info.device)

        if self._combo_port.count() == 0:
            self._combo_port.addItem("(no ports)", "")
            self._combo_port.setCurrentIndex(0)

        if saved:
            for i in range(self._combo_port.count()):
                if self._combo_port.itemData(i, Qt.ItemDataRole.UserRole) == saved:
                    self._combo_port.setCurrentIndex(i)
                    break

        self._fill_baud_combo(preferred_baud=self._ini_baud_int())

    def _current_port_device(self) -> str:
        assert self._combo_port is not None
        data = self._combo_port.currentData(Qt.ItemDataRole.UserRole)
        return (data if isinstance(data, str) else "") or ""

    def _current_baud(self) -> int:
        assert self._combo_baud is not None
        v = self._combo_baud.currentData(Qt.ItemDataRole.UserRole)
        if isinstance(v, int):
            return v
        text = self._combo_baud.currentText().strip()
        return int(text) if text.isdigit() else self._ini_baud_int()

    def _set_connected_ui(self, connected: bool) -> None:
        assert self._btn_connect is not None
        assert self._combo_port is not None
        assert self._combo_baud is not None
        self._btn_connect.setText("Disconnect" if connected else "Connect")
        self._combo_port.setEnabled(not connected)
        self._combo_baud.setEnabled(not connected)

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self._disconnect_meter()
            return
        self._connect_meter()

    def _connect_meter(self) -> None:
        assert self._serial_svc is not None
        device = self._current_port_device()
        if not device:
            if self._status is not None:
                self._status.showMessage("Select a COM port.", 5000)
            return

        baud = self._current_baud()
        params = {
            "port": device,
            "baudrate": baud,
            "bytesize": _bytesize_from_ini(self._cfg.get(INI_SECTION, "databits", fallback="8")),
            "parity": _parity_from_ini(self._cfg.get(INI_SECTION, "parity", fallback="N")),
            "stopbits": _stopbits_from_ini(self._cfg.get(INI_SECTION, "stopbits", fallback="1")),
            "timeout": 1.0,
        }

        if self._status is not None:
            self._status.showMessage(f"Opening {device}…", 3000)

        self._serial_svc.request_open(params)

    def _disconnect_meter(self) -> None:
        assert self._serial_svc is not None
        self._user_requested_disconnect = True
        self._serial_svc.request_close()
        self._cfg.set(INI_SECTION, "port", self._current_port_device())
        self._cfg.set(INI_SECTION, "baudrate", str(self._current_baud()))
        save_settings(self._cfg)


def load_settings() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if INI_PATH.is_file():
        cfg.read(INI_PATH, encoding="utf-8")
    if not cfg.has_section(INI_SECTION):
        cfg.add_section(INI_SECTION)
    for key, value in DEFAULTS.items():
        if not cfg.has_option(INI_SECTION, key):
            cfg.set(INI_SECTION, key, value)
    if not cfg.has_section(GUI_SECTION):
        cfg.add_section(GUI_SECTION)
    for key, value in GUI_DEFAULTS.items():
        if not cfg.has_option(GUI_SECTION, key):
            cfg.set(GUI_SECTION, key, value)
    return cfg


def save_settings(cfg: configparser.ConfigParser) -> None:
    with INI_PATH.open("w", encoding="utf-8", newline="\n") as f:
        f.write("; XDM1041 GUI — application settings (ASCII INI)\n")
        cfg.write(f)


def load_main_window() -> QMainWindow:
    ui_file = QFile(str(UI_PATH))
    if not ui_file.open(QFile.ReadOnly):
        raise FileNotFoundError(f"Cannot open UI file: {UI_PATH}")
    loader = QUiLoader()
    window = loader.load(ui_file)
    ui_file.close()
    if window is None:
        raise RuntimeError(f"QUiLoader failed for: {UI_PATH}")
    return window


def wire_file_exit(window: QMainWindow, app: QApplication) -> None:
    action = window.findChild(QAction, "actionExit")
    if action is not None:
        action.triggered.connect(app.quit)


def main() -> int:
    cfg = load_settings()
    if not INI_PATH.is_file():
        save_settings(cfg)

    runtime = RuntimeResources()
    atexit.register(runtime.shutdown)

    app = XdmGuiApplication(sys.argv, runtime)
    app.aboutToQuit.connect(runtime.shutdown)

    theme = resolve_stored_gui_theme(cfg)
    apply_qt_material_theme(app, theme)

    window = load_main_window()
    wire_file_exit(window, app)

    controller = MainWindowController(window, app, cfg)
    controller.setup()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
