"""Synchronize the separate character-select idle atlas with prepared art."""
import struct
import numpy as np
from PIL import Image
from decoder import Reader, GFS, decode_image, colorize, load_palette, parse_frames_data

EMPTY = 0xf81f


def unpack(packed):
 raw=np.zeros((*packed.shape,3),np.uint8)
 raw[:,:,2]=(packed>>5)&63
 raw[:,:,1]=(packed&31)|(np.rint((31-(packed>>11))/31*7).astype(np.uint8)<<5)
 return raw


def pack(raw):
 g=raw[:,:,1].astype(np.uint16);idx=raw[:,:,2].astype(np.uint16)
 if idx.max(initial=0)>63:raise ValueError('Character-select material index exceeds RGB565 storage.')
 return (np.rint((1-(g>>5)/7)*31).astype(np.uint16)<<11)|(idx<<5)|(g&31)


def read_preview(sprite,dds):
 r=Reader(sprite)
 def q():return struct.unpack('>Q',r.read(8))[0]
 def text():return r.read(q())
 if text()!=b'2.0':raise ValueError('Unsupported character-select sprite version.')
 text();r.read(4)
 if text()!=b'unigned char tile_x, tile_y, tile_u, tile_v;':raise ValueError('Unsupported character-select tile layout.')
 stride=q();count_pos=r.pos;nt=q();nf=q();na=q();tw=q();th=q();header_end=r.pos
 if stride!=4 or not 0<nt<=65536 or not 0<nf<=512 or na!=1 or (tw,th)!=(16,16):raise ValueError('Unsupported character-select frame layout.')
 tiles=np.frombuffer(r.read(nt*4),np.uint8).reshape(-1,4)
 records=[struct.unpack('>IIIff',r.read(20)) for _ in range(nf)]
 tail=sprite[r.pos:]
 if dds[:4]!=b'DDS ' or len(dds)<128 or struct.unpack_from('<I',dds,4)[0]!=124:raise ValueError('Invalid character-select DDS.')
 h,w=struct.unpack_from('<II',dds,12)
 if not w or not h or w%16 or h%16 or max(w,h)>4096 or len(dds)!=128+w*h*2:raise ValueError('Unsupported character-select atlas dimensions.')
 if struct.unpack_from('<7I',dds,80)!=(64,0,16,0xf800,0x7e0,0x1f,0):raise ValueError('Character-select atlas must use RGB565.')
 atlas=np.frombuffer(dds[128:],'<u2').reshape(h,w);canvases=[]
 for start,count,_,_,_ in records:
  if start+count>nt:raise ValueError('Character-select frame escapes its tile table.')
  parts=tiles[start:start+count]
  width=(int(parts[:,0].max(initial=0))+1)*16;height=(int(parts[:,1].max(initial=0))+1)*16
  canvas=np.full((height,width),EMPTY,np.uint16)
  for x,y,u,v in parts:
   x,y,u,v=map(int,(x,y,u,v))
   if (u+1)*16>w or (v+1)*16>h:raise ValueError('Character-select tile escapes its atlas.')
   canvas[y*16:y*16+16,x*16:x*16+16]=atlas[v*16:v*16+16,u*16:u*16+16]
  canvases.append(canvas)
 return canvases,records,sprite[:header_end],count_pos,tail


def visible_box(raw,palette):
 return colorize(raw,palette).getbbox()


def signature(raw,palette):
 image=colorize(raw,palette);box=image.getbbox()
 if box is None:return None
 image=image.crop(box).resize((48,64),Image.Resampling.BOX)
 pixels=np.array(image,dtype=float)/255
 pixels[:,:,:3]*=pixels[:,:,3:4]
 return pixels


