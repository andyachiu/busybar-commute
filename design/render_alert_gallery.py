"""Offline previews from production display payloads; no network/device access."""
from pathlib import Path
from datetime import datetime
import json
from PIL import Image, ImageDraw, ImageFont
from commutebar.device import payload
from commutebar.widgets import lunch_payload
from commutebar.sources import TZ
from commutebar.icons import event_icon
from commutebar.notices import advance_notice
import sys

OUT=Path(__file__).parent/'alert-gallery'
OUT.mkdir(exist_ok=True)
FONT=ImageFont.load_default(size=8)
LABEL=ImageFont.load_default(size=18)
SMALL=ImageFont.load_default(size=13)
now=datetime(2026,9,14,15,45,tzinfo=TZ)
base=dict(level='warning',front_action='GO 4:00',events=[],target='4:50 PM',
          action='Leave the office by 4:00 PM. Estimated home arrival 4:35 PM; target 4:50 PM.',
          fetched_at=now.isoformat(),stale=False,traffic_checked_at=now.isoformat(),display_priority=100)
game=dict(kind='baseball',conflict=True,title='Giants vs Dodgers',start=now.replace(hour=13,minute=5).isoformat(),
          game_state='Live',status='In Progress',opponent='Dodgers',score=dict(away=2,home=3),inning='Top 7',
          reason='Possible event departures during your drive; end time is estimated.')
cases=[]
def add(slug,title,description,p,asset=None):
    icons={'warriors':'basketball','traffic':'car','late':'car','closure':'detour',
           'convention':'convention','between':'car','stale':'car','concert':'event'}
    if slug in icons:
        icon=icons[slug];asset=icon+'-background.gif'
        for e in p['elements']:
            if e['display']=='front':e.update(x=18,width=53)
        p['elements'].insert(0,dict(id='event-icon',type='animation',path=icon+'-background.anim',
                                 loop=True,display='front',x=0,y=0,timeout=120))
    cases.append((slug,title,description,p,asset))
add('giants','Giants game + departure time','Simulated live game, score and traffic estimate.',
    payload({**base,'events':[game]},animation_path='baseball-background.anim'),'baseball-background.gif')
add('traffic','Traffic-based departure','No event overlap required: traffic alone can shift your departure.',payload(base))
add('warriors','Warriors game at Chase Center','A bouncing basketball beside the scrolling matchup. Sample game and estimate.',
    payload({**base,'events':[dict(kind='arena',conflict=True,title='Warriors vs Lakers',
        venue='Chase Center',status='Published schedule',timing='7:00 PM',
        start=now.replace(hour=19,minute=0).isoformat(),reason='Possible event arrivals during your drive.')]}))
add('late','Arrival deadline at risk','Traffic estimate threatens the 5 PM deadline.',
    payload({**base,'front_action':'CHECK MAPS','action':'Best checked option: leave 4:16 PM, estimated arrival 5:08 PM. Check maps now.'}))
add('closure','Street closure / driving advisory','A moving route marker highlights the detour arrow.',
    payload({**{k:v for k,v in base.items() if k!='traffic_checked_at'},'front_action':'CHECK MAPS','events':[dict(kind='advisory',conflict=True,title='SFMTA: downtown street restrictions',status='Published advisory',streets=['3rd Street'],reason='Check closure hours.')],
             'action':'Check Google Maps before leaving. Target home: 4:50 PM. Live traffic checks every 15 minutes, 3:15-4:15 PM.'}))
add('convention','Downtown convention or arena event','Event title scrolls on the front; details remain on the rear.',
    payload({**base,'events':[dict(kind='convention',conflict=True,title='Moscone convention',status='Daily times unverified',start=now.replace(hour=9).isoformat(),reason='Crowds near downtown.')]}))
fallback={k:v for k,v in base.items() if k!='traffic_checked_at'}
add('between','Between traffic checks','Shown between quarter-hour checks, or when traffic is unavailable.',
    payload({**fallback,'front_action':'CHECK MAPS','action':'Check Google Maps before leaving. Target home: 4:50 PM. Live traffic checks every 15 minutes, 3:15-4:15 PM.'}))
add('stale','Stale or incomplete event data','Available event context remains; no assurance that roads are clear.',
    payload({**fallback,'front_action':'CHECK MAPS','stale':True,'action':'Check Google Maps before leaving. Target home: 4:50 PM. Live traffic checks every 15 minutes, 3:15-4:15 PM.'}))
