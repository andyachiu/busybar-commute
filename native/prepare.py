"""Apply prototype overlay to the exact tested upstream revision; never flash."""
import shutil
import subprocess
import sys
import re
from pathlib import Path

# This is the exact 1.2.4 release currently installed on the user's target-22 bar.
PIN = 'b315346d2d0a686c5fada9e972bc688e85bd4137'
root = Path(sys.argv[1]).resolve()
head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
if head != PIN:
    raise SystemExit('Firmware revision differs from reviewed source')
shutil.copytree(Path(__file__).parent / 'upcoming_events', root / 'applications/main/upcoming_events', dirs_exist_ok=True)
for icon in (Path(__file__).parent / 'upcoming_events/assets').glob('*.png'):
    shutil.copy2(icon, root / 'assets/images/external/apps_menu' / icon.name)
package = root / 'applications/main/application.fam'
text = package.read_text()
if '"upcoming_events"' not in text:
    package.write_text(text.replace('        "clock",', '        "clock",\n        "upcoming_events",'))
header = root / 'applications/system/apps_menu/app_list.h'
source = root / 'applications/system/apps_menu/app_list.c'
text = header.read_text()
if 'AppsMenuEntryIdxUpcoming' not in text:
    header.write_text(text.replace('    AppsMenuEntryIdxComingSoon,', '    AppsMenuEntryIdxUpcoming,\n    AppsMenuEntryIdxComingSoon,'))
text = source.read_text()
if '[AppsMenuEntryIdxUpcoming]' not in text:
    text = text.replace('    [AppsMenuEntryIdxComingSoon]', '''    [AppsMenuEntryIdxUpcoming] = {
        .id = "upcoming_events",
        .name = "Upcoming Events",
        .icon_path = {
            .front = APPS_MENU_IMG_PATH("upcoming_front_8x8.image"),
            .back = APPS_MENU_IMG_PATH("upcoming_back_11x11.image"),
        },
    },
    [AppsMenuEntryIdxComingSoon]''')
else:
    text = re.sub(
        r'(\[AppsMenuEntryIdxUpcoming\][\s\S]*?\.front = APPS_MENU_IMG_PATH\(")\w+_front_8x8(\.image"\),[\s\S]*?\.back = APPS_MENU_IMG_PATH\(")\w+_back_11x11(\.image"\),)',
        r'\1upcoming_front_8x8\2upcoming_back_11x11\3', text, count=1)
source.write_text(text)
print('Prototype overlay prepared. Device unchanged.')
