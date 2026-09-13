"""Advance event notices; early departure plans are explicitly provisional."""
from datetime import datetime,timedelta
from .planner import at,clock

def advance_notice(result,config,now):
    if not config.get('advance_notices') or not result['events']:
        return result
    usual=at(now.date(),config['departure'])
    if result['display_priority']>=100 or now>=usual:
        return result
    result=dict(result)
    # Rotate all today's events, while preserving conflict-based urgency separately.
    event=result['events'][(now.hour*60+now.minute)%len(result['events'])]
    start=(clock(datetime.fromisoformat(event['start'])) if event.get('start')
           and event['kind'] not in ('convention','advisory') else 'Hours vary / check details')
    conflict=any(e['conflict'] for e in result['events'])
    leave=max(at(now.date(),config['earliest_departure']),
              usual-timedelta(minutes=config['event_warning_minutes'] if conflict else 0))
    if result.get('traffic_departure'):
        departure='Leave by '+clock(datetime.fromisoformat(result['traffic_departure']))
        basis='Google Maps estimate'
    elif result['stale'] or any(s['status']=='error' for s in result.get('sources',[])):
        departure='Check maps before leaving'
        basis='Event coverage incomplete'
    elif now>=at(now.date(),'15:15'):
        departure='Check maps before leaving'
        basis='Await next live traffic check'
    else:
        departure='Plan to leave '+clock(leave)
        basis='Provisional; traffic not checked'
    result.update(notice_event=event,advance_notice=True,notice_start=start,
                  notice_departure=departure,notice_basis=basis)
    if now<at(now.date(),'14:30'):result['display_priority']=10
    return result
