"""Select icons without changing event assessment or alert priority."""
def event_icon(event):
    if not event:
        return 'car'
    kind=event['kind']
    if kind=='baseball':return 'baseball'
    if kind=='advisory':return 'detour'
    if kind=='convention':return 'convention'
    if kind=='arena':
        if event.get('event_type')=='basketball':return 'basketball'
        # Compatibility with cached events fetched before event_type was added.
        if any(team in event.get('title','').lower() for team in ('warriors','valkyries')):
            return 'basketball'
        return 'event'
    return 'event'

def animation_for(result,config):
    event=result.get('notice_event') or next((e for e in result['events'] if e['conflict']),None)
    icon=event_icon(event)
    enabled=config.get('event_icons_verified',[])
    if icon in enabled or (icon=='baseball' and config.get('baseball_animation_verified') is True):
        return icon+'-background.anim'
    return None
