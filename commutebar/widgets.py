"""Fixed public office widgets, independent of calendars and personal data."""
from datetime import timedelta
from .sources import TZ
from .device import APP


def lunch_payload(now, animation_path=None):
    now = now.astimezone(TZ)
    start = now.replace(hour=11, minute=30, second=0, microsecond=0)
    end = start + timedelta(minutes=10)
    if now.weekday() >= 5 or not start <= now < end:
        return None
    lifetime = max(1, min(120, int((end - now).total_seconds())))
    def text(id, value, display, y, width):
        return dict(id=id, type='text', text=value, font='small', display=display,
                    x=1, y=y, width=width, align='top_left', color='#FFCC66FF',
                    timeout=lifetime)
    elements = [
        text('heading', "LET'S GO", 'front', 0, 70),
        text('detail', 'TO LUNCH', 'front', 8, 70),
        text('back-0', "LET'S GO TO LUNCH", 'back', 20, 144),
    ]
    if animation_path:
        for element in elements:
            if element['display'] == 'front':
                element.update(x=18, width=53)
        elements.insert(0, dict(id='lunch-bowl', type='animation', path=animation_path,
                                loop=True, display='front', x=0, y=0, timeout=lifetime))
    return dict(application_name=APP, priority=20, elements=elements)
