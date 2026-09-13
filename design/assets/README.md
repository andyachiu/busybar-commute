# Event animation assets

These original, text-free 72 × 16 pixel loops leave the right side blank for native text:

- baseball
- basketball
- convention
- event ticket
- traffic/car
- detour
- lunch bowl

The `.gif` files are editable conversion sources, PNG files are static references, and `.anim` files are BUSY Bar assets. `manifest.json` records their dimensions, timing, format, and hashes.

Rebuild them with Pillow and busyshow 0.1.0:

```sh
python3 -m pip install Pillow
python3 design/assets/build_assets.py /absolute/path/to/busyshow
```

The script invokes only the converter's offline `convert` command and validates the resulting binary layout. It does not contact a device or BUSY service. Firmware animation formats can change; verify the generated files against the firmware version and physical device before enabling them.

The source art and drawing script are original to Commute Bar. busyshow is by Nathan and contributors and is available under MIT OR Apache-2.0. Both license texts are retained in this directory; the converter binary is not included.