add('lunch','Lunch reminder','The enabled steaming-bowl animation, with the message on both screens.',
    lunch_payload(now.replace(hour=11,minute=30),'lunch-bowl-background.anim'),'lunch-bowl-background.gif')
add('concert','Concert or other arena event','A sparkling ticket for arena events; sample event and estimate.',
    payload({**base,'events':[dict(kind='arena',conflict=True,title='Chase Center concert',
        timing='7:30 PM',start=now.replace(hour=19,minute=30).isoformat(),reason='Possible event arrivals during your drive.')]}))

morning=now.replace(hour=9,minute=0)
notice_config=dict(advance_notices=True,departure='16:15',earliest_departure='15:15',event_warning_minutes=15)
for slug,title,event,icon in [('advance-giants','Morning heads-up: Giants',
    {**game,'start':now.replace(hour=18,minute=45).isoformat()},'baseball'),
    ('advance-warriors','Morning heads-up: Warriors',dict(kind='arena',conflict=True,title='Warriors vs Lakers',
      venue='Chase Center',start=now.replace(hour=19).isoformat(),timing='7:00 PM'),'basketball')]:
    r={k:v for k,v in base.items() if k!='traffic_checked_at'}
    r.update(events=[event],missing=[],display_priority=50,fetched_at=morning.isoformat())
    r=advance_notice(r,notice_config,morning)
    add(slug,title,'Sample event day: start time and provisional office departure before the urgent alert.',
        payload(r,animation_path=icon+'-background.anim'),icon+'-background.gif')
if len(sys.argv)>1:
    cases=[c for c in cases if c[0] in sys.argv[1:]]

def render(p,display,t,asset):
    size=(72,16) if display=='front' else (160,80)
    im=Image.new('RGB',size)
    if display=='front' and asset:
        src=Image.open(Path(__file__).parent/'assets'/asset)
        src.seek(int(t*10)%src.n_frames);im.paste(src.convert('RGB'),(0,0))
    for e in p['elements']:
        if e['display']!=display or e['type']!='text':continue
        color=tuple(bytes.fromhex(e['color'][1:7])) if display=='front' else (235,235,235)
        width=e['width'];s=e['text'];length=ImageDraw.Draw(im).textlength(s,font=FONT)
        offset=0 if length<=width else max(0,int((t-1)*30))%int(length+20)
        tile=Image.new('RGB',(width,8));ImageDraw.Draw(tile).text((-offset,-1),s,font=FONT,fill=color)
        im.paste(tile,(e['x'],e['y']))
    return im

sheet=Image.new('RGB',(1000,len(cases)*365+75),'#10151c')
ImageDraw.Draw(sheet).text((20,15),'BUSY BAR / ALL ALERT PREVIEWS',font=LABEL,fill='white')
ImageDraw.Draw(sheet).text((20,43),'SAMPLE DATA ONLY. Actual payloads; approximate font, brightness and scrolling. No device changes.',font=SMALL,fill='#aab6c5')
for i,(slug,title,desc,p,asset) in enumerate(cases):
    frames=[]
    for n in range(80):
        card=Image.new('RGB',(1000,355),'#17202b');d=ImageDraw.Draw(card)
        d.text((20,12),title,font=LABEL,fill='white')
        d.text((20,40),desc,font=SMALL,fill='#bac5d3')
        d.text((20,76),'FRONT - 72 x 16',font=SMALL,fill='#94a5b7')
        d.text((480,76),'REAR - 160 x 80',font=SMALL,fill='#94a5b7')
        card.paste(render(p,'front',n/10,asset).resize((432,96),Image.Resampling.NEAREST),(20,103))
        card.paste(render(p,'back',n/10,None).resize((480,240),Image.Resampling.NEAREST),(480,103))
        frames.append(card)
    frames[0].save(OUT/(slug+'.png'))
    frames[0].save(OUT/(slug+'.gif'),save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=False)
    sheet.paste(frames[0],(0,75+i*365))
    (OUT/(slug+'.json')).write_text(json.dumps(p,indent=2))
sheet.save(OUT/'all-alerts.png')
print('Rendered',len(cases),'paired front/rear previews:',OUT.resolve())
