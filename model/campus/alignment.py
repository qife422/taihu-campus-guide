"""Render source-overlay audit panels; this is evidence of tracing, not ground accuracy."""
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,math
ROOT=Path(__file__).resolve().parent;D=json.loads((ROOT/'layout.json').read_text());ims={}
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',11)
for src in ['satellite','north-extension']:
 im=Image.open(ROOT/'references'/(src+'.jpg')).convert('RGB')
 if src=='satellite':im=im.resize((1152,1920))
 dr=ImageDraw.Draw(im)
 for r in D['buildings']:
  if r['source']!=src:continue
  ps=[tuple(x) for x in r['outline']];dr.line(ps+[ps[0]],fill='#ffdc58',width=1);dr.text(ps[0],r['id'],font=font,fill='white',stroke_width=1,stroke_fill='#142827')
 for r in D['tracks']:
  if r.get('source','satellite')!=src:continue
  rad=r['wide']/2;half=(r['long']-r['wide'])/2;ang=math.radians(r['angle']);c=r['center'];ps=[]
  for cy,start in [(half,0),(-half,math.pi)]:
   for i in range(49):
    a=start+i*math.pi/48;x=rad*math.cos(a);y=cy+rad*math.sin(a);ps.append((c[0]+x*math.cos(ang)+y*math.sin(ang),c[1]+x*math.sin(ang)-y*math.cos(ang)))
  dr.line(ps+[ps[0]],fill='#83eaff',width=2)
 ims[src]=im
sheet=Image.new('RGB',(2400,1700),'#f4f4ed');dr=ImageDraw.Draw(sheet);large=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',27)
panels=[('NORTH CAMPUS | ROOF TRACING','satellite',(470,175,910,595)),('CENTRAL CAMPUS | ROOF TRACING','satellite',(350,850,755,1305)),('SOUTH CAMPUS | CORRECTED OUTLINES','satellite',(240,1640,615,1850)),('NORTHERN EXTENSION | SEPARATE EXPORT','north-extension',(280,0,950,830))]
for i,(title,src,box) in enumerate(panels):
 x=(i%2)*1200;y=(i//2)*820;dr.text((x+26,y+22),title,font=large,fill='#18342e');c=ims[src].crop(box);c.thumbnail((1148,735));sheet.paste(c,(x+26,y+68))
dr.text((26,1650),'Yellow: interpreted roof outlines | Cyan: fitted track extents | Source: Esri World Imagery | Heights are estimates',font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',22),fill='#18342e');sheet.save(ROOT/'alignment.png')
print('Saved alignment.png')
