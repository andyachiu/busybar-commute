"""Public source adapters. An unsuccessful fetch never becomes an empty success."""
import json
import re
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
MLB = 'https://statsapi.mlb.com/api/v1/schedule'
MOSCONE = 'https://www.moscone.com/v1/events_endpoint'
SFMTA = 'https://www.sfmta.com/reports/street-closure-and-event-list'


def request(url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    h = {'User-Agent': 'CommuteBar/0.1 (personal commute preview)', **(headers or {})}
    if data is not None:
        h['Content-Type'] = 'application/json'
    with urlopen(Request(url, data=data, headers=h), timeout=20) as response:
        return response.read().decode()


def parse_mlb(body):
    if not isinstance(body.get('dates'), list) or 'totalGames' not in body:
        raise ValueError('MLB response schema changed')
    events = {}
    for day in body['dates']:
        for game in day['games']:
            if game['teams']['home']['team']['id'] != 137 or game['venue']['id'] != 2395:
                continue
            state = game['status']['detailedState']
            if any(word in state.lower() for word in ('cancel', 'postpon')):
                continue
            unknown = game['status'].get('startTimeTBD', False)
            start = None if unknown else datetime.fromisoformat(game['gameDate'].replace('Z', '+00:00')).astimezone(TZ).isoformat()
            event = dict(id=f"mlb-{game['gamePk']}", title='Giants vs ' + game['teams']['away']['team']['name'],
                         venue='Oracle Park', source='Giants', date=game['officialDate'], start=start,
                         end=None, kind='baseball', status=state, url=f"https://www.mlb.com/gameday/{game['gamePk']}")
            event['opponent'] = game['teams']['away']['team']['name']
            event['game_state'] = game['status'].get('abstractGameState', '')
            scores = [game['teams'][side].get('score') for side in ('away', 'home')]
            # Scheduled games sometimes include zeros; those are not a played score.
            if event['game_state'] in ('Live', 'Final') and all(type(s) is int and s >= 0 for s in scores):
                event['score'] = dict(away=scores[0], home=scores[1])
            linescore = game.get('linescore') or {}
            if event['game_state'] == 'Live' and type(linescore.get('currentInning')) is int:
                event['inning'] = str(linescore.get('inningState', '')) + ' ' + str(linescore['currentInning'])
            events[event['id']] = event
    return list(events.values())


def parse_moscone(body):
    if not isinstance(body, list) or not body:
        raise ValueError('Moscone response missing calendar records')
    events = {}
    for row in body:
        # Venue's JS renders these wall-clock fields without a timezone conversion.
        # All-day conventions never imply a verified evening dismissal time.
        start = datetime.fromisoformat(row['start']).replace(tzinfo=TZ)
        end = datetime.fromisoformat(row['end']).replace(tzinfo=TZ)
        event = dict(id='moscone-' + row['nid'], title=row['title'], venue='Moscone Center',
                     source='Moscone', date=start.date().isoformat(), start=start.isoformat(), end=end.isoformat(),
                     kind='convention', status='Published dates; daily times unverified',
                     url='https://www.moscone.com/node/' + row['nid'])
        events[event['id']] = event
    return list(events.values())


def sfmta_health(html, now):
    date = re.search(r'<time[^>]+datetime="([^"]+)"', html)
    if not date:
        raise ValueError('Cannot verify SFMTA publication date')
    stamp = datetime.fromisoformat(date[1].replace('Z', '+00:00'))
    age = (now - stamp).days
    return dict(name='SFMTA closure PDF', status='review', url=SFMTA,
                detail=f'Closure list published {stamp.date()}; {age} days old. Manual review required; closures are not parsed.')


def refresh(now):
    from datetime import timedelta
    from concurrent.futures import ThreadPoolExecutor
    jobs = {
        'Giants': (MLB + '?' + urlencode(dict(sportId=1, teamId=137, startDate=now.date().isoformat(),
                                             endDate=(now.date() + timedelta(days=30)).isoformat(), hydrate='linescore')), parse_mlb),
        'Moscone': (MOSCONE, parse_moscone),
    }
    events, health = [], []
    def fetch(item):
        name, (url, parser) = item
        try:
            rows = parser(json.loads(request(url)))
            return rows, dict(name=name, status='ok', detail=f'{len(rows)} records loaded', url=url)
        except Exception as exc:
            return [], dict(name=name, status='error', detail=f'Fetch or parse failed ({type(exc).__name__}); coverage unavailable', url=url)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for rows, status in pool.map(fetch, jobs.items()):
            events.extend(rows)
            health.append(status)
    try:
        health.append(sfmta_health(request(SFMTA), now))
    except Exception as exc:
        health.append(dict(name='SFMTA closure PDF', status='error', detail=f'Cannot verify closure list ({type(exc).__name__})', url=SFMTA))
    from .chase import fetch_chase, PAGE
    from .advisories import fetch_advisories, INDEX
    try:
        rows = fetch_chase(now)
        events.extend(rows)
        health.append(dict(name='Chase Center', status='ok', detail=f'{len(rows)} arena events loaded; small plaza activities excluded', url=PAGE))
    except Exception as exc:
        health.append(dict(name='Chase Center', status='error', detail=f'Calendar unavailable ({type(exc).__name__}); do not infer no events', url=PAGE))
    try:
        rows, problems = fetch_advisories(now)
        events.extend(rows)
        health.append(dict(name='SFMTA advisories', status='partial' if problems else 'ok',
                           detail=f'{len(rows)} downtown driving advisories; {len(problems)} items need review. Dates are outer advisory windows; exact closure hours vary.', url=INDEX))
    except Exception as exc:
        health.append(dict(name='SFMTA advisories', status='error', detail=f'Advisories unavailable ({type(exc).__name__})', url=INDEX))
    # Bound the stored records to the relevant month, rather than retaining venue history.
    end_date = (now.date() + timedelta(days=30)).isoformat()
    events = [e for e in events if (e.get('end') or e.get('start') or e['date'])[:10] >= now.date().isoformat() and e['date'] <= end_date]
    return dict(fetched_at=now.isoformat(), events=events, sources=health)
