"""Build text-free native backgrounds offline. Never contacts BUSY Bar.
Usage: python3 build_assets.py /absolute/path/to/busyshow-0.1.0
"""
from pathlib import Path
from PIL import Image, ImageDraw
import hashlib, json, math, struct, subprocess, sys
ROOT=Path(__file__).resolve().parent

def render(kind,t):
 im=Image.new('RGB',(72,16));d=ImageDraw.Draw(im)
 if kind=='baseball':
  d.ellipse((2,2,13,13),fill=(225,221,203))
  shift=round(math.sin(t*2*math.pi/16))
  for y in (4,7,10):
   d.line((5+shift,y,6+shift,y+1),fill=(190,50,36));d.line((10+shift,y,9+shift,y+1),fill=(190,50,36))
 elif kind=='basketball':
  y=2-round(abs(math.sin(t*math.pi/16))*2)
  d.ellipse((2,y,13,y+11),fill=(245,146,38))
  d.line((7,y,7,y+11),fill=(103,49,20))
  d.line((2,y+5,13,y+5),fill=(103,49,20))
  d.arc((0,y+1,6,y+10),270,90,fill=(103,49,20))
  d.arc((9,y+1,15,y+10),90,270,fill=(103,49,20))
  d.line((4,15,11,15),fill=(65,50,25))
 elif kind=='event':
  d.rounded_rectangle((2,3,13,12),radius=2,fill=(180,134,242))
  d.rectangle((1,7,3,8),fill=(0,0,0));d.rectangle((12,7,14,8),fill=(0,0,0))
  for y in (4,6,8,10):d.point((10,y),fill=(85,51,130))
  if t%16<8:d.line((5,0,5,2),fill=(245,220,255))
  else:d.line((14,1,15,2),fill=(245,220,255))
 elif kind=='convention':
  d.rectangle((2,4,13,14),fill=(71,162,198))
  d.rectangle((4,1,11,3),fill=(123,202,221))
  for x in (4,7,10):
   for y in (6,9):d.rectangle((x,y,x+1,y+1),fill=(237,226,145) if (t//4+x+y)%3 else (30,76,99))
  d.rectangle((7,12,9,14),fill=(20,51,67))
 elif kind=='car':
  col=(255,89,61)
  d.rectangle((2,6,12,10),fill=col);d.polygon([(4,6),(6,3),(10,3),(12,6)],fill=col)
  d.line((6,5,9,5),fill=(30,20,15));d.point((4,11),fill=(200,200,200));d.point((11,11),fill=(200,200,200))
  d.point((t%14,14),fill=col)
 elif kind=='detour':
  col=(150,178,255)
  d.line((3,13,3,8,11,8,11,2),fill=col,width=2);d.polygon([(8,4),(11,1),(14,4)],fill=col)
  route=[(3,13),(3,11),(3,9),(5,8),(7,8),(9,8),(11,8),(11,6),(11,4)]
  d.point(route[t%len(route)],fill=(245,245,255))
 elif kind=='lunch-bowl':
  d.ellipse((2,8,14,11),fill=(255,211,128))
  d.polygon([(2,10),(14,10),(11,14),(5,14)],fill=(231,145,62))
  d.line((5,15,11,15),fill=(255,211,128))
  # Three gently rising steam wisps, confined to the icon column.
  for x,phase in ((4,0),(8,4),(12,8)):
   step=(t+phase)%16
   y=7-step//3
   tint=220-step*7
   shift=round(math.sin((t+phase)*math.pi/8))
   d.line((x+shift,y,x+shift-1,y-2),fill=(tint,tint,tint))
 assert not im.crop((16,0,72,16)).getbbox()
 return im

def inspect(path):
 b=path.read_bytes()
 assert b[:8]==b'bicycle0'
 assert tuple(b[9:12])==(72,16,0) # BGR888
 fps=b[12];assert fps>0
 section_bytes,frame_bytes,sections,records,ticks=struct.unpack_from('<IIIII',b,16)
 assert sections==1 and 36+section_bytes+frame_bytes==len(b)
 start,end,offset=struct.unpack_from('<III',b,36)
 assert (start,end,offset)==(0,ticks-1,36+section_bytes)
 assert b[49:36+section_bytes]==b'default\0'
 pos=offset;durations=0
 for _ in range(records):
  encoding,duration,length=struct.unpack_from('<BBH',b,pos)
  assert encoding in (0,1) and duration>0
  pos+=4+length;assert pos<=len(b);durations+=duration
 assert pos==len(b) and durations==ticks
 return {'file':path.name,'width':72,'height':16,'format':'bicycle0/BGR888','fps':fps,'encoded_frames':records,'display_frames':ticks,'duration_seconds':round(ticks/fps,3),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}

if __name__=='__main__':
 tool=Path(sys.argv[1]).resolve()
 version=subprocess.check_output([str(tool),'--version'],text=True).strip()
 assert version=='busyshow 0.1.0',version
 manifest={'converter':version,'hardware_verified':False,'assets':[]}
 for kind in ('baseball','basketball','event','convention','car','detour','lunch-bowl'):
  frames=[render(kind,t) for t in range(32)]
  gif=ROOT/(kind+'-background.gif')
  # GIF uses 10ms units; 125ms truncates. Use exact 100ms delays (10fps).
  frames[0].save(gif,save_all=True,append_images=frames[1:],duration=100,loop=0,disposal=2)
  frames[0].save(ROOT/(kind+'-background.png'))
  native=gif.with_suffix('.anim')
  subprocess.run([str(tool),'convert',str(gif),'--screen','front','--output',str(native)],check=True)
  entry=inspect(native);entry['source_gif']=gif.name
  manifest['assets'].append(entry)
 (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(manifest,indent=2))
