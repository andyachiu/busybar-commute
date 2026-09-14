# Upcoming Events native app

This optional firmware overlay adds an **Upcoming Events** entry to the BUSY Bar Apps menu.

The app reads two local files:

- `/ext/user_assets/commute-bar/events-a.bin`
- `/ext/user_assets/commute-bar/events-b.bin`

It selects the newest valid snapshot when opened and checks again after 60 seconds without input. Turn the wheel to browse at most 20 events, press OK for details, and press Back to return. The front uses two lines scrolling together at 25 pixels per minute beside the event icon: event name above, date and start time below. Cached data older than one hour is labeled stale.

Snapshots use a fixed-size, credential-free format with strict lengths, NUL-terminated strings, and CRC32 validation. The Python publisher uploads the inactive A/B slot and records it only after the upload succeeds. Invalid or partial data does not replace the in-memory schedule.

The native cache contains public event names, venues, timing, icon categories, and provisional departure advice. It does not contain office or home addresses, routing credentials, BUSY tokens, or live route results.

## Build

The overlay targets official firmware 1.2.4 at commit `b315346d2d0a686c5fada9e972bc688e85bd4137`:

```sh
git clone --recursive --branch 1.2.4 https://github.com/busy-app/busybar-firmware.git /tmp/busybar-firmware
git -C /tmp/busybar-firmware checkout b315346d2d0a686c5fada9e972bc688e85bd4137
git -C /tmp/busybar-firmware submodule update --init --recursive
python3 native/prepare.py /tmp/busybar-firmware
cd /tmp/busybar-firmware
./fbt TARGET_HW=22 FIRMWARE_ORIGIN=CommuteBar
```

The upstream checkout must include its submodules, and the build downloads a compiler. Replace target 22 only after checking your device's reported target. This repository deliberately excludes compiled firmware.

> [!NOTE]
> `./fbt` runs `git submodule update --init --recursive` itself on every invocation unless `FBT_NO_SYNC` is set, so a non-recursive clone is normally repaired automatically. The explicit flags above match the upstream README and make the dependency visible; they are belt-and-braces rather than strictly required.

> [!WARNING]
> Flashing a self-built image can leave the device with a working display and USB API but a **non-functional Wi-Fi radio** — for example on an intercom (Si917) version mismatch, which upstream exposes an `INTERCOM_FORCE_VERSION` override for. Always verify Wi-Fi after flashing, while you still have a known-good network available:
>
> ```sh
> curl -s http://10.0.4.20/api/wifi/networks   # expect 200 + network list, not 503
> ```

## Generate a local cache

```sh
python3 -m commutebar --refresh
python3 -m commutebar.snapshot data/events.json /tmp/events-a.bin --config config.local.json
```

The official asset endpoint accepts the snapshot as an app-scoped file named `events-a.bin` or `events-b.bin`. Keep authentication in a token file or secret mount and out of shell history and source control.

## Test

`tests/test_snapshot.py` compiles the real C decoder and checks Python/C compatibility, capacity, truncation, corruption, unterminated strings, checksum failures, A/B publication, and exclusion of private address fields.
