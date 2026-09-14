"""BUSY Bar HTTP API 27.5.0 adapter, verified against the connected USB schema."""
import json
import textwrap
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .sources import request
from .details import event_details, cause, stamp

APP = 'commute-bar'


def ascii_text(text):
    return ''.join(c if 32 <= ord(c) <= 126 else ' ' for c in text).strip() or ' '


def payload(plan, test=False, animation_path=None):
    color = '#FFCC66FF' if plan['level'] == 'warning' else '#A9EFCCFF'
    lifetime = 60 if test else 120
    if test:
        heading, sub = 'HOME BY 5', 'USB TEST'
        lines = ['Commute Bar - USB test', 'Home by 5:00 PM', 'Usual leave: 4:15 PM', 'Target: 4:50 PM', 'Events + traffic alerts', 'Test expires in 60 sec']
    else:
        heading = 'OFF DUTY' if plan['front_action'] == 'OFF DUTY' else 'GO HOME'
        event = plan.get('notice_event') or next((e for e in plan['events'] if e['conflict']), None)
        sub = 'CHECK MAPS' if not event else ('GIANTS GAME' if event['kind'] == 'baseball' else event['title'])
        lines = [ascii_text(event['title'] if event else 'Commute Bar'), 'Target arrival: '+plan['target']]
        lines += textwrap.wrap(ascii_text(plan['action']), width=27)[:5]
        lines += ['Event estimate' if 'traffic_checked_at' not in plan else 'Google Maps '+stamp(plan['traffic_checked_at'])]
        if event:
            details = event_details(event, plan['fetched_at'], plan['stale'], plan.get('show_scores', True))
            lines = [event['title'], details[0], cause(event), plan['action'],
                     'Target home: '+plan['target'],
                     'Event precaution' if 'traffic_checked_at' not in plan else 'Google Maps '+stamp(plan['traffic_checked_at'])]
            if len(details) >= 4:
                lines += details[-2:]
            else:
                lines += details[1:2] + ['Updated '+stamp(plan['fetched_at'])]
        if plan.get('advance_notice'):
            heading = ('GIANTS GAME' if event['kind']=='baseball' else event['title'])
            sub = plan['notice_start']+' / '+plan['notice_departure']
            lines = [event['title'],event.get('venue','Event nearby'),
                     'Starts: '+plan['notice_start'],plan['notice_departure'],
                     'Home target: '+plan['target'],plan['notice_basis'],
                     'Live checks 3:15-4:15 PM','Updated '+stamp(plan['fetched_at'])]
    elements = []
    def text(id, content, display, y, width, tint):
        return dict(id=id,type='text',text=ascii_text(content),font='small',display=display,
                    x=1,y=y,width=width,align='top_left',color=tint,timeout=lifetime,
                    scroll_rate=600,scroll_start_delay=1000,scroll_repeat_delay=1500)
    elements.append(text('heading',heading,'front',0,70,color))
    elements.append(text('detail',sub,'front',8,70,color))
    for i,line in enumerate(lines[:8]):
        elements.append(text(f'back-{i}',line,'back',i*10,144,'#FFFFFFFF'))
    if animation_path and not test:
        for element in elements:
            if element['display'] == 'front':
                element.update(x=18, width=53)
        elements.insert(0, dict(id='event-icon', type='animation', path=animation_path,
                               loop=True, display='front', x=0, y=0, timeout=lifetime))
    return dict(application_name=APP,priority=plan.get('display_priority', 10),elements=elements)


def send(plan, address='http://10.0.4.20', test=False):
    if not test and not plan['active']:
        return 'Outside commute window; device left unchanged.'
    try:
        return request(address.rstrip('/')+'/api/display/draw',payload(plan,test))
    except HTTPError as exc:
        exc.close()
        if exc.code == 409:
            return 'Display busy: higher-priority app active; existing display preserved.'
        if exc.code == 403:
            return 'Device denied access; check USB connection or authentication.'
        return f'Device rejected display update (HTTP {exc.code}).'
    except (URLError, TimeoutError):
        return 'Device unavailable; preview saved. Reconnect and retry.'


def clear(address='http://10.0.4.20'):
    url=address.rstrip('/')+'/api/display/draw?'+urlencode({'application_name':APP})
    with urlopen(Request(url,method='DELETE'),timeout=8) as response:
        return response.read().decode()
