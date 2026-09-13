"""Optional Google Routes enrichment. Only called with an explicitly configured key."""
from datetime import timedelta
import json
import math
import time
from .sources import request
from .planner import at, clock


def enrich(plan, config, now, key):
    if not plan['active']:
        return plan
    target = at(now.date(), config['deadline']) - timedelta(minutes=config['arrival_cushion_minutes'])
    deadline = at(now.date(), config['deadline'])
    earliest = max(now + timedelta(minutes=1), at(now.date(), config['earliest_departure']))
    # Candidate office-exit times at five-minute intervals; do not defer beyond the usual departure.
    last = max(earliest, at(now.date(), config['departure']))
    # Bound paid requests and latency: check now/earliest, midpoint, usual departure.
    # These are sampled options, not an exhaustive search for the latest safe time.
    candidates = sorted(set([earliest, earliest+(last-earliest)/2, last]))
    estimates = []
    started = time.monotonic()
    try:
        for leave in candidates:
            drive_start = leave + timedelta(minutes=config['office_exit_minutes'])
            payload = dict(origin={'address':config['origin']}, destination={'address':config['destination']},
                           travelMode='DRIVE', routingPreference='TRAFFIC_AWARE_OPTIMAL',
                           departureTime=drive_start.isoformat())
            body = json.loads(request('https://routes.googleapis.com/directions/v2:computeRoutes', payload,
                          {'X-Goog-Api-Key':key, 'X-Goog-FieldMask':'routes.duration'}))
            seconds = float(body['routes'][0]['duration'].removesuffix('s'))
            if not 0 < seconds < 14400:
                raise ValueError('Invalid driving duration')
            estimates.append((leave, drive_start + timedelta(seconds=seconds)))
        effective_now = now + timedelta(seconds=time.monotonic() - started)
        estimates = [x for x in estimates if x[0] > effective_now]
        if not estimates:
            raise TimeoutError('Departure estimates expired while fetching')
        safe = [x for x in estimates if x[1] <= target]
        if safe:
            leave, arrive = safe[-1]
            plan['action'] = f'Leave the office by {clock(leave)}. Estimated home arrival {clock(arrive)}; target {clock(target)}.'
            plan['title'] = 'Best checked traffic departure'
            plan['front_action'] = 'GO ' + leave.strftime('%I:%M').lstrip('0')
        else:
            leave, arrive = min(estimates, key=lambda x:x[1])
            plan['title'] = 'Arrival deadline at risk' if arrive > deadline else 'Arrival cushion at risk'
            plan['action'] = f'Best checked option: leave {clock(leave)}, estimated arrival {clock(arrive)}. Check maps now.'
            plan['level'] = 'warning'
            plan['front_action'] = 'CHECK MAPS'
        plan['mode'] = 'Google Maps estimate · up to three departure options · not a guarantee'
        plan['traffic_checked_at'] = now.isoformat()
        plan['traffic_departure'] = leave.isoformat()
        plan['prep_at'] = clock(leave-timedelta(minutes=config['heads_up_minutes']))
        if any(e['kind']=='advisory' for e in plan['events']):
            plan['action'] += ' Review the closure advisory; the route estimate may not reflect every restriction.'
        # Do not conceal source failures after adding traffic.
    except Exception as exc:
        plan['mode'] = f'Traffic unavailable ({type(exc).__name__}) · event-based precaution only'
    return plan
