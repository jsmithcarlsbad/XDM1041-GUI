# Remote serial protocol (Pico ↔ XDM1041 GUI)

This document describes the **ASCII line protocol** over a **second USB‑serial link** (the Pico) while the PC GUI uses a **separate** COM port for the OWON XDM1041. The goal is to keep the Pico side simple (MicroPython `uart.readline()` style).

**Scope:** Behaviour here matches what the desktop GUI implements for `comboBox_RemotePort` / `comboBox_RemoteBaud` / `pushButton_RemoteOpen`. If the GUI and this file ever disagree, treat the **running GUI** as authoritative and update this file.

---

## Operator visibility (GUI follows the Pico)

The bench **operator is meant to watch the same screen** while the Pico runs a test:

- **`MODE`** — Updates the **DMM mode** combo and **mode icon** immediately (same as if the operator chose that function). Range/sample-rate widgets stay consistent with the new mode.
- **`START` / `STOP`** (or `ACQ …`) — Toggles **Acquire**; when the XDM1041 is connected and acquisition is on, the **LCD readout** updates in **real time** at the meter poll rate (GUI sample rate + instrument integration).
- **Manual GUI use** — The operator can still change mode or Acquire with the mouse; the next Pico command will move the GUI again to match the script.

So the Pico drives automation, while the GUI remains the **live monitor** for mode changes and measured values.

---

## Range / scaling (auto only on Pico side)

The **Pico is expected to use automatic ranging only** for measurements:

- The protocol does **not** define manual range steps (`RANGE n`, etc.). The Pico should not rely on cycling fixed ranges.
- Readings are reported as the GUI formats them after the instrument’s **auto-range** behaviour (GUI **Auto** vs **Manual** affects SCPI `AUTO` vs `RANGE` — see below).
- When the **remote UART is opened** in the desktop GUI, the app switches **Auto/Manual** to **Auto** and sends **`AUTO`** to the meter (when connected), so remote sessions start in **instrument auto-range** unless the user changes it again in the GUI.

If you need manual ranging for bench work, do it in the GUI; the Pico protocol stays oriented around **single `READ` lines** suitable for scripted stimulus/measure loops.

---

## Transport

| Item | Value |
|------|--------|
| Framing | 8 data bits, no parity, 1 stop bit (8N1) |
| Baud | Configurable (e.g. `115200`); must match GUI INI / combo box |
| Encoding | UTF‑8 |
| Message boundary | One line per message, terminated by **LF** (`\n`). The GUI may also accept **CRLF** (`\r\n`) on input. |
| Direction | **Full duplex**: Pico sends **commands**; PC sends **replies** and **measurement lines** whenever rules below say so. |

---

## Two independent timers (important)

1. **Meter acquisition** — How often the PC polls the XDM1041 (GUI “Acquire” + instrument **RATE F/M/S**). This can be slow or bursty.
2. **Remote publish rate** — How often the PC **transmits the last cached reading** to the Pico on the remote UART (`RATE` command, Hz).

The PC **always** updates its internal cache when a new reading arrives from the meter. At each remote **tick** (every `1 / RATE` seconds), it sends **one line** with that **last** value. If the meter is slower than `RATE`, the **same** line may be sent again until a new reading arrives. No back‑pressure queue is required on the Pico for normal use.

---

## Commands (Pico → PC)

Send a single line per command. Leading/trailing spaces are ignored. `#` starts an optional comment line (ignored by the PC).

Case: command **keywords** are matched case‑insensitively where noted. **Mode IDs** are lowercase with underscores, exactly as in the table below.

### `PICO <version string>` (required after connect)

As soon as the USB/UART link to the PC is usable, the Pico **must** send one line identifying its firmware so the operator can confirm the correct device and build.

```text
PICO <version>
```

- **`<version>`** is a **free-text** string (any printable UTF‑8 you like): e.g. `0.2.1`, `mpy-2024-01-15`, `MicroPython v1.23.1 on RP2040`, or a git hash.
- Send it **early** — typically right after your `UART`/`usb_cdc` is ready, or immediately after you receive the host line `READY xdm_gui` (order either way is fine; the GUI accepts `PICO` anytime while the remote port is open).
- The GUI **status bar** shows **COM port**, **baud rate**, and this **Pico version** string (plus a note that auto-range is on) so the bench operator can monitor the link at a glance.
- If the line is missing text after `PICO`, the PC replies with `ERR pico_version_missing`.

**Example (MicroPython-style):**

```text
PICO MicroPython v1.23.1; xdm-remote 0.1.0
```

### `MODE <mode_id>`

Selects the DMM function in the GUI (same as changing the mode combo). The PC applies this to the meter when the meter link is connected and acquisition is running, per GUI logic.

Ranging for that mode follows the GUI’s **Auto/Manual** state; for Pico-driven workflows, assume **Auto** (see **Range / scaling** above).

**Example:** `MODE dc_volts`

### `START` / `STOP`

Controls **acquisition** (equivalent to checking/unchecking **Acquire** in the GUI).

- `START` — begin polling the meter (if connected).
- `STOP` — stop polling; GUI may show idle readout.

Aliases (if implemented): `ACQ 1`, `ACQ ON`, `ACQ 0`, `ACQ OFF`.

