# Troubleshooting

## Resolved: Wi-Fi scan returns no networks after flashing a self-built firmware

**Status:** Resolved as of 2026-09-14. Device and Wi-Fi are fully functional.

### Resolution & Root Cause
The radio hardware and custom firmware overlay were never broken. 
1. The firmware rejects Wi-Fi scanning while associated to an AP (`[WifiStatusScanNotPossible] = {.code = 400, "Scan not possible when connected"}`).
2. `./fbt flash_usb` updates only the STM32 main MCU without power-cycling the Silicon Labs Si917 wireless coprocessor.
3. Because the BusyBar runs on an internal battery, unplugging USB did not power off the device. The coprocessor retained an associated/connecting state across the MCU flash, causing the scan endpoint to return `Scan not possible when connected` (or `Generic error` if connection failed), resulting in zero networks in the companion app.
4. After a cold restart and issuing `POST /api/wifi/disconnect`, `/api/wifi/networks` successfully returned all visible networks (13 networks scanned).

See [UPSTREAM-PROPOSAL.md](UPSTREAM-PROPOSAL.md) for the upstream firmware fixes for `updater.c` and `api_wifi.c`.


### Symptom

The BUSY companion app shows an **empty Wi-Fi network list** — zero networks, even in
dense environments where dozens are visible from a laptop. Selecting a network is
impossible because none are ever listed.

This presents as an office/corporate-network compatibility problem. It is not one.

### Root symptom, measured directly

The app populates its list from a device endpoint that is hard-failing:

```console
$ curl -s -m 8 -w " [%{http_code}, %{time_total}s]\n" http://10.0.4.20/api/wifi/networks
{"error":"Generic error"} [503, 0.019s]
```

Consistent across repeated attempts. Two details make this diagnostic:

1. **The endpoint is real, not a typo.** Nonexistent paths return an HTML `404` page.
   This returns a JSON `503`. `POST`/`PUT` return `405 Method Not Allowed`, confirming
   a real GET-only route.
2. **~19ms is an instant rejection, not a scan timeout.** A genuine Wi-Fi scan takes
   1–4 seconds because the radio must dwell on each channel. Failing in 19ms means the
   firmware never engages the radio at all — the wireless subsystem is refusing the
   request outright.

Meanwhile `/api/wifi/status` returns `200` with `{"state":"disconnected"}`, and there
is **no** `enable`/`radio`/`power` endpoint, so this is not a setting that was toggled off.

### Correlation with the flash

| Evidence | Value |
| --- | --- |
| `firmware.commit_hash` | `b315346d-dirty` — a **self-built** image (`-dirty` = uncommitted tree) |
| `firmware.build_date` | `2026-09-13` |
| `system.uptime` | ~22h at time of diagnosis — booted immediately after that build |
| Prior behavior | Wi-Fi worked on **stock** firmware, before this flash |

The flash broke Wi-Fi. The precise mechanism is **unconfirmed**.

### Ruled out — do not re-investigate these

All of the following were considered and eliminated. The failure is entirely device-side.

| Hypothesis | Why it's eliminated |
| --- | --- |
| Captive portal on the guest network | Failure occurs before any association attempt |
| SSID band compatibility (2.4GHz vs 5GHz) | Irrelevant; no scan is ever performed |
| Corporate client isolation | Failure is inside the device |
| Companion-app permissions (Android Location, iOS Local Network) | Would fail identically on a known-good home network; it did not |
| MDM policy on the phone | Device-side fault |
| Dead radio / antenna hardware | Worked on stock firmware on the same hardware |
| Unset regulatory domain | Would have failed everywhere, including at home |
| **Missing git submodules** (`git clone` without `--recursive`) | **`./fbt` runs `git submodule update --init --recursive` on every invocation** unless `FBT_NO_SYNC` is set, so a non-recursive clone self-repairs before building |

> [!NOTE]
> The submodule theory was investigated at length and is **wrong**. It is listed here
> specifically so it isn't rediscovered and pursued again. A correct recursive clone does
> fetch `lib/wiseconnect` (the Silicon Labs WiSeConnect SDK for the SiWx917, ~337MB,
> containing `connectivity_firmware/*.rps` coprocessor images) — but `fbt` would have
> fetched it anyway.

### Intercom (Si917) version mismatch (confirmed 2026-09-14)

**Confirmed.** A main-MCU image built from a commit other than the coprocessor's logs
`[E][IntercomSync] Handshake failure, possible version mismatch` in `/ext/log.txt`, suspends
the intercom service, and leaves `/api/wifi/status` at `unknown`. The intercom control
string defaults to the build's git hash, and `flash_usb` never updates the Si917, so build
from the exact commit the device reports as `intercom_version`. Passing
`INTERCOM_FORCE_VERSION=<that hash>` to `./fbt` also pins the handshake. The original
analysis follows.

