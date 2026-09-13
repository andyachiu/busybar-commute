"""Fail-closed request reservations; stores counters, never Google Maps content."""
import json
from .sources import TZ

MONTHLY_REQUEST_LIMIT = 400  # $4 at verified $10/1000 Pro pricing, before credits/tax.
SLOTS = {'15:15', '15:30', '15:45', '16:00', '16:15'}

def reservation(state, now, amount=3):
    now = now.astimezone(TZ)
    slot = now.strftime('%Y-%m-%dT%H:%M')
    if now.weekday() >= 5 or now.strftime('%H:%M') not in SLOTS:
        return None
    if not isinstance(state, dict) or type(state.get('used')) is not int or not isinstance(state.get('slots'), list):
        raise ValueError('Invalid traffic budget state')
    if state['used'] < 0 or slot in state['slots'] or state['used'] + amount > MONTHLY_REQUEST_LIMIT:
        return None
    return {'used': state['used'] + amount, 'slots': [*state['slots'], slot]}

def reserve(bucket, now):
    from google.api_core.exceptions import NotFound, PreconditionFailed
    now = now.astimezone(TZ)
    blob = bucket.blob('traffic-budget/'+now.strftime('%Y-%m')+'.json')
    try:
        blob.reload(timeout=10)
        generation = blob.generation
        state = json.loads(blob.download_as_text(if_generation_match=generation, timeout=10))
    except NotFound:
        # Missing current state must not silently reset spending after deletion.
        return False
    updated = reservation(state, now)
    if updated is None:
        return False
    try:
        blob.upload_from_string(json.dumps(updated), content_type='application/json',
                                if_generation_match=generation, timeout=10)
    except PreconditionFailed:
        return False
    return True
