"""Descriptive event details; scores are timestamped snapshots, never traffic inputs."""
from datetime import datetime
from .sources import TZ


def stamp(value):
    return datetime.fromisoformat(value).astimezone(TZ).strftime('%I:%M %p').lstrip('0')


def event_details(event, fetched_at, stale=False, show_scores=True):
    rows = []
    if event['kind'] == 'baseball':
        rows.append('First pitch ' + (stamp(event['start']) if event.get('start') else 'TBD'))
        rows.append(event.get('inning') or event.get('status', 'Status unavailable'))
        score = event.get('score')
        if show_scores and score and not stale:
            label = 'Final' if event.get('game_state') == 'Final' else 'Score snapshot'
            rows.append(f"{label}: {event.get('opponent', 'Opponent')} {score['away']} - Giants {score['home']}")
            rows.append('Score checked ' + stamp(fetched_at))
        elif show_scores and score:
            rows.append('Score hidden: update needed')
    else:
        rows.append(event.get('timing', 'Check event details'))
    return rows


def cause(event):
    if event['kind'] == 'advisory':
        return 'Road restrictions; check route'
    if event['kind'] == 'convention':
        return 'Convention crowds; timing unknown'
    if not event.get('start'):
        return 'Event time unconfirmed'
    return ('Possible departing crowds' if 'departures' in event.get('reason', '')
            else 'Possible arriving crowds')
