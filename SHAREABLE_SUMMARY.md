# XDM1041 workspace — summary for collaborators

This note is for anyone opening **`XDM1041`** in its **own Cursor (or VS Code) window**, separate from the parent **PICO** firmware project.

---

## Intended goal

Build a **Windows 11 desktop application** (GUI) that will eventually:

1. **Talk to an OWON XDM1041** bench multimeter over **USB serial** (SCPI), using **Python** and **PySerial**, for trusted **voltage / current** (and other mode) readings.
2. **Talk to a Raspberry Pi Pico** (over USB serial) running the **2DHC_Driver** MicroPython firmware in the sibling **`micropython/`** tree under **`PICO`**) so the Pico can drive the **Helmholtz coil** path (quasi-DC via PWM / bridge / RC).
3. **Run calibration workflows**: compare meter readings to Pico-reported values (and/or commanded behavior), so the **quasi-DC output** presented to the coil can be **characterized and corrected** in software.

The GUI stack is **PySide6 (Qt)**. After the app is stable, the plan is to **package it as a Windows `.exe`** (e.g. **PyInstaller** — see `requirements-exe.txt`).

---

## What has been set up in this folder

| Item | Purpose |
|------|--------|
| **`.venv/`** | **Dedicated** Python virtual environment for this app only. **Do not** use global Python or **`PICO/.venv`** for XDM1041 work. |
| **`requirements.txt`** | **`pyserial`**, **`PySide6`** — install with **`XDM1041\.venv\Scripts\python.exe -m pip install -r requirements.txt`**. |
| **`requirements-exe.txt`** | **`pyinstaller`** (optional, for later `.exe` builds) — same venv only. |
| **`XDM1041.code-workspace`** | Open this in Cursor/VS Code so the workspace root is **`XDM1041`** and **new terminals** target **`.venv`**. |
| **`.vscode/settings.json`** | **`python.defaultInterpreterPath`** → **`.venv\Scripts\python.exe`**, terminal auto-activation enabled. |
| **`pyrightconfig.json`** | Analysis uses **`.venv`** inside this folder. |

**Reference hardware protocol (not vendored here):** community SCPI examples for the XDM1041, e.g. [TheHWcave/OWON-XDM1041](https://github.com/TheHWcave/OWON-XDM1041) (`Utility/XDM1041.py`, **`SCPI/`** command notes).

---

## How to open the “other” Cursor instance

1. **File → Open Workspace from File…**
2. Choose **`XDM1041\XDM1041.code-workspace`** (under the repo, same level as `requirements.txt`).

Or **Open Folder…** → select the **`XDM1041`** directory.

Confirm the status bar / **Python: Select Interpreter** shows **`.\.venv\Scripts\python.exe`**. New integrated terminals should activate **that** venv (Python extension required).

---

## Relationship to the PICO Cursor instance

| Window | Focus |
|--------|--------|
| **PICO** (repo root / `PICO.code-workspace`) | MicroPython on Pico (`micropython/`), **`deploy.py`**, coil driver firmware, **`PICO/.venv`** for host tools (e.g. deploy). |
| **XDM1041** (this workspace) | Desktop **PySide6** app, **XDM1041** + (later) **Pico serial** calibration UI, **`XDM1041/.venv`** only. |

Same git repo can be cloned once; **two Cursor windows** = two different **workspace roots** and two **venvs**, by design.

---

## What is *not* done yet

- **GUI application code** (main window, flows) — to be implemented under **`XDM1041/`**.
- **XDM1041 driver module** — thin PySerial/SCPI client to be added (may follow patterns from the GitHub reference above).
- **Pico serial client** — speak the existing line protocol (`HELP`, `TARGET`, `PWM`, `READ`, `STATUS`, …) from `micropython/main.py`.
- **PyInstaller** build scripts / CI — after the GUI works.

---

## One-line pitch

**“Calibration bench app: OWON XDM1041 as reference + Pico as coil driver, in one PySide6 tool, isolated in `XDM1041/.venv` on Windows 11.”**
