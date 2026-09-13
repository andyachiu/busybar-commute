"""Conservative event assessment; event timing is not a traffic forecast."""
from datetime import datetime, timedelta
from .sources import TZ


def at(day, time):
    return datetime.fromisoformat(day.isoformat() + 'T' + time).replace(tzinfo=TZ)


def clock(value):
    return value.strftime('%I:%M %p').lstrip('0')


def assess_event(event, day, departure, deadline, config):
    if event['date'] > day.isoformat() or (event.get('end') or event.get('start') or event['date'])[:10] < day.isoformat():
        return None
    e = dict(event)
    if event['kind'] == 'advisory':
        e['reason'] = 'SFMTA driving advisory. Affected streets include ' + ', '.join(event.get('streets', [])) + '. Check specific closure hours and consider an alternate route.'
        e['conflict'] = True
        e['timing'] = 'Closure hours vary; see advisory'
        return e
    if event['kind'] == 'convention':
        e['reason'] = 'Convention near downtown; daily crowd-release times and route impact are unverified.'
        e['conflict'] = True
        e['timing'] = 'Daily times unverified'
        return e
    if not event.get('start'):
        e.update(conflict=True, timing='Time TBD', reason='Event start time is unconfirmed; check traffic before departure.')
        return e
    start = datetime.fromisoformat(event['start'])
    e['timing'] = clock(start)
    arrival_start = start - timedelta(minutes=config['arrival_buffer_minutes'])
    if event.get('doors'):
        arrival_start = min(arrival_start, datetime.fromisoformat(event['doors']) - timedelta(minutes=30))
    inbound = (arrival_start, start + timedelta(minutes=30))
    ending = start + timedelta(minutes=config['game_duration_minutes'] if event['kind']=='baseball' else config.get('arena_duration_minutes', 180))
    outbound = (ending - timedelta(minutes=30), ending + timedelta(minutes=config['exit_buffer_minutes']))
    overlaps = lambda window: window[0] <= deadline and window[1] >= departure
    e['conflict'] = overlaps(inbound) or overlaps(outbound)
    e['reason'] = ('Possible event arrivals during your drive.' if overlaps(inbound) else
                   'Possible event departures during your drive; end time is estimated.' if overlaps(outbound) else
                   'No overlap with the configured event buffers; this does not establish clear roads.')
    return e


def plan(snapshot, config, now):
    now = now.astimezone(TZ)
    day = now.date()
    departure = at(day, config['departure'])
    deadline = at(day, config['deadline'])
    target = deadline - timedelta(minutes=config['arrival_cushion_minutes'])
    fetched = datetime.fromisoformat(snapshot['fetched_at'])
    if fetched.tzinfo is None:
        raise ValueError('Cache timestamp must include timezone')
    age = (now - fetched).total_seconds() / 60
    stale = age < -5 or age > config['cache_max_age_minutes']
    events = [e for row in snapshot['events'] if (e := assess_event(row, day, departure, deadline, config))]
    # A closure notice and the matching Moscone listing are one decision context.
    # Retain the event but link its related advisories, rather than double-counting it.
    for event in events:
        if event['kind'] == 'convention':
            words={w.lower() for w in event['title'].split() if len(w)>4 and not w.isdigit()}
            event['related_advisories']=[a['url'] for a in events if a['kind']=='advisory' and any(w in a['title'].lower() for w in words)]
    events.sort(key=lambda e: (not e['conflict'], e['kind']!='advisory', e.get('start') or '', e['id']))
    conflicts = [e for e in events if e['conflict']]
    missing = [s['name'] for s in snapshot['sources'] if s['status'] != 'ok']
    failed = [s['name'] for s in snapshot['sources'] if s['status'] == 'error']
    active = (day.weekday() in config['commute_weekdays']
              and at(day, config.get('monitor_start', '14:30')) <= now < deadline)
    suggestion = max(at(day, config['earliest_departure']), departure - timedelta(minutes=config['event_warning_minutes']))
    if not active:
        title, action, level = 'Outside commute hours', 'No departure alert scheduled. You can still review nearby events.', 'quiet'
    elif stale:
        title, action, level = 'Refresh event data', 'Stored schedules are stale or incorrectly dated. Check maps and event sources.', 'warning'
    elif failed:
        title, action, level = 'Some event sources are unavailable', 'Check maps and the failed sources before leaving. Available event notices are listed below.', 'warning'
    elif any(e['kind']=='advisory' for e in conflicts):
        title, level = 'Road restrictions may affect your route', 'warning'
        action = 'Review the affected streets and check an alternate route before leaving. An earlier departure may not avoid a closure.'
    elif conflicts:
        title, level = 'Events may affect your drive', 'warning'
        action = (f'Consider leaving at {clock(suggestion)} as an event-based precaution. Check live traffic first.'
                  if now < suggestion else 'Check live traffic now before leaving. The earlier precautionary departure time has passed.')
    else:
        title, action, level = 'No event overlap found', 'Check live traffic before your usual departure. Event coverage is incomplete.', 'neutral'
    front_action = ('OFF DUTY' if not active else 'CHECK DATA' if stale or failed else
                    'CHECK ROUTE' if any(e['kind']=='advisory' for e in conflicts) else
                    'TRY ' + suggestion.strftime('%I:%M').lstrip('0') if conflicts and now < suggestion else 'CHECK MAPS')
    return dict(title=title, action=action, level=level, events=events, sources=snapshot['sources'],
                front_action=front_action,
                stale=stale, missing=missing, active=active, rendered_at=now.isoformat(), fetched_at=snapshot['fetched_at'],
                show_scores=config.get('show_scores', True),
                departure=clock(departure), deadline=clock(deadline), target=clock(target),
                route='Office → Potrero Hill', mode='Event-based precaution · traffic not connected',
                prep_at=clock(max(at(day, config['earliest_departure']), suggestion - timedelta(minutes=config['heads_up_minutes']))),
                upcoming=sorted([e for e in snapshot['events'] if e['date'] > day.isoformat()], key=lambda e: (e['date'], e['id']))[:12])