The upstream firmware README documents an `INTERCOM_FORCE_VERSION` variable used to
"override the intercom (Si917) version check." A dedicated escape hatch implies version
mismatches between the main firmware and the Si917 wireless coprocessor are a known,
recurring failure mode. If the built firmware disagrees with the coprocessor image on the
device, the wireless subsystem would fail to initialize — producing exactly the observed
instant `503`.

Supporting hint: the device reports `intercom_version` as `b315346d` — a **git commit
hash**, not a version string — alongside `nwp_version` `1611.2.1.1.255.11.71`, which does
not match the WiSeConnect SDK's `2.15.5.1.x.x` scheme.

This was later confirmed; see above.

---

## Next steps

### Why this can't be done on a corp-managed macOS machine

The `fbt` toolchain is downloaded pre-built and **ad-hoc signed**. macOS rejects and
`SIGKILL`s it:

```console
$ toolchain/arm64-darwin/bin/arm-none-eabi-gcc --version
exit=137          # SIGKILL, zero output

$ codesign -dv toolchain/arm64-darwin/bin/python3.11
Signature=adhoc, flags=0x20002(adhoc,linker-signed)

$ spctl -a -vv toolchain/arm64-darwin/bin/arm-none-eabi-gcc
rejected
```

This affects the **entire toolchain**, not just its bundled Python — substituting a
system Python does not help, because `arm-none-eabi-gcc` is killed the moment the build
invokes it. Do not attempt to disable Gatekeeper or strip security attributes on a managed
machine. Build on a personal machine or in a Linux container instead.

### Recovery and rebuild procedure

Perform this **somewhere with a known-good Wi-Fi network available**, so Wi-Fi can be
verified immediately after flashing.

**1. Restore stock firmware first.** Use the official BUSY companion app over USB. The
device exposes `/api/update` (accepts `POST`), and the USB link works even with Wi-Fi
broken. Note there is **no OTA fallback** — Wi-Fi is required for auto-update, so USB is
the only recovery path.

**2. Confirm stock firmware restores Wi-Fi:**

```sh
curl -s -m 8 http://10.0.4.20/api/wifi/networks    # expect 200 + network list
```

If this still returns `503` on stock firmware, the problem is not the overlay build and
the device likely needs vendor support.

**3. Rebuild — stock first, no overlay.** This isolates whether the overlay is implicated
at all:

```sh
git clone --recursive --branch 1.2.4 https://github.com/busy-app/busybar-firmware.git
cd busybar-firmware
git checkout b315346d2d0a686c5fada9e972bc688e85bd4137
./fbt TARGET_HW=22
./fbt flash_usb
curl -s -m 8 http://10.0.4.20/api/wifi/networks    # must be 200 before continuing
```

**4. Only if step 3 passes**, apply the overlay and repeat:

```sh
python3 /path/to/busybar-commute/native/prepare.py .
./fbt TARGET_HW=22 FIRMWARE_ORIGIN=CommuteBar
./fbt flash_usb
curl -s -m 8 http://10.0.4.20/api/wifi/networks    # verify again
```

If step 3 passes and step 4 fails, the overlay build is implicated and
`INTERCOM_FORCE_VERSION` is the next thing to investigate.

> [!TIP]
> The overlay is optional. `config.example.json` ships `native_snapshot_enabled: false`,
> and the entire hosted Cloud Run path in `commutebar/hosted.py` works on stock firmware.
> Staying on stock costs nothing essential.

---

## Device API reference (observed)

Discovered by probing firmware 1.2.4 / API 27.5.0 over the USB interface. Useful for
diagnostics; not an official specification.

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/status` | GET | Full device/firmware/system/power telemetry |
| `/api/wifi/status` | GET | `{"state":"disconnected"}` |
| `/api/wifi/networks` | GET | Scan results — the endpoint the companion app uses |
| `/api/wifi/connect` | POST | GET returns `405` |
| `/api/wifi/disconnect` | POST | GET returns `405` |
| `/api/update` | POST | Firmware update transport |
| `/api/display/draw` | POST/DELETE | Used by `commutebar/device.py` |

> [!TIP]
> **Probing technique:** nonexistent routes return an **HTML** `404` page, while real
> routes return **JSON**. A JSON error body means the endpoint exists and is genuinely
> failing; an HTML 404 means you guessed the path wrong.

### USB connectivity

The bar exposes a USB virtual ethernet interface. The host takes `10.0.4.21`, the device
is `10.0.4.20`:

```sh
ifconfig | grep -B3 "10.0.4.21"     # find the interface (e.g. en12)
ping -c 3 10.0.4.20
curl -s http://10.0.4.20/api/status | python3 -m json.tool
```

Note `power.state` reads `discharging` while on USB with a full battery; if
`battery_current` is `0` and `usb_voltage` is ~5000mV, the device is running on USB power
and this is normal.
