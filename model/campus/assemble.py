"""Losslessly assemble overlapping Blender render tiles. No scaling or AI generation."""
from PIL import Image
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
if '--stream' in sys.argv:
 # One in-memory image per view; the producer reuses one PNG tile on disk.
 import hashlib
 out=None;view=None
 for line in sys.stdin:
  command=json.loads(line)
  if command['action']=='begin':
   view=command;out=Image.new('RGBA',(view['width'],view['height']))
  elif command['action']=='tile':
   path=Path(command['file']);im=Image.open(path).convert('RGBA');a,b,c,d=command['render_bounds'];x0,y0,x1,y1=command['core'];assert im.size==(c-a,d-b),(im.size,(c-a,d-b));out.paste(im.crop((x0-a,y0-b,x1-a,y1-b)),(x0,y0));im.close()
  elif command['action']=='finish':
   destination=ROOT/(view['name']+'.png');out.save(destination,compress_level=9);out.close();out=None
  print(json.dumps({'ok':True,'action':command['action']}),flush=True)
 sys.exit(0)
manifest=json.loads(Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/taihu-full/tiles/manifest.json').read_text())
for v in manifest:
 destination=ROOT/(v['name']+'.png')
 if destination.exists() and destination.stat().st_mtime>=max(Path(t['file']).stat().st_mtime for t in v['tiles']):
  print('Already assembled',v['name']);continue
 out=Image.new('RGBA',(v['width'],v['height']))
 for t in v['tiles']:
  im=Image.open(t['file']).convert('RGBA');a,b,c,d=t['render_bounds'];x0,y0,x1,y1=t['core'];assert im.size==(c-a,d-b),(t['file'],im.size,(c-a,d-b));out.paste(im.crop((x0-a,y0-b,x1-a,y1-b)),(x0,y0))
 out.save(ROOT/(v['name']+'.png'),compress_level=9);print('Assembled',v['name'],out.size)
