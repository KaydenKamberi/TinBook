# Hardware Specification — Tinbook device (Phase 2)

> AI agents: this is the exact hardware. Do not assume any other board, screen, or battery. If something here conflicts with a vendor's current docs, trust the vendor docs and note it in your handoff.

## 1. Bill of materials (exact parts)
| # | Part | Exact model | Do NOT confuse with |
|---|---|---|---|
| 1 | Computer | **Raspberry Pi Zero 2 WH** (Zero 2 W with pre-soldered 40-pin header; Raspberry Pi part SC0721) | Pi Zero **WH** (original, single-core, Bluetooth 4.1), Pi Zero 2 W without header, Pi Zero W |
| 2 | Screen + buttons | **Pimoroni Display HAT Mini** (PIM589) | Pimoroni Display HAT Mini is not the "Mini PiTFT", "1.3\" LCD HAT", or "Display HAT" (non-mini) |
| 3 | Battery | **PiSugar 3** (1200 mAh, pogo-pin, for Pi Zero) | PiSugar 2, PiSugar S, PiSugar 3 **Plus** (5000 mAh, for Pi 3/4) |
| 4 | Storage | microSD, 32 GB, A1 or A2, Class 10 / U1+ (e.g. SanDisk Ultra, Samsung EVO Select) | — |
| 5 | Sync cable | Micro-USB (male) → USB-A or USB-C (match Kayden's PC), **data** cable, ≤ 30 cm | "Charge-only" cables — they won't work for sync |
| 6 | Case | Altoids Classic peppermint tin (standard size) | Altoids Smalls / Arctic tins (too small) |
| 7 | Insulation | Kapton tape or electrical tape; optional 1–2 mm craft foam sheet | — |
| 8 | Mounting | Double-sided foam tape (non-conductive); M2.5 standoffs are included with the HAT | — |
| — | Already owned | AirPods (Bluetooth A2DP), USB-C charger/cable, soldering iron (not required), PC | — |

## 2. Raspberry Pi Zero 2 WH
- SoC: RP3A0 (BCM2710A1), 4× Arm Cortex-A53 @ 1 GHz, 64-bit
- RAM: 512 MB LPDDR2 — keep memory use small; no desktop environment
- Wireless: 2.4 GHz 802.11 b/g/n Wi-Fi + Bluetooth 4.2 / BLE, **one shared radio** (Wi-Fi activity can cause Bluetooth audio stutter → turn Wi-Fi off during playback)
- Ports: mini-HDMI, **micro-USB "USB"** (OTG/data — used for USB gadget sync), **micro-USB "PWR IN"** (not used; PiSugar powers the board), microSD, CSI camera
- 40-pin GPIO header, pre-soldered
- Size: 65 × 30 mm
- OS: Raspberry Pi OS **Lite 64-bit** (latest version offered by Raspberry Pi Imager). Boot config lives at `/boot/firmware/config.txt`.

## 3. Pimoroni Display HAT Mini
- 2.0" IPS LCD, 320 × 240, ST7789V2 driver, SPI, ~220 PPI
- 4 tactile buttons (A, B, X, Y) + RGB LED + QwST connector + Breakout Garden header (unused)
- Size ≈ 65.5 × 35 × 9 mm; about 5 mm taller than the Pi Zero
- **With a Pi Zero attached on the included standoffs, total depth ≈ 17 mm** (before the PiSugar)
- Buttons sit close to the screen edge — case cut-outs must not press on the display or its ribbon cable edge
- Software: Pimoroni `displayhatmini` Python library (+ Pillow). Use the library's constants (`DisplayHATMini.BUTTON_A`, etc.) — **never hardcode GPIO numbers.** Expected (verify against the library): buttons A=GPIO5, B=GPIO6, X=GPIO16, Y=GPIO24; LED R/G/B = GPIO17/27/22; backlight = GPIO13; display on SPI0.
- Expected physical layout (verify with the demo in CP6B): **A top-left, B bottom-left, X top-right, Y bottom-right** of the screen. The button map in §5 is by name, so it still works if the layout differs.
- Requires SPI enabled.

## 4. PiSugar 3
- 1200 mAh LiPo, connected to the PiSugar board by cable; board attaches **under** the Pi via pogo pins and screws. **Uses no GPIO header pins** — fully compatible with the Display HAT Mini on top.
- USB-C charging port on the PiSugar board. Charging while running (UPS) supported.
- I2C at 0x57 (and RTC 0x68) — requires I2C enabled. No conflict with the Display HAT Mini.
- Power button with accidental-touch protection: **power on = short press, then long press.**
- Software: PiSugar power manager
  ```
  wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
  bash pisugar-power-manager.sh -c release
  ```
  Web UI on port 8421. `device/power.py` talks to `pisugar-server` over its local TCP interface (expected port 8423; verify).
- Vendor claims 8–10 h on older Pi Zeros; **our estimate for Zero 2 W + Bluetooth audio is 3–5 h.** Measure in CP8.
- ⚠ Verify in PiSugar docs whether plugging the Pi's micro-USB data port into a PC (for sync) while the PiSugar is attached is safe (back-powering). If not, sync must only happen with the PiSugar switched off or the design must change. CP5 must resolve this before CP7.

## 5. Button map & behavior
Names refer to Display HAT Mini buttons. Events: `tap` (<600 ms), `hold` (≥600 ms), `long` (≥1500 ms).

| Screen | A | B | X | Y |
|---|---|---|---|---|
| **Library** | tap: up | tap: down | tap: open & play selected (resume) | tap: go to Now Playing (if a book is loaded) · hold: Menu |
| **Now Playing** | tap: −30 s · hold: previous chapter | tap: +30 s · hold: next chapter | tap: play/pause | tap: Library (keeps playing) · hold: Menu |
| **Menu / lists** | tap: up | tap: down | tap: select | tap: back |
| **Asleep (screen off)** | ignored | ignored | **long: wake** | ignored |
| **Sync mode** | — | — | — | long: eject & exit sync |

- Screen sleeps after 20 s without input (backlight off). While asleep, every input except X `long` is ignored (pocket lock). Playback continues.
- LED: brief green on wake; slow red blink at ≤15% battery; solid blue in sync mode.
- Menu items: Bluetooth (scan / connect / forget), Speed (0.75–2.0), Sync mode, Battery info, Shut down.

## 6. Physical assembly (Altoids tin)
1. Flash the microSD with Raspberry Pi Imager (OS Lite 64-bit; set hostname `tinbook`, username, Wi-Fi, enable SSH). Boot the bare Pi on a USB power supply and confirm `ssh <user>@tinbook.local` works.
2. Attach the PiSugar 3 under the Pi (align pogo pins with the header pads, screw in). Charge it fully. Boot from battery.
3. Mount the Display HAT Mini on top using the included standoffs.
4. Run CP5 setup. Confirm screen, buttons, battery reading, and AirPods audio all work **before** it goes in the tin.
5. **Measure the tin's inside depth.** Stack ≈ 17 mm (Pi + HAT) + PiSugar board (measure). If it doesn't fit with the lid closed: remove standoffs and use foam tape, or use a deeper tin / 3D-printed case.
6. Line the inside of the tin (base + walls) with Kapton/electrical tape or foam. **No bare metal may touch the boards.**
7. Place the stack screen-up so the lid opens like a flip cover. Place the battery beside the stack, away from any cut edges. Never bend, puncture, or squeeze the LiPo.
8. With everything in place, mark and cut **two openings** on the tin wall: PiSugar USB-C (charging) and the Pi's micro-USB **"USB"** port (sync). Also make sure the PiSugar power button is reachable (opening or reachable with lid open). File all edges smooth and cover them with tape.
9. Secure the stack with foam tape. Bluetooth test with the lid **closed** at pocket-to-ear distance; if it cuts out, drill a small hole near the Pi's antenna end (opposite the ports side).

## 7. OS configuration summary (implemented in CP5)
- SPI on, I2C on, `dtoverlay=dwc2` (USB gadget capable; `g_mass_storage` loaded only in sync mode)
- Audio: PipeWire + WirePlumber + `libspa-0.2-bluetooth`; user lingering enabled; `mpv` for playback
- Library: FAT32 image `/home/<user>/tinbook.img` (16 GB, label `TINBOOK`) mounted at `/mnt/tinbook`; `TINBOOK_LIBRARY_DIR=/mnt/tinbook/library`
- Power: CPU governor `powersave`, activity LED off, Wi-Fi off during playback (`rfkill`), backlight off when idle

## 8. Open items to verify on real hardware
- [ ] Button physical layout matches §3
- [ ] PiSugar back-powering safety during USB sync (§4)
- [ ] PiSugar TCP port/commands
- [ ] Stack depth vs. tin depth
- [ ] Bluetooth range with lid closed
- [ ] Real battery life