### `RATE <hz>`

Sets the **remote UART publish rate** in **hertz** (lines per second).

- `RATE 10` — send at most **10** `READ …` lines per second (same cached value repeated if the meter is slower).
- `RATE 0` — disable periodic publish (implementation may still send on other events; see GUI notes).

Reasonable range: e.g. **0.1 Hz … 50 Hz** (exact caps are GUI‑defined).

### `PING`

Liveness check.

**Reply:** one line `PONG`.

---

## Valid `mode_id` values

Use these exact strings (same as `XDM1041_GUI.py`):

| `mode_id` | Meaning |
|-----------|---------|
| `dc_volts` | DC voltage |
| `ac_volts` | AC voltage |
| `ohms` | Resistance |
| `dc_current` | DC current |
| `ac_current` | AC current |
| `frequency` | Frequency |
| `capacitance` | Capacitance |
| `diode` | Diode test |
| `continuity` | Continuity |
| `temperature` | Temperature |

Unknown `MODE` IDs should produce an `ERR` line (see below).

---

## Lines from PC → Pico

### Measurement: `READ`

Each published sample is **one line**:

```text
READ<TAB><mode_id><TAB><value><TAB><unit>
```

- **`<TAB>`** is the ASCII tab character (`\t`, byte `0x09`).
- **`<mode_id>`** — same vocabulary as `MODE`.
- **`<value>`** — human‑readable string as shown on the LCD (may contain spaces, e.g. `1.234 K`, `500 mΩ`, `OVER RANGE`, `OPEN`). It is **not** guaranteed to be a single float token.
- **`<unit>`** — short **scale/unit hint** for automation (e.g. `V`, `A`, `Ω`, `Hz`, `F`, `°C`, `—`). The PC derives this from mode + formatted text; treat it as a **hint**, not a full parser for `<value>`.

**Example:**

```text
READ	dc_volts	1.2345	V
```

**Example (resistance with suffix in value):**

```text
READ	ohms	2.0050 kΩ	kΩ
```

If a field must contain a tab (unlikely), the GUI should escape or strip tabs inside `<value>`; Pico code may assume **exactly three** tabs if parsing naïvely.

### Status / errors: `ERR` / `OK`

```text
ERR <code> [<short message>]
```

Examples (wording may vary slightly in the app):

- `ERR unknown_mode`
- `ERR no_meter` — action needs the XDM1041 connected
- `ERR bad_rate` — invalid `RATE` argument

Optional success acks (if implemented): `OK …`

### Session banner (PC → Pico)

After the remote port is opened successfully, the PC sends:

```text
READY xdm_gui
```

The Pico may treat this as **host ready** and then (or immediately on enumerate) send its required **`PICO …`** version line. The PC continues with `PONG`, `ERR`, `READ`, … as applicable.

---

## Suggested Pico (MicroPython) usage

1. Open UART at the configured baud, 8N1.
2. **Print the version line once** (required), e.g. `uart.write(b"PICO my-fw 0.1.0\\n")` — optionally after you see `READY xdm_gui` on the read side.
3. Send commands with `\n` termination.
4. Read with `uart.readline()` (or equivalent), `decode('utf-8')`, `strip()`.
5. Split `READ` lines:

   ```python
   if line.startswith("READ\t"):
       parts = line.split("\t", 3)
       if len(parts) == 4:
           _, mode_id, value, unit = parts
   ```

6. Use a **non-blocking** read loop or `select.poll` if you must service both UART and other tasks.
7. Do not assume `READ` lines are **only** periodic: handle **bursts** if the GUI also sends immediate updates after certain events.

---

## INI file (PC side)

`XDM_GUI.ini` defines **two independent serial ports**. The file header (written whenever the GUI saves settings) states which section is which:

| Section | Hardware | Typical keys |
|---------|----------|----------------|
| **`[instrument]`** | **OWON XDM1041** multimeter (SCPI) | `port`, `baudrate`, `databits`, `parity`, `stopbits`, `dmm_mode`, `sample_rate`, … |
| **`[remote]`** | **Pico / remote** second UART (this protocol) | `port`, `baudrate` |

Do **not** swap these: the meter and the Pico must use **different** COM ports.

Remote-specific options:

- `port` — COM device for the Pico (e.g. `COM5`)
- `baudrate` — integer baud (often `115200`)
- `publish_hz` — optional default for `RATE` after open (when implemented in the GUI)

Opening the remote port in the GUI also persists `port` / `baudrate` under **`[remote]`** and, as elsewhere in this doc, switches **Auto/Manual** to **Auto**.

---

## Versioning

When the protocol changes, bump a version string in the `READY` line or add `PROTO 1` / `PROTO 2` commands. Pico code can branch on that if needed.

---

## Summary cheat sheet

| Direction | Line |
|-----------|------|
| Pico → PC | `PICO <version>` (**once after connect**) |
| Pico → PC | `MODE dc_volts` |
| Pico → PC | `START` / `STOP` |
| Pico → PC | `RATE 10` |
| Pico → PC | `PING` |
| PC → Pico | `READY xdm_gui` |
| PC → Pico | `PONG` |
| PC → Pico | `READ\t<mode>\t<value>\t<unit>` |
| PC → Pico | `ERR …` |
