"""Private Cloud Run endpoint. Cloud Run IAM authenticates Scheduler requests."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from .sources import TZ, refresh, request
from .planner import plan, at
from .device import payload
from .widgets import lunch_payload
from .traffic import enrich
from .icons import animation_for
from .notices import advance_notice
from .snapshot import publish as publish_native_snapshot


def priority(result, config, now):
    if result.get('traffic_departure'):
        checked = datetime.fromisoformat(result['traffic_checked_at'])
        leave = datetime.fromisoformat(result['traffic_departure'])
        if (result['active'] and 0 <= (now-checked).total_seconds() < 120
                and now >= leave-timedelta(minutes=config['heads_up_minutes'])):
            return config.get('urgent_priority', 100)
    """Escalate actionable advice near departure, not all afternoon."""
    has_conflict = any(e['conflict'] for e in result['events'])
    departure = at(now.date(), config['departure'])
    precaution = max(at(now.date(), config['earliest_departure']),
                     departure - timedelta(minutes=config['event_warning_minutes']))
    urgent = (result['active'] and has_conflict and not result['stale']
              and now >= precaution - timedelta(minutes=config['heads_up_minutes']))
    return config.get('urgent_priority', 100) if urgent else config.get('routine_priority', 50)


class Cache:
    def __init__(self):
        from google.cloud import storage
        self.bucket = storage.Client().bucket(os.environ['CACHE_BUCKET'])
        self.blob = self.bucket.blob('events.json')

    def reserve_traffic(self, now):
        from .traffic_budget import reserve
        return reserve(self.bucket, now)

    def read(self):
        from google.api_core.exceptions import NotFound
        try:
            return json.loads(self.blob.download_as_text(timeout=15))
        except NotFound:
            return None

    def write(self, snapshot):
        self.blob.upload_from_string(json.dumps(snapshot), content_type='application/json', timeout=15)

    def read_native_publish_state(self):
        from google.api_core.exceptions import NotFound
        blob = self.bucket.blob('native-publish.json')
        try:
            blob.reload(timeout=15)
            generation = blob.generation
            return json.loads(blob.download_as_text(timeout=15)), generation
        except NotFound:
            return {}, 0

    def write_native_publish_state(self, state, generation):
        self.bucket.blob('native-publish.json').upload_from_string(
            json.dumps(state), content_type='application/json', timeout=15,
            if_generation_match=generation)


def tick(config, cache, token, now=None, dry_run=False, traffic_key=None):
    simulated = now is not None
    now = (now or datetime.now(TZ)).astimezone(TZ)
    if ((config.get('advance_notices') and lunch_payload(now)) or now.weekday() not in config['commute_weekdays']
            or not at(now.date(), config.get('monitor_start', '14:30')) <= now < at(now.date(), config['deadline'])):
        animation_path = ('lunch-bowl-background.anim'
                          if config.get('lunch_animation_verified') is True else None)
        lunch = lunch_payload(now, animation_path)
        if lunch:
            if not dry_run:
                if not token:
                    raise ValueError('Missing token')
                try:
                    request('https://api.busy.app/busybar/display/draw', lunch,
                            headers={'Authorization': 'Bearer ' + token})
                except HTTPError as exc:
                    # Missing/unsupported assets fall back; priority/auth errors do not.
                    if not animation_path or exc.code not in (400, 404):
                        raise
                    exc.close()
                    fallback = lunch_payload(now if simulated else datetime.now(TZ))
                    if not fallback:
                        return {'status': 'outside_window'}
                    request('https://api.busy.app/busybar/display/draw', fallback,
                            headers={'Authorization': 'Bearer ' + token})
            return {'status': 'preview_only' if dry_run else 'updated',
                    'widget': 'lunch', 'priority': lunch['priority']}
        return {'status': 'outside_window'}
    snapshot = cache.read()
    age = None if snapshot is None else (now - datetime.fromisoformat(snapshot['fetched_at'])).total_seconds()
    if age is None or age < -300 or age >= 900:
        snapshot = refresh(now)
        cache.write(snapshot)
    native_status = 'disabled'
    if config.get('native_snapshot_enabled') is True and not dry_run:
        if not token:
            raise ValueError('Missing token')
        try:
            native_status = publish_native_snapshot(cache, token, snapshot, config, now)
        except Exception:
            # Local browsing is secondary; a failed cache upload must not suppress alerts.
            native_status = 'failed'
    # Refresh can take time; recheck the window and data age before drawing.
    current = now if simulated else datetime.now(TZ)
    result = plan(snapshot, config, current)
    if not result['active']:
        return {'status': 'outside_window'}
    if config.get('advance_notices') and current<at(current.date(),'14:30') and not result['events']:
        return {'status':'no_morning_events'}
    if config.get('traffic_enabled') is True and traffic_key and not dry_run:
        try:
            allowed = cache.reserve_traffic(current)
        except Exception:
            allowed = False
        if allowed:
            result = enrich(result, config, current, traffic_key)
        if 'traffic_checked_at' not in result:
            # Never replace a traffic-based early warning with a later event-only time.
            result['front_action'] = 'CHECK MAPS'
            result['action'] = ('Check Google Maps before leaving. Target home: '
                                + result['target'] + '. Live traffic checks every 15 minutes, 3:15-4:15 PM.')
        current = now if simulated else datetime.now(TZ)
        if current >= at(current.date(), config['deadline']):
            return {'status': 'outside_window'}
    result['display_priority'] = priority(result, config, current)
    result = advance_notice(result,config,current)
    animation = animation_for(result,config)
    if not dry_run:
        if not token:
            raise ValueError('Missing token')
        try:
            request('https://api.busy.app/busybar/display/draw', payload(result, animation_path=animation),
                    headers={'Authorization': 'Bearer ' + token})
        except HTTPError as exc:
            if not animation or exc.code not in (400, 404):
                raise
            exc.close()
            if not simulated and datetime.now(TZ) >= at(current.date(), config['deadline']):
                return {'status': 'outside_window'}
            request('https://api.busy.app/busybar/display/draw', payload(result),
                    headers={'Authorization': 'Bearer ' + token})
    return {'status': 'preview_only' if dry_run else 'updated', 'priority': result['display_priority'],
            'coverage_gaps': len(result['missing']), 'native_snapshot': native_status}


def app(environ, start_response):
    if environ.get('PATH_INFO') != '/tick' or environ.get('REQUEST_METHOD') != 'POST':
        start_response('404 Not Found', [('Content-Type', 'application/json')])
        return [b'{"status":"not_found"}']
    try:
        config = json.loads(Path(os.environ['COMMUTE_CONFIG_FILE']).read_text())
        dry_run = os.environ.get('DRY_RUN', 'true').lower() != 'false'
        token = '' if dry_run else Path(os.environ['BUSY_TOKEN_FILE']).read_text().strip()
        traffic_key = (Path(os.environ['TRAFFIC_KEY_FILE']).read_text().strip()
                       if config.get('traffic_enabled') is True and os.environ.get('TRAFFIC_KEY_FILE') else None)
        result = tick(config, Cache(), token, dry_run=dry_run, traffic_key=traffic_key)
        print(json.dumps(result), flush=True)
        status = '200 OK'
    except Exception as exc:
        # Exceptions from upstream may contain credentials or addresses: log type only.
        print(json.dumps({'status': 'error', 'type': type(exc).__name__}), flush=True)
        status, result = '503 Service Unavailable', {'status': 'update_failed'}
    start_response(status, [('Content-Type', 'application/json')])
    return [json.dumps(result).encode()]
