from pathlib import Path
import struct, sys, json, io, mmap, datetime, hashlib
import numpy as np
from PIL import Image


class Reader:
 def __init__(self,b,pos=0):self.b,self.pos=b,pos
 def read(self,n):
  assert 0<=n<=len(self.b)-self.pos
  result=self.b[self.pos:self.pos+n];self.pos+=n;return result
 def num(self,fmt):return struct.unpack('<'+fmt,self.read(struct.calcsize(fmt)))[0]

def cmpimg(r,legacy=False):
 n,w,h,used=struct.unpack('<4H',r.read(8));flags=r.num('B')
 assert n==w*h and w<256 and h<256 and used<=n
 assert flags&8
 if flags&4:r.read(8)
 mask=r.read((n+7)//8) if flags&16 else b''
 assert sum(int(x).bit_count() for x in mask)==used
 assert flags&32
 # Pre-VRSN depots omit the art pointer and channel sizes for empty images.
 if legacy and not n:
  if hasattr(r,'image_positions'):r.image_positions.append(None)
  return dict(n=n,w=w,h=h,used=used,flags=flags,mask=mask.hex(),offset=-1,sizes=(0,0,0))
 if hasattr(r,'image_positions'):r.image_positions.append(r.pos)
 offset=r.num('i');sizes=struct.unpack('<3i',r.read(12))
 return dict(n=n,w=w,h=h,used=used,flags=flags,mask=mask.hex(),offset=offset,sizes=sizes)

def frame(r,legacy=False):
 origin=struct.unpack('<2i',r.read(8));art_bank=r.num('B');markers=r.num('B');r.read(markers*12)
 flags=r.num('B');images={}
 for i in range(8):
  if flags&(1<<i):images[i]=cmpimg(r,legacy)
 offsets=struct.unpack('<10i',r.read(40))
 for _ in range(3):r.read(r.num('H')*16)
 return dict(origin=origin,art_bank=art_bank,images=images,offsets=offsets)

def parse_frames_data(name,b,art_size,with_locations=False):
 legacy=b[4:8]!=b'VRSN'
 if not legacy:
  assert struct.unpack_from('<I',b,8)[0] in (3,9), 'Unsupported FOIT version'
 for i in range(11,min(len(b)-30,300000)):
  n,w,h,used,flags=struct.unpack_from('<4HB',b,i)
  empty=legacy and n==w==h==used==0 and flags&0x38==0x28
  if not empty and not (w and h and n==w*h and used and used<=n and w<150 and h<150 and flags&0x38==0x38):continue
  k=i+9+(8 if flags&4 else 0)+(n+7)//8
  if k+16>len(b):continue
  if not empty:
   off,a,c,d=struct.unpack_from('<4i',b,k)
   if off<0 or not (0<a and 0<c and 0<d and off+a+c+d<=art_size):continue
  start=i-11
  if b[start+9]!=0 or b[start+10]&1==0 or b[start-5]!=1:continue
  count=struct.unpack_from('<I',b,start-4)[0]
  if not 1<=count<20000:continue
  try:
   r=Reader(b,start);r.image_positions=[];frames=[frame(r,legacy) for _ in range(count)]
   locations=dict(zip(((j,k) for j,f in enumerate(frames) for k in f['images']),r.image_positions))
   return (frames,locations) if with_locations else frames
  except (AssertionError,struct.error):pass
 raise ValueError(f'No valid frame section for {name}')

def rle(b,size):
 out=bytearray();r=Reader(b)
 while len(out)<size:
  code=r.num('B');repeat=bool(code&128);n=code&127
  n=n+1 if n<125 else max(1,int.from_bytes(r.read(n-124),'big'))
  assert len(out)+n<=size
  out.extend(r.read(1)*n if repeat else r.read(n))
 assert r.pos==len(b),(r.pos,len(b),size)
 return np.frombuffer(out,dtype=np.uint8).copy()

def decode_image(meta,art,selected_channels=(0,1,2)):
 count=meta['used'];offset=meta['offset'];sizes=meta['sizes']
 assert offset>=0 and all(s>=0 for s in sizes)
 channels=[]
 for ch,size in enumerate(sizes):
  if ch not in selected_channels:
   channels.append(np.zeros((count,16,16),dtype=np.uint8));offset+=size;continue
  raw=rle(art[offset:offset+size],count*256).reshape(16,count*16)
  offset+=size
  if ch==0:
   for y in range(2,15,2):raw[y]=raw[y]+raw[y-2]
   raw[15]=raw[15]+raw[14]
   for y in range(1,15,2):
    a=raw[y-1].astype(np.uint16);c=raw[y+1].astype(np.uint16)
    raw[y]=(((a>>4)+(c>>4))//2<<4)|(((a&15)+(c&15))//2)
  if ch==1 and meta['flags']&64:
   for y in range(1,15,2):
    raw[y]=(raw[y]&224)|(((raw[y-1]&31).astype(np.uint16)+(raw[y+1]&31))//2)
  channels.append(raw.reshape(16,count,16).transpose(1,0,2))
 tiles=np.stack(channels,axis=-1)
 canvas=np.zeros((meta['h']*16,meta['w']*16,3),dtype=np.uint8)
 mask=bytes.fromhex(meta['mask']);j=0
 for i in range(meta['n']):
  if mask[i//8]&(1<<(i%8)):
   y,x=divmod(i,meta['w']);canvas[y*16:y*16+16,x*16:x*16+16]=tiles[j];j+=1
 assert j==count
 return canvas

def legacy_palette(data):
 """Expand embedded gradient ranges into a table indexed by stored art bytes."""
 candidates=[]
 for trailer in (8,10):
  try:
   r=Reader(data,struct.unpack_from('<I',data)[0])
   r.read(r.num('B'));r.read(4)
   assert r.num('B')==1
   count=r.num('H');assert 1<=count<=256
   default=None
   for _ in range(count):
    size=r.num('H');assert 1<=size<=256
    colors=np.frombuffer(r.read(size*4),dtype=np.uint8).reshape(size,4)[:,[2,1,0,3]].astype(float)
    if default is None:default=colors
    # Two auxiliary colors; later depots add a two-byte palette field.
    r.read(trailer)
   groups=r.num('B');assert groups>0
   palette=np.zeros((len(default),16,4),float);previous=-1
   for _ in range(groups):
    low=r.num('B');high=r.num('B');r.read(2);label=r.read(r.num('B'))
    assert low==previous+1 and low<=high<len(default)
    assert label and all(32<=value<127 for value in label)
    points=default[low:high+1][::-1]
    x=np.linspace(0,len(points)-1,16);left=x.astype(int);right=np.minimum(left+1,len(points)-1);t=(x-left)[:,None]
    palette[low:high+1]=np.floor(points[left]*(1-t)+points[right]*t)
    previous=high
   assert previous==len(default)-1
   candidates.append(palette)
  except (AssertionError,struct.error,IndexError,ValueError):pass
 if len(candidates)!=1:raise ValueError('Cannot read legacy character palette gradients. Export refused to avoid incorrect colors.')
 return candidates[0]


def load_palette(name,data,sprites):
 if data[4:8]!=b'VRSN':return legacy_palette(data)
 with Image.open(io.BytesIO(sprites.read(f'sprites/{name}_1p.dds'))) as image:
  return np.asarray(image.convert('RGBA'),dtype=float)


def colorize(raw,palette):
 idx=raw[:,:,2].astype(int)
 idx=np.minimum(idx,len(palette)-1) # Palette sampler clamps at the texture edge.
 g=raw[:,:,1].astype(float)
 # Render the palette gradient and outline with neutral stage lighting.
 intensity=(g%32)/31
 x=intensity*15
 lo=np.floor(x).astype(int);hi=np.minimum(lo+1,15);t=(x-lo)[:,:,None]
 color=palette[idx,lo]*(1-t)+palette[idx,hi]*t
 black=(g//32)/7
 color[:,:,:3]*=(1-black[:,:,None])
 color[:,:,3]=np.maximum((color[:,:,3]%128)*2,black*255)
 return Image.fromarray(np.clip(np.rint(color),0,255).astype(np.uint8))

class GFS:
 def __init__(self,path):
  self.file=Path(path).open('rb');self.data=mmap.mmap(self.file.fileno(),0,access=mmap.ACCESS_READ)
  self.entries={};pos=0
  def number(fmt):
   nonlocal pos
   size=struct.calcsize(fmt);v=struct.unpack_from('>'+fmt,self.data,pos)[0];pos+=size;return v
  def string():
   nonlocal pos
   size=number('Q');v=self.data[pos:pos+size].decode().rstrip('\0');pos+=size;return v
  try:
   offset=number('I');assert string()=='Reverge Package File';string();count=number('Q')
   assert count<1000000
   for _ in range(count):
    name=string();size=number('Q');align=number('I')
    if align>1:offset=(offset+align-1)//align*align
    assert offset+size<=len(self.data)
    self.entries[name]=(offset,size);offset+=size
   # Older depots use temp paths. Alias their entries without touching bytes.
   for name,location in list(self.entries.items()):
    canonical=None
    if name.startswith('temp/true_color_sprites/'):
     canonical='sprites/'+name.rsplit('/',1)[-1]
    elif name.startswith('temp/') and '/' not in name[5:] and name.endswith(('.art','.art-pt','.foit')):
     canonical='characters/'+name[5:]
    if canonical:
     canonical=canonical.replace('/boss_marie.','/bossmarie.').replace('/boss_marie_','/bossmarie_')
     self.entries.setdefault(canonical,location)
  except Exception:
   self.close();raise ValueError(f'Invalid GFS archive: {path}')
 def read(self,name):
  offset,size=self.entries[name];return self.data[offset:offset+size]
 def close(self):
  self.data.close();self.file.close()
 def __enter__(self):return self
 def __exit__(self,*args):self.close()

NAMES={'annie':'Annie','beowulf':'Beowulf','bigband':'Big Band','blackdahlia':'Black Dahlia','bossmarie':'Marie (boss)','cerebella':'Cerebella','double':'Double','eliza':'Eliza','filia':'Filia','fukua':'Fukua','marie':'Marie','msfortune':'Ms. Fortune','painwheel':'Painwheel','parasoul':'Parasoul','peacock':'Peacock','robofortune':'Robo-Fortune','squigly':'Squigly','umbrella':'Umbrella','valentine':'Valentine'}

def data_folder(game):
 p=Path(game).expanduser().resolve()
 if (p/'data01').is_dir():p=p/'data01'
 for name in ['characters-art.gfs','characters-art-pt.gfs','characters-foits.gfs','sprites.gfs']:
  if not (p/name).is_file():raise ValueError(f'Cannot find {name}. Choose the installed Skullgirls folder or its data01 folder.')
 return p

def available_characters(game):
 p=data_folder(game)
 with GFS(p/'characters-art.gfs') as art,GFS(p/'sprites.gfs') as sprites:
  return [name for name in NAMES if f'characters/{name}.art' in art.entries and f'sprites/{name}_1p.dds' in sprites.entries]

class Cancelled(Exception):pass

def extract(game,output,characters,progress=lambda *args:None,cancel=None,save_layers=False,limit=None):
 source=data_folder(game);target=Path(output).expanduser().resolve()
 if target==source or target.is_relative_to(source):raise ValueError('Choose an output folder outside the game data01 folder.')
 assert characters and all(n in NAMES for n in characters), 'Select at least one character'
 target.mkdir(parents=True,exist_ok=True)
 stamp=datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
 run=target/f'Skullgirls Sprites {stamp}'
 suffix=1
 while run.exists():run=target/f'Skullgirls Sprites {stamp} ({suffix})';suffix+=1
 run.mkdir()
 manifest={'source':str(source),'palette':'1p (default)','lighting':'neutral','status':'running','characters':{},'errors':[]}
 total=done=0
 try:
  with GFS(source/'characters-art.gfs') as art_archive,GFS(source/'characters-art-pt.gfs') as pt_archive,GFS(source/'characters-foits.gfs') as foit_archive,GFS(source/'sprites.gfs') as sprites:
   parsed={}
   for name in characters:
    if cancel and cancel.is_set():raise Cancelled()
    progress(0,0,f'Reading {NAMES[name]} frame metadata…')
    try:parsed[name]=parse_frames_data(name,foit_archive.read(f'characters/{name}.foit'),art_archive.entries[f'characters/{name}.art'][1])
    except Exception as exc:manifest['errors'].append({'character':name,'error':str(exc) or repr(exc)})
   total=sum(min(len(f),limit) if limit is not None else len(f) for f in parsed.values())
   for name,frames in parsed.items():
    art_banks={5:art_archive.read(f'characters/{name}.art'),4:pt_archive.read(f'characters/{name}.art-pt')}
    pal=load_palette(name,foit_archive.read(f'characters/{name}.foit'),sprites)
    folder=run/NAMES[name];folder.mkdir();records=[]
    selected=frames[:limit] if limit is not None else frames
    for i,f in enumerate(selected):
     if cancel and cancel.is_set():raise Cancelled()
     record={'frame':i,'origin':f['origin'],'art_bank':f['art_bank'],'layers':[]}
     try:
      result=None
      for layer in [0,1]:
       m=f['images'].get(layer)
       if not m or m['offset']<0:continue
       im=colorize(decode_image(m,art_banks[f['art_bank']]),pal)
       record['layers'].append(layer)
       if save_layers and 1 in f['images']:
        layerdir=folder/'Layers';layerdir.mkdir(exist_ok=True)
        im.save(layerdir/f'frame_{i:04d}_layer_{layer}.png',compress_level=3)
       if result is None:result=im
       else:
        assert result.size==im.size,'Layer sizes differ'
        result=Image.alpha_composite(result,im)
      if result is None:record['status']='empty'
      else:
       filename=f'frame_{i:04d}.png';result.save(folder/filename,compress_level=3)
       record.update(file=filename,size=result.size,status='ok')
     except Exception as exc:
      record.update(status='error',error=str(exc) or repr(exc));manifest['errors'].append({'character':name,'frame':i,'error':record['error']})
     records.append(record);done+=1
     if i%10==0 or i==len(selected)-1:progress(done,total,f'{NAMES[name]} · frame {i+1:,} of {len(selected):,}')
    (folder/'frames.json').write_text(json.dumps(records,indent=2))
    manifest['characters'][name]={'frames':len(records),'exported':sum(r['status']=='ok' for r in records),'failed':sum(r['status']=='error' for r in records)}
   manifest['status']='complete' if not manifest['errors'] else 'complete_with_errors'
 except Cancelled:
  manifest['status']='cancelled'
 finally:
  (run/'manifest.json').write_text(json.dumps(manifest,indent=2))
  (run/'README.txt').write_text('Character sprites decoded directly from the installed Skullgirls GFS archives.\nPNG frames use each character\'s default palette and neutral lighting.\nFrames are numbered in the game\'s internal order. frames.json preserves origins and art bank references.\nStage lighting and animated palette effects are not baked into these images.\nOriginal game files were opened read-only. Each run uses a new folder.\nSee manifest.json for export counts, cancellation status, and any failed frames.\n')
 return run,manifest

if __name__=='__main__':
 raise SystemExit('Launch the desktop app with python app.py.')
