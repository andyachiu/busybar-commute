"""Bounded, credential-free schedule snapshot for the native browser prototype."""
import argparse
import json
import struct
import unicodedata
import zlib
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .sources import TZ
from .planner import assess_event, at, clock
from .icons import event_icon

MAGIC = b'CBAR0001'
WIDTHS = (80, 48, 48, 80, 16)
MAX_EVENTS = 20
UPLOAD = 'https://api.busy.app/busybar/assets/upload'


def field(text, width):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore')
    text = bytes(c if 32 <= c < 127 else 32 for c in text)
    return text[:width - 1].ljust(width, b'\0')


def encode(cache, now, config=None):
    """Use the source timestamp, never make an old cache appear newly fetched."""
    fetched = datetime.fromisoformat(cache['fetched_at'])
    if fetched.tzinfo is None or now.tzinfo is None or fetched > now:
        raise ValueError('Invalid cache timestamp')
    today = now.astimezone(TZ).date().isoformat()
    events = sorted((e for e in cache['events']
                     if (e.get('end') or e['date'])[:10] >= today),
                    key=lambda e: (e['date'], e.get('start') or '', e['id']))
    rows, seen = [], set()
    for event in events:
        if event['id'] in seen:
            continue
        seen.add(event['id'])
        start = event.get('start')
        timing = (datetime.fromisoformat(start).astimezone(TZ).strftime('%a %m/%d %I:%M %p')
                  if start and event['kind'] not in ('advisory', 'convention')
                  else event['date'] + ' / hours unverified')
        advice = 'Departure: check commute alert; cached schedule only'
        if config and (now - fetched).total_seconds() <= 3600 and not any(
                s.get('status') == 'error' for s in cache.get('sources', [])):
            day = max(date.fromisoformat(event['date']), now.astimezone(TZ).date())
            if day.weekday() in config['commute_weekdays']:
                departure = at(day, config['departure'])
                assessed = [assess_event(e, day, departure, at(day, config['deadline']), config)
                            for e in cache['events']]
                conflict = any(e and e['conflict'] for e in assessed)
                leave = max(at(day, config['earliest_departure']), departure - timedelta(
                    minutes=config['event_warning_minutes'] if conflict else 0))
                advice = 'Plan: ' + clock(leave) + ' / provisional, check maps'
            else:
                advice = 'No office commute scheduled for this day'
        values = (event['title'], event.get('venue', ''), timing,
                  advice, event_icon(event))
        rows.append(b''.join(field(v, w) for v, w in zip(values, WIDTHS)))
        if len(rows) == MAX_EVENTS:
            break
    body = struct.pack('<II', int(fetched.timestamp()), len(rows)) + b''.join(rows)
    return MAGIC + struct.pack('<I', zlib.crc32(body)) + body


def upload(token, slot, blob):
    """Upload one complete inactive slot; an HTTP success is the acknowledgement."""
    if slot not in ('a', 'b'):
        raise ValueError('Invalid snapshot slot')
    query = urlencode({'application_name': 'commute-bar', 'file': f'events-{slot}.bin'})
    request = Request(UPLOAD + '?' + query, data=blob, method='POST', headers={
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/octet-stream',
        'User-Agent': 'CommuteBar/0.1 (native snapshot publisher)',
    })
    with urlopen(request, timeout=20) as response:
        response.read()


def publish(cache, token, snapshot, config, now):
    """Retry the same inactive slot until acknowledged, then alternate next time."""
    state, generation = cache.read_native_publish_state()
    if state.get('fetched_at') == snapshot['fetched_at']:
        return 'unchanged'
    slot = 'b' if state.get('slot') == 'a' else 'a'
    upload(token, slot, encode(snapshot, now, config))
    cache.write_native_publish_state(
        {'slot': slot, 'fetched_at': snapshot['fetched_at'], 'published_at': now.isoformat()},
        generation)
    return 'published'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else None
    blob = encode(json.loads(args.cache.read_text()), datetime.now(TZ), config)
    args.output.write_bytes(blob)
    print(f'Wrote {len(blob)} bytes; at most {MAX_EVENTS} events')


if __name__ == '__main__':
    main()