def sync_preview(source,name,frames,main_art,assets):
 """Update verified idle counterparts; unrelated edits leave the atlas untouched."""
 if name not in ('filia','valentine'):return {}
 prefix=f'sprites/character_select_{name}'
 with GFS(source/'sprites.gfs') as sprites:
  if prefix+'.spr.msb' not in sprites.entries:return {}
  key='characters-art.gfs/characters/'+name+'.art'
  metadata_key='characters-foits.gfs/characters/'+name+'.foit'
  if key not in assets or metadata_key not in assets:return {}
  sprite=sprites.read(prefix+'.spr.msb');dds=sprites.read(prefix+'.dds')
  canvases,records,header,count_pos,tail=read_preview(sprite,dds)
  # Menu idle frames follow the standing idle, after the empty FOIT frame.
  # Verify the artwork before using this relationship on any game version.
  targets={}
  updated=parse_frames_data(name,assets[metadata_key],len(assets[key]))
  for i in range(len(records)):
   if i+1>=len(frames):continue
   frame=frames[i+1]
   if frame['art_bank']!=5 or 0 not in frame['images']:continue
   old=frame['images'][0]
   new=updated[i+1]['images'].get(0)
   if new==old:continue
   targets[i]=(old,new)
  if not targets:return {}
  palette=load_palette(name,assets[metadata_key],sprites)
  for i,(old,new) in targets.items():
   original=decode_image(old,main_art);replacement=decode_image(new,assets[key]);menu=unpack(canvases[i])
   a=signature(original,palette);b=signature(menu,palette)
   if a is None or b is None or np.mean(np.abs(a-b))>.08:
    raise ValueError(f'Cannot verify {name} character-select idle frame {i+1}; its preview differs from the standing idle.')
   sx0,sy0,sx1,sy1=visible_box(original,palette);tx0,ty0,tx1,ty1=visible_box(menu,palette)
   sx=(tx1-tx0)/(sx1-sx0);sy=(ty1-ty0)/(sy1-sy0)
   w=max(1,round(original.shape[1]*sx));h=max(1,round(original.shape[0]*sy))
   left=round(tx0-sx0*sx);top=round(ty0-sy0*sy)
   if left<0 or top<0 or left+w>4096 or top+h>4096:raise ValueError('Edited character-select idle exceeds supported bounds.')
   width=max(canvases[i].shape[1],((left+w+15)//16)*16);height=max(canvases[i].shape[0],((top+h+15)//16)*16)
   result=np.full((height,width),EMPTY,np.uint16)
   resized=np.array(Image.fromarray(replacement).resize((w,h),Image.Resampling.NEAREST))
   packed=pack(resized);packed[np.array(colorize(resized,palette))[:,:,3]==0]=EMPTY
   result[top:top+h,left:left+w]=packed;canvases[i]=result
 return build_preview(canvases,records,header,count_pos,tail,dds,prefix)


def build_preview(canvases,records,header,count_pos,tail,dds,prefix):
 unique=[];lookup={};frame_tiles=[];newrecords=[]
 for canvas,(_,_,duration,ox,oy) in zip(canvases,records):
  start=len(frame_tiles)
  for y in range(canvas.shape[0]//16):
   for x in range(canvas.shape[1]//16):
    tile=canvas[y*16:y*16+16,x*16:x*16+16]
    if np.all(tile==EMPTY):continue
    blob=tile.astype('<u2').tobytes()
    if blob not in lookup:lookup[blob]=len(unique);unique.append(blob)
    frame_tiles.append((x,y,lookup[blob]))
  if len(frame_tiles)==start:
   blob=np.full((16,16),EMPTY,dtype='<u2').tobytes()
   if blob not in lookup:lookup[blob]=len(unique);unique.append(blob)
   frame_tiles.append((0,0,lookup[blob]))
  newrecords.append((start,len(frame_tiles)-start,duration,ox,oy))
 # Keep existing dimensions where possible, grow only to fit new unique tiles.
 h,w=struct.unpack_from('<II',dds,12)
 while (h//16)*(w//16)<len(unique):
  if w<=h:w*=2
  else:h*=2
  if max(w,h)>4096:raise ValueError('Character-select atlas is full.')
 atlas=np.full((h,w),EMPTY,np.uint16);cols=w//16
 for k,blob in enumerate(unique):
  u,v=k%cols,k//cols;atlas[v*16:v*16+16,u*16:u*16+16]=np.frombuffer(blob,'<u2').reshape(16,16)
 table=b''.join(bytes((x,y,k%cols,k//cols)) for x,y,k in frame_tiles)
 header=bytearray(header);struct.pack_into('>Q',header,count_pos,len(frame_tiles))
 sprite=bytes(header)+table+b''.join(struct.pack('>IIIff',*record) for record in newrecords)+tail
 dds_header=bytearray(dds[:128]);struct.pack_into('<III',dds_header,12,h,w,w*2)
 texture=bytes(dds_header)+atlas.astype('<u2').tobytes()
 decoded,verified,_,_,_=read_preview(sprite,texture)
 if verified!=newrecords or any(not np.array_equal(a,b[:a.shape[0],:a.shape[1]]) for a,b in zip(decoded,canvases)):
  raise ValueError('Character-select round-trip verification failed.')
 return {'sprites.gfs/'+prefix+'.spr.msb':sprite,'sprites.gfs/'+prefix+'.dds':texture}
