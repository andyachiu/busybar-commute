"""Read the same public event service as Chase Center's calendar."""
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urljoin
from .sources import request, TZ

PAGE = 'https://chasecenter.com/events/'
GATEWAY = 'https://baseline-api-gateway-9rhe3qap.uc.gateway.dev'


def client_settings(html, loader=request):
    # This is public website client configuration, not a user's credential.
    # Fail closed when the site's build structure changes.
    match = re.search(r'<script src="([^" ]*/1421-[a-z0-9]+\.js)"', html)
    if not match:
        raise ValueError('Chase calendar configuration moved')
    js = loader(urljoin(PAGE, match[1]))
    def value(export):
        symbol = re.search(re.escape(export) + r':\(\)=>(\w+)', js)
        if not symbol:
            raise ValueError('Chase client configuration changed')
        literal = re.search(r'\b' + re.escape(symbol[1]) + r'="([^"\n]+)"', js)
        if not literal:
            raise ValueError('Chase client value missing')
        return literal[1]
    host, public_key = value('u2'), value('j5')
    if host != GATEWAY:
        raise ValueError('Chase service host changed; review required')
    return host, public_key


def parse_chase(body):
    if not isinstance(body.get('data'), list) or not isinstance(body.get('hasMore'), bool):
        raise ValueError('Chase event response changed')
    events = {}
    for row in body['data']:
        if row.get('hideFromCalendar') or row.get('hideDateTime'):
            continue
        kind = row['eventType']
        if kind in ('gsw', 'gsv'):
            if row.get('home') is not True:
                continue
        elif kind != 'cce':
            # Small Thrive City activities are not treated as arena-scale traffic.
            continue
        elif 'chase center' not in (row.get('location') or '').lower():
            continue
        if re.search(r'cancel(?:led|ed)|postponed', row.get('topFlagTextOverride') or '', re.I):
            continue
        start = datetime.fromisoformat(row['datetime']).astimezone(TZ)
        doors = datetime.fromisoformat(row['doorsOpenTime']).astimezone(TZ).isoformat() if row.get('doorsOpenTime') else None
        event = dict(id='chase-'+row['uid'], title=row['title'], venue='Chase Center', source='Chase Center',
                     date=start.date().isoformat(), start=None if row.get('hideTime') else start.isoformat(),
                     end=None, kind='arena', status='Published schedule', doors=doors,
                     url='https://chasecenter.com/events/'+row['uid']+'/')
        events[event['id']] = event
        event['event_type'] = 'basketball' if kind in ('gsw', 'gsv') else 'arena_event'
    return list(events.values())


def fetch_chase(now, loader=request):
    host, public_key = client_settings(loader(PAGE), loader)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = {}
    for page in range(1, 11):
        url = host + '/api/v1/prod/events?' + urlencode(dict(start=start.isoformat(),
            end=(start+timedelta(days=31)).isoformat(),sortByDatetime='asc',page=page,pageSize=100))
        body = json.loads(loader(url, headers={'x-api-key':public_key}))
        rows.update({e['id']:e for e in parse_chase(body)})
        if not body['hasMore']:
            return list(rows.values())
    raise ValueError('Chase pagination exceeded safety bound; coverage incomplete')
