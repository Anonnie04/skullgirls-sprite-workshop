"""Exercise real archive-format fixtures without writing to the installed game."""
from pathlib import Path
import io,json,struct,shutil,threading
import numpy as np
from PIL import Image
from workshop import *

def make_gfs(path,entries):
 def string(s):b=s.encode();return struct.pack('>Q',len(b))+b
 table=string('Reverge Package File')+string('1.1')+struct.pack('>Q',len(entries))
 for name,data in entries.items():table+=string(name)+struct.pack('>QI',len(data),1)
 path.write_bytes(struct.pack('>I',len(table)+4)+table+b''.join(entries.values()))

def fixture(root):
 game=root/'FixtureGame';data=game/'data01';data.mkdir(parents=True);arts={5:bytearray(),4:bytearray()};frames=[]
 def image(bank,flags=58,variant=0):
  index=np.tile(np.array([1,1,2,2]*4,np.uint8),(16,1));g=np.tile(np.arange(16,dtype=np.uint8)*2,(16,1))
  if variant:index=np.flip(index,axis=1).copy()
  streams=[bytes(256),g.tobytes(),index.tobytes()];encoded=[bytes([126])+len(b).to_bytes(2,'big')+b for b in streams]
  offset=len(arts[bank]);arts[bank].extend(b''.join(encoded))
  if bank==4:arts[bank].append(0xbb)
  return dict(n=1,w=1,h=1,used=1,flags=flags,mask='01',offset=offset,sizes=tuple(map(len,encoded)))
 def record(bank,images):
  result=struct.pack('<2iBBB',0,0,bank,0,sum(1<<k for k in images))
  for k,m in sorted(images.items()):result+=struct.pack('<4HB',1,1,1,1,m['flags'])+b'\x01'+struct.pack('<4i',m['offset'],*m['sizes'])
  return result+bytes(46)
 m0=image(5);m1=image(5,variant=1);m2=image(4,122);m3=image(5);overlay=image(5,variant=1)
 frames=[record(5,{0:m0}),record(5,{0:m1}),record(4,{0:m2}),record(5,{0:m3,1:overlay}),record(5,{0:m1})]
 foit=struct.pack('<I',16)+b'VRSN'+struct.pack('<I',9)+bytes(4)+b'\x01'+struct.pack('<I',len(frames))+b''.join(frames)
 palette=np.zeros((4,16,4),np.uint8)
 for row,color in [(1,(100,160,220)),(2,(200,210,180)),(3,(220,45,45))]:
  for x in range(16):palette[row,x,:3]=np.array(color)*(.35+.65*x/15);palette[row,x,3]=255
 dds=io.BytesIO();Image.fromarray(palette).save(dds,format='DDS')
 make_gfs(data/'characters-art.gfs',{'characters/annie.art':bytes(arts[5])});make_gfs(data/'characters-art-pt.gfs',{'characters/annie.art-pt':bytes(arts[4])});make_gfs(data/'characters-foits.gfs',{'characters/annie.foit':foit});make_gfs(data/'sprites.gfs',{'sprites/annie_1p.dds':dds.getvalue()})
 return game

def expect_error(callback,contains):
 try:callback()
 except Exception as exc:
  assert contains.casefold() in str(exc).casefold(),str(exc);return
 raise AssertionError('Expected operation to be refused: '+contains)

def legacy_metadata(modern,trailer=8,colors=None,groups=None,empty=False):
 if colors is None:colors=np.array([[0,0,0,0],[100,160,220,255],[200,210,180,255],[220,45,45,255]],np.uint8)
 if groups is None:groups=[(i,i) for i in range(len(colors))]
 name=b'Annie';header=bytes([len(name)])+name+bytes(4)+b'\x01'+struct.pack('<H',1)
 header+=struct.pack('<H',len(colors))+colors[:,[2,1,0,3]].tobytes()+bytes(trailer)
 header+=bytes([len(groups)])
 for i,(low,high) in enumerate(groups):
  label=f'material{i}'.encode();header+=struct.pack('<BBH',low,high,0)+bytes([len(label)])+label
 count=struct.unpack_from('<I',modern,17)[0];frames=modern[21:]
 if empty:
  image=struct.pack('<4HB',0,0,0,0,40)
  frames=struct.pack('<2iBBB',7,10,5,0,65)+image*2+bytes(46)+frames;count+=1
 return struct.pack('<I',4)+header+b'\x01'+struct.pack('<I',count)+frames


def run(report):
 report=Path(report).resolve();root=unique(report.parent/'Test Runs','Workshop tests');passed=[]
 try:
  # Similar whites may share a material; hue, opacity and outline stay guarded.
  pal=np.zeros((4,16,4),float);pal[1,:,:3]=240;pal[2,:,:3]=235;pal[3,:,:3]=[240,30,30];pal[1:, :,3]=255
  raw_white=np.zeros((1,3,3),np.uint8);raw_white[:,:,1]=31;raw_white[:,:,2]=1
  pixels=np.array([[[240,240,240,254],[240,30,30,254],[240,240,240,128]]],np.uint8)
  mapped,swaps=remap_whites(raw_white,pal,pixels,np.ones((1,3),bool),2)
  assert swaps==1 and mapped[0,0,2]==2 and np.array_equal(mapped[0,1:],raw_white[0,1:])
  assert np.array_equal(mapped[:,:,0],raw_white[:,:,0]) and np.array_equal(mapped[:,:,1]//32,raw_white[:,:,1]//32)
  refused,swaps=remap_whites(raw_white,pal,pixels,np.ones((1,3),bool),3);assert swaps==0 and np.array_equal(refused,raw_white)
  assert white_materials(pal)==[1,2]
  passed.append('white material fitting keeps normals outline opacity and nonwhite pixels; distant colors refused')
  from compression import encode_exact
  from decoder import rle
  blank=bytes(256);encoded,_=encode_exact(blank,259);assert len(encoded)==259 and bytes(rle(encoded,256))==blank;passed.append('simple replacements pad with valid exact-length RLE')
  import compression as codec
  from itertools import product
  # Exhaustively compare the masked planner with every legal assignment.
  for seed in range(8):
   rng_mask=np.random.default_rng(seed);values=rng_mask.integers(0,4,7,dtype=np.uint8);free=np.zeros(7,bool);free[[1,4]]=True
   optimized,minimum=codec.optimize_ignored_brightness(values,free)
   brute=1000
   for a,b in product(range(32),repeat=2):
    trial=values.copy();trial[1]=a;trial[4]=b;brute=min(brute,codec.reference_optimal(trial)[0])
   assert minimum==brute and codec.encode_exact(optimized,None)[1]==minimum
   assert np.array_equal(optimized[~free],values[~free]) and np.array_equal(optimized>>5,values>>5)
  passed.append('masked brightness optimizer matches exhaustive legal assignments and preserves every visible bit')
  # Context IDs above 255 must remain distinct; compare all legal palette choices.
  for seed in range(4):
   rng_groups=np.random.default_rng(seed);groups=rng_groups.integers(0,2,(301,4),dtype=np.int16);contexts=np.array([0,300,1,300,0]);values=rng_groups.integers(0,4,5,dtype=np.uint8)
   choices=[np.flatnonzero(groups[c]==groups[c,v]) for c,v in zip(contexts,values)]
   brute=min(codec.reference_optimal(np.array(t,np.uint8))[0] for t in product(*choices))
   optimized,minimum=codec.optimize_equivalent_indices(values,contexts,groups)
   assert minimum==brute and codec.encode_exact(optimized,None)[1]==minimum
   assert all(groups[c,a]==groups[c,b] for c,a,b in zip(contexts,values,optimized))
   native_mask=codec.native_optimal
   try:
    codec.native_optimal=None;fallback,fallback_min=codec.optimize_equivalent_indices(values,contexts,groups);assert fallback_min==minimum
    fallback_g,fallback_g_min=codec.optimize_ignored_brightness(np.array([1,0,1],np.uint8),np.array([False,True,False]));assert fallback_g_min==2 and list(fallback_g)==[1,1,1]
   finally:codec.native_optimal=native_mask
  passed.append('equivalent palette optimizer matches exhaustive assignments and CPU fallback with wide contexts')
  palette_test=np.zeros((5,16,4),float);palette_test[1,:,:3]=np.arange(16)[:,None]*15;palette_test[1,:,3]=255;palette_test[2]=palette_test[1];palette_test[3,:,:3]=[200,20,20];palette_test[3,:,3]=255
  g=np.array([31,224,0,31,224,0],np.uint8);idx=np.array([1,3,4,2,0,0],np.uint8);groups=equivalent_material_groups(palette_test)
  optimized,_=codec.optimize_equivalent_indices(idx,g,groups)
  a=np.zeros((1,len(g),3),np.uint8);a[0,:,1]=g;a[0,:,2]=idx;b=a.copy();b[0,:,2]=optimized
  assert np.array_equal(np.array(colorize(a,palette_test)),np.array(colorize(b,palette_test)))
  passed.append('equivalent storage changes preserve rendered opaque black and transparent pixels')
  streams=[codec.encode_exact(bytes([value])*256,None)[0] for value in [0,17,1]];bank=b''.join(streams)
  meta=dict(n=1,w=1,h=1,used=1,flags=58,mask='01',offset=0,sizes=tuple(map(len,streams)))
  raw=decode_image(meta,bank);replacement=raw.copy();replacement[::2,:,1]=16;pixels=np.array(colorize(replacement,palette_test))
  payload,preview,stats=encode_replacement(meta,bank,palette_test,pixels)
  assert len(payload)==len(bank) and stats['brightness_color_tolerance'] and stats['shading_max_error']<=12
  restored=decode_image(meta,payload);assert np.array_equal(restored[:,:,0],raw[:,:,0]) and np.array_equal(np.array(preview)[:,:,3],pixels[:,:,3])
  passed.append('nearby shading fits an otherwise oversized stream with unchanged normals opacity and fixed slots')
  values=np.array([16,17,17,17,18],np.uint8);contexts=np.zeros(5,np.int32);groups=np.ones((1,256),np.int16)
  chosen,minimum=codec.optimize_equivalent_indices(values,contexts,groups,preferred=values.astype(np.int16))
  assert minimum==2 and np.all(chosen==17)
  passed.append('equally compact shading uses the median preferred value to limit visible bias')
  native=codec.native_optimal
  rng=np.random.default_rng(9)
  streams=[bytes(),bytes(256),bytes(70000),rng.integers(0,256,2000,dtype=np.uint8).tobytes(),np.repeat(rng.integers(0,10,150,dtype=np.uint8),rng.integers(1,300,150)).tobytes()]
  for stream in streams:
   reference=codec.reference_optimal(stream)
   if native is not None:
    accelerated=native(np.frombuffer(stream,dtype=np.uint8));assert reference[0]==accelerated[0] and np.array_equal(reference[1],accelerated[1]) and np.array_equal(reference[2],accelerated[2])
   codec.packet_plan.cache_clear();payload,_=codec.encode_exact(stream,None);assert bytes(rle(payload,len(stream)))==stream
  codec.packet_plan.cache_clear();first,_=codec.encode_exact(bytes(256),None);codec.encode_exact(bytes(256),259);assert codec.packet_plan.cache_info().hits==1
  try:
   codec.native_optimal=None;codec.packet_plan.cache_clear();fallback,_=codec.encode_exact(bytes(256),None);assert first==fallback
  finally:codec.native_optimal=native;codec.packet_plan.cache_clear()
  passed.append('native compression preserves reference tie rules and exact bytes; repeated planning cached; CPU fallback verified')
  literal=rng.integers(0,256,2000,dtype=np.uint8).tobytes()
  compact,minimum=codec.encode_exact(literal,None);assert minimum<=2003
  padded,_=codec.encode_exact(literal,2005);assert len(padded)==2005 and bytes(rle(padded,2000))==literal
  passed.append('extended literal packets fit smaller slots with exact padding and lossless round trip')
  game=fixture(root);original={p.name:sha(p) for p in (game/'data01').glob('*.gfs')}
  import workshop as engine
  original_decode=engine.decode_image;original_open=Image.open
  try:
   def forbidden(*args,**kwargs):raise AssertionError('Tree generation must not decode or open PNGs')
   engine.decode_image=forbidden;Image.open=forbidden
   tree,tree_manifest=generate_input_tree(game,root/'Projects')
  finally:engine.decode_image=original_decode;Image.open=original_open
  with GFS(game/'data01'/'characters-art-pt.gfs') as art_pt,GFS(game/'data01'/'characters-art.gfs') as art,GFS(game/'data01'/'characters-foits.gfs') as foit:
   fs=parse_frames_data('annie',foit.read('characters/annie.foit'),art.entries['characters/annie.art'][1]);meta=fs[2]['images'][0];bank=art_pt.read('characters/annie.art-pt');baseline=decode_image(meta,bank)
   start=meta['offset'];normal=bank[start:start+meta['sizes'][0]];goffset=start+meta['sizes'][0];stored=rle(bank[goffset:goffset+meta['sizes'][1]],256).reshape(16,16)
   altered=stored.copy();altered[1:15:2]=(altered[1:15:2]&224)|rng.integers(0,32,(7,16),dtype=np.uint8)
   encoded,_=codec.encode_exact(altered.ravel(),meta['sizes'][1]);ioffset=goffset+meta['sizes'][1];payload=normal+encoded+bank[ioffset:ioffset+meta['sizes'][2]]
   restored=decode_image(meta,bank[:start]+payload+bank[start+len(payload):]);assert np.array_equal(baseline,restored)
  passed.append('ignored interpolated brightness bits can be compressed differently without changing decoded art or normals')
  with GFS(game/'data01'/'characters-art.gfs') as art,GFS(game/'data01'/'characters-foits.gfs') as foit,GFS(game/'data01'/'sprites.gfs') as sprites:
   fs=parse_frames_data('annie',foit.read('characters/annie.foit'),art.entries['characters/annie.art'][1]);meta=fs[0]['images'][0];bank=art.read('characters/annie.art')
   with Image.open(io.BytesIO(sprites.read('sprites/annie_1p.dds'))) as image:pal=np.array(image.convert('RGBA'),float)
   edited=decode_image(meta,bank);edited[4:8,4:8,1]=0;edited[4:8,4:8,2]=3;png=np.array(colorize(edited,pal))
   payload,preview,stats=encode_replacement(meta,bank,pal,png)
   assert np.array_equal(np.array(preview),png),'Representable edited colors must not be replaced by old material colors'
   assert stats['palette_selection']=='closest palette' and stats['material_color_changes']==0 and not stats['brightness_color_tolerance']
   assert len(stats['compression_attempts'])==1 and not stats['compression_attempts'][0]['allow_shading']
  passed.append('exact representable edited colors win over original-material bias before any visible fitting')
  assert tree_manifest['status']=='complete' and not list(tree.rglob('*.png')) and scan_input(tree)==([],[])
  assert tree_manifest['characters'].keys()=={'annie'}
  passed.append('standalone full Input tree without decoding or opening PNGs')
  legacy=fixture(root/'Legacy')
  for archive in (legacy/'data01').glob('*.gfs'):
   with GFS(archive) as contents:
    entries={key.replace('characters/','temp/').replace('sprites/','temp/true_color_sprites/'):contents.read(key) for key in contents.entries}
   if archive.name=='characters-foits.gfs':
    entries={key:value[:8]+struct.pack('<I',3)+value[12:] for key,value in entries.items()}
   make_gfs(archive,entries)
  assert available_characters(legacy)==['annie']
  legacy_project,legacy_manifest=export_project(legacy,root/'Projects',['annie'],limit=1)
  assert legacy_manifest['status']=='complete' and len(legacy_manifest['exports'])==1
  legacy_route=next(iter(legacy_manifest['exports']))
  pixels=np.array(Image.open(legacy_project/'Output'/legacy_route).convert('RGBA'));pixels[4:12,4:12]=[180,35,35,254];Image.fromarray(pixels).save(legacy_project/'Input'/legacy_route)
  legacy_prepared,legacy_plan=prepare_import(legacy,legacy_project);assert len(legacy_plan['patches'])==1 and not legacy_plan['errors'],legacy_plan
  legacy_original={f.name:sha(f) for f in (legacy/'data01').glob('*.gfs')}
  legacy_backup,_=apply_import(legacy_prepared,check_running=False);restore_import(legacy_backup,check_running=False)
  assert legacy_original=={f.name:sha(f) for f in (legacy/'data01').glob('*.gfs')}
  passed.append('legacy temp archive paths support detection export import and verified restore')
  # Early metadata has no VRSN header and omits pointer/size fields on empty images.
  early=fixture(root/'PreVRSN');archive=early/'data01'/'characters-foits.gfs'
  with GFS(archive) as contents:modern=contents.read('characters/annie.foit')
  preversion=legacy_metadata(modern,empty=True)
  make_gfs(archive,{'characters/annie.foit':preversion})
  early_project,early_manifest=export_project(early,root/'Projects',['annie'])
  assert early_manifest['status']=='complete' and early_manifest['characters']['annie']['frames']==6
  assert early_manifest['characters']['annie']['exported']==5
  assert [v['frame'] for v in early_manifest['exports'].values()][0]==1
  early_route=next(iter(early_manifest['exports']))
  shutil.copy2(early_project/'Output'/early_route,early_project/'Input'/early_route)
  _,early_plan=prepare_import(early,early_project)
  assert not early_plan['errors'] and len(early_plan['skipped'])==1
  from decoder import legacy_palette
  controls=np.array([[0,0,0,0],[240,180,120,255],[120,90,60,255],[30,20,10,255],[220,30,40,100],[110,15,20,100]],np.uint8)
  for trailer in [8,10]:
   table=legacy_palette(legacy_metadata(modern,trailer,controls,[(0,0),(1,3),(4,5)]))
   assert np.array_equal(table[1],table[2]) and np.array_equal(table[1],table[3])
   assert np.array_equal(table[1,0],controls[3]) and np.array_equal(table[1,-1],controls[1])
   assert np.array_equal(table[1,1],[42,29,16,255])
   assert np.array_equal(table[4],table[5]) and np.all(table[4,:,3]==100)
   probe=np.array([[[0,31,2],[0,0,2],[0,31,5]]],np.uint8)
   assert np.array_equal(np.array(colorize(probe,table))[0],[[240,180,120,254],[30,20,10,254],[220,30,40,200]])
  expect_error(lambda:legacy_palette(preversion[:20]),'legacy character palette')
  # Embedded colors, rather than the deliberately different DDS gradients, render exports.
  first=np.array(Image.open(early_project/'Output'/early_route).convert('RGBA'))
  assert np.any(np.all(first==[100,160,220,254],axis=2))
  with GFS(archive) as contents:table=load_palette('annie',contents.read('characters/annie.foit'),None)
  with GFS(early/'data01'/'characters-art.gfs') as contents:
   fs=parse_frames_data('annie',preversion,contents.entries['characters/annie.art'][1]);bank=contents.read('characters/annie.art')
   assert np.array_equal(np.array(matching_silhouette(fs[1]['images'][0],bank,table))[:,:,3],first[:,:,3])
  first[4:12,4:12]=[220,45,45,254];Image.fromarray(first).save(early_project/'Input'/early_route)
  prepared,plan=prepare_import(early,early_project)
  assert len(plan['patches'])==1 and not plan['errors'],plan
  early_original={f.name:sha(f) for f in (early/'data01').glob('*.gfs')}
  backup,_=apply_import(prepared,check_running=False);restore_import(backup,check_running=False)
  assert early_original=={f.name:sha(f) for f in (early/'data01').glob('*.gfs')}
  passed.append('legacy embedded gradients render correct RGB alpha and silhouettes; both palette layouts and verified import/restore')
  # An art entry alone cannot be exported without its palette.
  art_path=early/'data01'/'characters-art.gfs'
  with GFS(art_path) as contents:entries={key:contents.read(key) for key in contents.entries}
  entries['characters/bossmarie.art']=b'placeholder';make_gfs(art_path,entries)
  assert available_characters(early)==['annie']
  expect_error(lambda:parse_frames_data('annie',modern[:8]+struct.pack('<I',99)+modern[12:],99999),'Unsupported FOIT version')
  expect_error(lambda:parse_frames_data('annie',bytes(100),99999),'No valid frame section')
  passed.append('pre-VRSN empty frames preserve numbering and export/import; missing palettes excluded; unknown versions refused')
  project,manifest=export_project(game,root/'Projects',['annie']);assert manifest['status']=='complete';assert len(manifest['exports'])==7
  assert not list((project/'Input').rglob('*.png'));od={p.relative_to(project/'Output').as_posix() for p in (project/'Output').rglob('*') if p.is_dir()};id={p.relative_to(project/'Input').as_posix() for p in (project/'Input').rglob('*') if p.is_dir()};assert od==id;passed.append('mirrored branches; Input empty; layered frames exported')
  tree_route=next(k for k,v in tree_manifest['exports'].items() if v['frame']==0)
  shutil.copy2(project/'Output'/tree_route,tree/'Input'/tree_route)
  _,tree_plan=prepare_import(game,tree);assert not tree_plan['errors'] and len(tree_plan['skipped'])==1,tree_plan
  passed.append('standalone tree recognizes added PNGs and prepares them without export')
  reference=game/'Digital Art Compendium'/'Frame Dump'/'annie'/'idle'/'stand_idle';reference.mkdir(parents=True)
  shutil.copy2(project/'Output'/tree_route,reference/'idle01_annie_1p.png')
  reference_tree,reference_manifest=generate_input_tree(game,root/'Projects')
  reference_route=next(iter(reference_manifest['reference_files']))
  assert (reference_tree/'Input'/reference_route).parent.is_dir() and not list(reference_tree.rglob('*.png'))
  shutil.copy2(reference/'idle01_annie_1p.png',reference_tree/'Input'/reference_route)
  assert len(scan_input(reference_tree)[0])==1
  _,reference_plan=prepare_import(game,reference_tree);assert not reference_plan['errors'],reference_plan
  passed.append('Compendium tree recognizes filenames and lazily resolves game frames')
  alias_project,alias_manifest=export_project(game,root/'Projects',['annie'],limit=1)
  alias_route=next(iter(alias_manifest['exports']));parts=alias_route.split('/');assert parts[:2]==['annie','annie']
  actual_route='/'.join(parts[1:]);alias_path=alias_project/'Input'/actual_route;alias_path.parent.mkdir(parents=True,exist_ok=True)
  with Image.open(alias_project/'Output'/alias_route) as image:edited_alias=np.array(image.convert('RGBA'))
  edited_alias[4:8,4:8]=[77,16,16,254];Image.fromarray(edited_alias).save(alias_path)
  found_alias,unknown_alias=scan_input(alias_project);assert not unknown_alias and found_alias[0][1]==actual_route and found_alias[0][2]['_route']==alias_route
  alias_prepared,alias_plan=prepare_import(game,alias_project);assert len(alias_plan['patches'])==1 and not alias_plan['errors'],alias_plan
  assert actual_route in alias_plan['input_hashes'] and alias_route not in alias_plan['input_hashes']
  saved_alias=alias_path.read_bytes();alias_path.write_bytes(saved_alias+b'changed');expect_error(lambda:apply_import(alias_prepared,check_running=False),'Input PNG changed');alias_path.write_bytes(saved_alias)
  alias_backup,_=apply_import(alias_prepared,check_running=False);restore_import(alias_backup,check_running=False)
  assert route_signature('annie/data/attack/frames/effects/a.png')==route_signature('annie/annie/data/attack/effects/frames/a.png')
  assert route_signature('../annie/data/a.png') is None
  passed.append('alternate Input folder layouts preserve actual-path integrity through prepare apply and restore')
  # A normalized alias must not choose between two different recorded routes.
  ambiguous=dict(alias_manifest);ambiguous['exports']={
   'annie/annie/data/attack/frames/effects/a.png':next(iter(alias_manifest['exports'].values())),
   'annie/annie/data/attack/effects/frames/a.png':next(iter(alias_manifest['exports'].values()))}
  ambiguity=root/'Ambiguous project';(ambiguity/'Input/annie/data/attack/effects').mkdir(parents=True);write_json(ambiguity/'project.json',ambiguous)
  shutil.copy2(alias_path,ambiguity/'Input/annie/data/attack/effects/a.png');assert not scan_input(ambiguity)[0] and len(scan_input(ambiguity)[1])==1
  passed.append('ambiguous normalized folder routes are refused instead of guessed')
  # Optional Misc_ is restricted to Parasoul troops and never chooses a
  # destination when two recorded paths collapse to the same alias.
  troop_route='parasoul/parasoul/data/troops/jump/frames/Misc_soldier_jump_up1_parasoul_1p.png'
  troop_actual='parasoul/data/troops/frames/jump/soldier_jump_up1_parasoul_1p.png'
  assert route_signature(troop_route)==route_signature(troop_actual)
  assert route_signature('parasoul/data/idle/Misc_a.png')!=route_signature('parasoul/data/idle/a.png')
  troops=dict(alias_manifest);troops['characters']={'parasoul':{}};troops['exports']={troop_route:dict(character='parasoul',frame=0,layer=0)}
  troop_project=root/'Troop aliases';troop_path=troop_project/'Input'/troop_actual;troop_path.parent.mkdir(parents=True);shutil.copy2(alias_path,troop_path);write_json(troop_project/'project.json',troops)
  found,unknown=scan_input(troop_project);assert not unknown and found[0][1]==troop_actual and found[0][2]['_route']==troop_route
  troops['exports'][troop_route.replace('Misc_','')]=troops['exports'][troop_route];write_json(troop_project/'project.json',troops)
  assert not scan_input(troop_project)[0] and scan_input(troop_project)[1]==[troop_actual]
  passed.append('Parasoul troop Misc aliases preserve actual paths and refuse collisions; other animations stay distinct')
  from layout import Catalog,descriptor
  from scipy.spatial import cKDTree
  catalog=Catalog.__new__(Catalog);catalog.name='parasoul'
  catalog.paths=['troops/crimsonhunting/Misc_afire1_parasoul_1p.png','other.png']
  silhouette=Image.new('RGBA',(16,16),(0,0,0,255));vector=descriptor(silhouette)
  def candidates(first,second):
   vectors=np.array([vector.copy(),vector.copy()]);vectors[0,0]+=first;vectors[1,1]+=second;catalog.tree=cKDTree(vectors)
  candidates(6,12);assert catalog.route(silhouette,1508)[0]==catalog.convert(catalog.paths[0])
  candidates(6,7);assert catalog.route(silhouette,1508)[0]==catalog.fallback(1508)
  candidates(8,12);assert catalog.route(silhouette,1508)[0]==catalog.fallback(1508)
  candidates(6,12);catalog.paths[0]='troops/crimsonhunting/Misc_a6_parasoul_1p.png';assert catalog.route(silhouette,1508)[0]==catalog.fallback(1508)
  passed.append('translucent troop flash matching accepts separated candidates but refuses ambiguity distance overflow and unrelated poses')
  # Existing exported projects can recognize a newly installed Compendium route.
  extra_reference=reference.parent/'extra';extra_reference.mkdir();shutil.copy2(reference/'idle01_annie_1p.png',extra_reference/'extra01_annie_1p.png')
  lazy_input=alias_project/'Input'/'annie/data/idle/extra/frames/extra01_annie_1p.png';lazy_input.parent.mkdir(parents=True);shutil.copy2(extra_reference/'extra01_annie_1p.png',lazy_input)
  lazy_found,lazy_unknown=scan_input(alias_project);assert not lazy_unknown
  assert any(e['frame'] is None and e.get('reference_relative') for f,r,e in lazy_found)
  assert json.loads((alias_project/'project.json').read_text())==alias_manifest
  lazy_input.unlink();(extra_reference/'extra01_annie_1p.png').unlink();extra_reference.rmdir()
  passed.append('exported projects discover installed Compendium references without rewriting manifests or moving PNGs')
  with GFS(game/'data01'/'characters-art.gfs') as art,GFS(game/'data01'/'characters-art-pt.gfs') as pt,GFS(game/'data01'/'characters-foits.gfs') as foit,GFS(game/'data01'/'sprites.gfs') as sprites:
   frames=parse_frames_data('annie',foit.read('characters/annie.foit'),art.entries['characters/annie.art'][1])
   banks={5:art.read('characters/annie.art'),4:pt.read('characters/annie.art-pt')}
   with Image.open(io.BytesIO(sprites.read('sprites/annie_1p.dds'))) as im:palette=np.array(im.convert('RGBA'),dtype=float)
   for fr in frames:
    for meta in fr['images'].values():assert np.array_equal(np.array(matching_silhouette(meta,banks[fr['art_bank']],palette))[:,:,3],np.array(colorize(decode_image(meta,banks[fr['art_bank']]),palette))[:,:,3])
   original_match=engine.matching_silhouette
   try:
    engine.matching_silhouette=lambda *args:(_ for _ in ()).throw(AssertionError('Cached maps must not decode frames'))
    _,cached_plan=prepare_import(game,reference_tree);assert not cached_plan['errors'],cached_plan
   finally:engine.matching_silhouette=original_match
   events=[];changed={**banks,5:banks[5]+b'changed'}
   resolve_frame_routes(game/'data01','annie',frames,palette,changed,reference_tree,lambda *a:events.append(a),None)
   assert any('Matching' in e[2] for e in events)
  passed.append('alpha matching matches rendered alpha exactly; cached maps skip decoding and invalidate on changed art')

  from project_match import align_sequences,match_projects,copy_matches
  a=np.zeros(1025);a[0]=10;b=np.zeros(1025);b[1]=10;c=np.zeros(1025);c[2]=10;extra=np.zeros(1025);extra[3]=10
  pairs,_=align_sequences([a,b,c],[a,extra,b,c],None);assert [(i,j) for i,j,_ in pairs]==[(0,0),(1,2),(2,3)]
  match_source,ms=export_project(game,root/'Projects',['annie'],limit=3)
  match_target,mt=export_project(game,root/'Projects',['annie'],limit=3)
  source_route=next(k for k,v in ms['exports'].items() if v['frame']==0)
  edited=np.array(Image.open(match_source/'Output'/source_route).convert('RGBA'));edited[4:12,4:12]=[180,35,35,254];Image.fromarray(edited).save(match_source/'Output'/source_route)
  original_source=sha(match_source/'Output'/source_route)
  match_folder,matches=match_projects(match_source,match_target);assert len(matches['matches'])==3 and not matches['review']
  _,copied=copy_matches(match_folder);assert len(copied['copied'])==1 and copied['unchanged']==2,copied
  assert sha(match_source/'Output'/source_route)==original_source
  shutil.copy2(match_target/'Output'/source_route,match_target/'Input'/source_route)
  _,references=copy_matches(match_folder);assert len(references['replaced_references'])==1
  assert sha(match_target/'Input'/source_route)==original_source

  existing=match_target/'Input'/source_route;existing.write_bytes(b'keep my edit')
  _,again=copy_matches(match_folder);assert len(again['existing'])==1 and existing.read_bytes()==b'keep my edit'
  edited[0,0]=[1,2,3,255];Image.fromarray(edited).save(match_source/'Output'/source_route)
  expect_error(lambda:copy_matches(match_folder),'PNG changed')
  passed.append('project alignment handles inserted frames; copies preserve originals and existing edits; stale matching refused')
  # Missing middle characters must not stop later characters or renumber frames.
  sparse_source=root/'SparseSource';sparse_target=root/'SparseTarget'
  shutil.copytree(match_source,sparse_source);shutil.copytree(match_target,sparse_target)
  for location,extra_names in [(sparse_source,['double','filia']),(sparse_target,['double','eliza','filia'])]:
   saved=json.loads((location/'project.json').read_text());base=list(saved['exports'].items())
   for name in extra_names:
    for route,entry in base:
     renamed=route.replace('annie',name);saved['exports'][renamed]={**entry,'character':name}
     target_png=safe_path(location/'Output',renamed);target_png.parent.mkdir(parents=True,exist_ok=True)
     shutil.copy2(location/'Output'/route,target_png)
   write_json(location/'project.json',saved)
  shutil.rmtree(sparse_source/'Output'/'double')
  source_missing=next(r for r,e in ms['exports'].items() if e['frame']==1)
  (sparse_source/'Output'/source_missing).unlink()
  target_missing=next(r for r,e in mt['exports'].items() if e['frame']==2).replace('annie','filia')
  (sparse_target/'Output'/target_missing).unlink()
  sparse_folder,sparse=match_projects(sparse_source,sparse_target)
  assert sparse['status']=='matched' and len(sparse['missing_exports'])==5
  paired=sparse['matches']+sparse['review']
  # Reused-image recovery may pair more than one available source frame to
  # a surviving target, but never reference the target PNG that is missing.
  assert {r['character'] for r in paired}=={'annie','filia'} and len(paired)==5
  assert {r['source_frame'] for r in paired if r['character']=='annie'}=={0,2}
  assert {r['target_frame'] for r in paired if r['character']=='filia'}=={0,1}
  assert {r['source_frame'] for r in paired if r['character']=='filia'}=={0,1,2}
  _,sparse_sm=project_info(sparse_source);_,sparse_tm=project_info(sparse_target)
  for record in paired:
   for item in record['copies']:
    assert (sparse_source/'Output'/item['source']).is_file() and (sparse_target/'Output'/item['target']).is_file()
    assert sparse_sm['exports'][item['source']]['frame']==record['source_frame']
    assert sparse_tm['exports'][item['target']]['frame']==record['target_frame']
  copy_matches(sparse_folder)
  # A surviving composite cannot conceal a missing editable layer.
  from project_match import present_frames
  partial=dict(unmatched=[],missing_exports=[])
  groups={'annie':[(3,[(source_route,{'layer':None}),('missing/layers/frame.png',{'layer':1})])]}
  assert present_frames(sparse_source,groups,'source',partial,None)=={}
  assert partial['missing_exports'][0]['paths']==['missing/layers/frame.png']
  assert partial['unmatched'][0]['source_frame']==3
  passed.append('missing source/target PNGs and whole characters do not stop later matches; frame IDs and layer integrity preserved')
  # Drive the actual Tk buttons and their worker/event completion path.
  from workshop_app import App
  import workshop_app as ui,time
  ui_source,um=export_project(game,root/'Projects',['annie'],limit=2)
  ui_target,_=export_project(game,root/'Projects',['annie'],limit=2)
  uroute=next(k for k,v in um['exports'].items() if v['frame']==0)
  upng=ui_source/'Output'/uroute;pixels=np.array(Image.open(upng).convert('RGBA'));pixels[4:12,4:12,:3]=[180,35,35];Image.fromarray(pixels).save(upng)
  app=App();app.withdraw();app.match_source.set(str(ui_source));app.match_target.set(str(ui_target))
  def await_ui():
   deadline=time.monotonic()+15
   while app.busy:
    app.update();time.sleep(.01)
    assert time.monotonic()<deadline,'UI worker did not finish'
  messages=[];old_error=ui.messagebox.showerror;ui.messagebox.showerror=lambda *args:messages.append(args)
  try:
   app.overlap.set(99);assert app.overlap_label.get()=='99%'
   app.match_button.invoke();assert 'disabled' in app.overlap_slider.state();await_ui();assert app.match_folder and 'disabled' not in app.copy_button.state()
   assert app.match_report['min_overlap']==.99 and 'disabled' not in app.overlap_slider.state()
   assert not list((ui_target/'Input').rglob('*.png'));assert 'Nothing copied yet' in app.status.get()
   # A failed copy must leave the Copy button available to retry.
   saved=upng.read_bytes();upng.write_bytes(saved+b'changed')
   app.copy_button.invoke();await_ui();assert messages and 'disabled' not in app.copy_button.state()
   upng.write_bytes(saved);app.copy_button.invoke();await_ui()
   assert len(list((ui_target/'Input').rglob('*.png')))==1
   assert app.project.get()==str(ui_target) and app.tabs.index(app.tabs.select())==1
   assert (app.match_folder/'copy-result.json').exists();assert 'Copied 1 PNGs' in app.status.get()
  finally:ui.messagebox.showerror=old_error;app.destroy()
  passed.append('real Match and Copy buttons stage PNGs; failed copies remain retryable; UI distinguishes matching from copying')
  passed.append('shape overlap slider updates its percentage, supplies the worker threshold and stays locked during matching')

  from animation_sequence import animations,plan_sequence,stage_sequence
  layered_groups=[items for key,items in animations(project).items() if '[layer ' in key]
  assert len(layered_groups)==2 and all(len({entry['layer'] for route,entry in items})==1 for items in layered_groups)
  sequence_target,_=export_project(game,root/'Projects',['annie'],limit=3)
  sequence_groups=animations(sequence_target);animation=max(sequence_groups,key=lambda k:len(sequence_groups[k]));routes=[r for r,e in sequence_groups[animation]];assert len(routes)>=2
  exporter=root/'Animation editor exports';exporter.mkdir();files=[]
  for name,color in [('Timeline 1_0010.png',(120,30,40,254)),('Timeline 1_0002.png',(10,20,30,254))]:
   file=exporter/name;Image.new('RGBA',(4,4),color).save(file);files.append(file)
  source_hashes={str(f):sha(f) for f in files};output_hashes={str(f):sha(f) for f in (sequence_target/'Output').rglob('*.png')}
  mapping=plan_sequence(sequence_target,files,animation);assert Path(mapping[0]['source']).name=='Timeline 1_0002.png'
  _,staged=stage_sequence(sequence_target,files,animation);assert staged['copied']==2 and staged['backed_up']==0
  assert sha(sequence_target/'Input'/routes[0])==sha(files[1]) and sha(sequence_target/'Input'/routes[1])==sha(files[0])
  expect_error(lambda:plan_sequence(sequence_target,[files[1]],animation,start=1),'already contains')
  previous=sha(sequence_target/'Input'/routes[1]);_,replaced=stage_sequence(sequence_target,[files[1]],animation,start=1,overwrite=True)
  assert replaced['backed_up']==1 and sha(Path(replaced['folder'])/'Previous Input'/routes[1])==previous
  before_input={str(f):sha(f) for f in (sequence_target/'Input').rglob('*.png')}
  def fail_sequence(*args):raise OSError('simulated copy failure')
  try:stage_sequence(sequence_target,files,animation,overwrite=True,progress=fail_sequence)
  except OSError:pass
  else:raise AssertionError('Failure should roll back sequence staging')
  assert before_input=={str(f):sha(f) for f in (sequence_target/'Input').rglob('*.png')}
  expect_error(lambda:plan_sequence(sequence_target,files,animation,start=len(routes)-1),'exceeds')
  assert source_hashes=={str(f):sha(f) for f in files} and output_hashes=={str(f):sha(f) for f in (sequence_target/'Output').rglob('*.png')}
  assert len(scan_input(sequence_target)[0])==2 and not scan_input(sequence_target)[1]
  passed.append('animation sequence natural ordering single-frame start backups rollback and overflow; sources and Output preserved')
  alias=sequence_target/'Input'/animation/'Timeline reference_0000.png';shutil.copy2(files[1],alias)
  stage_sequence(sequence_target,[alias],animation,overwrite=True)
  assert len(scan_input(sequence_target)[0])==2 and not scan_input(sequence_target)[1]
  alias_bytes=alias.read_bytes();Image.new('RGBA',(4,4),(240,80,30,254)).save(alias)
  assert len(scan_input(sequence_target)[1])==1
  alias.write_bytes(alias_bytes)
  passed.append('staged animation sources inside Input are ignored only while source and destination hashes still match')
  app=App();app.withdraw();app.project.set(str(sequence_target));old_picker=ui.filedialog.askopenfilenames
  try:
   ui.filedialog.askopenfilenames=lambda **kwargs:tuple(map(str,files))
   app.sequence_button.invoke();dialog=app.sequence_dialog;dialog.withdraw();dialog.animation.set(animation);dialog.select_animation();dialog.overwrite.set(True)
   assert 'disabled' not in dialog.copy_button.state();dialog.copy_button.invoke();await_ui()
   assert 'Animation staged' in app.status.get() and len(app.table.get_children())==2
   app.update_idletasks();assert app.winfo_reqheight()<=900
  finally:ui.filedialog.askopenfilenames=old_picker;app.destroy()
  passed.append('actual sequence import button mapping dialog and worker stage numbered PNGs within window')

  assert scan_input(project)==([],[]);expect_error(lambda:prepare_import(game,project),'no PNGs');passed.append('empty Input scan')
  route=next(k for k,v in manifest['exports'].items() if v['frame']==0);shutil.copy2(project/'Output'/route,project/'Input'/route)
  prepared,plan=prepare_import(game,project);assert not plan['patches'] and len(plan['skipped'])==1;passed.append('unchanged PNG skipped')
  (project/'Input'/'unknown.png').write_bytes((project/'Output'/route).read_bytes());_,plan=prepare_import(game,project);assert len(plan['errors'])==1;(project/'Input'/'unknown.png').unlink();passed.append('unrecognized Input paths refused')
  expect_error(lambda:safe_path(project,'../escape.png'),'escapes');passed.append('path traversal refused')
  # Make an actual full-canvas change, preserving dimensions; both art banks.
  for frame in [0,2]:
   rel=next(k for k,v in manifest['exports'].items() if v['frame']==frame)
   image=Image.open(project/'Output'/rel).convert('RGBA');pixels=np.array(image);pixels[4:12,4:12]=[180,35,35,254];Image.fromarray(pixels).save(project/'Input'/rel)
  prepared,plan=prepare_import(game,project);assert len(plan['patches'])==2 and not plan['errors'],plan
  assert {p['art_bank'] for p in plan['patches']}=={4,5};passed.append('changed PNGs prepared for both art banks, including interpolated shading')
  mod_folder,mods=export_mod_zips(prepared,root/'Mod ZIPs')
  assert len(mods)==1 and mods[0]['character']=='annie'
  import zipfile
  with zipfile.ZipFile(mod_folder/mods[0]['file']) as archive:
   info=json.loads(archive.read('mod.json'));assert info['id'].startswith('spriteworkshop.annie.') and info['version']=='1.0.0'
   assert set(archive.namelist())=={'mod.json','characters-art.gfs/characters/annie.art','characters-art-pt.gfs/characters/annie.art-pt','characters-foits.gfs/characters/annie.foit'}
   metadata=archive.read('characters-foits.gfs/characters/annie.foit')
   new_frames=parse_frames_data('annie',metadata,len(archive.read('characters-art.gfs/characters/annie.art')))
   for bank,(archive_name,suffix) in ART_FILES.items():
    with GFS(game/'data01'/archive_name) as original_archive:
     offset,size=original_archive.entries[f'characters/annie{suffix}'];expected=bytearray(original_archive.read(f'characters/annie{suffix}'))
    for record in plan['patches']:
     if record['art_bank']==bank:
      start=len(expected);expected.extend((prepared/record['payload']).read_bytes())
      if bank==4:expected.append(0xbb)
      assert new_frames[record['frame']]['images'][record['layer']]['offset']==start
    assert archive.read(archive_name+'/characters/annie'+suffix)==expected
  assert {p.name:sha(p) for p in (game/'data01').glob('*.gfs')}==original
  assert json.loads((prepared/'plan.json').read_text())['status']=='prepared' and not (project/'Backups').exists()
  expect_error(lambda:export_mod_zips(prepared,game/'bad'),'outside')
  passed.append('character mod ZIP contains verified complete patched assets in manager layout; game and preparation unchanged')
  # Exercise the actual metadata window through the existing ZIP worker.
  app=App();app.withdraw();app.project.set(str(project));app.prepared=prepared;app.plan=plan
  old_directory=ui.filedialog.askdirectory;ui.filedialog.askdirectory=lambda **kwargs:str(root/'Named mod ZIPs')
  try:
   app.start_mod_export();dialog=app.mod_dialog;dialog.withdraw()
   dialog.name.set('');dialog.submit();assert 'enter a mod name' in dialog.error.get() and not app.busy
   dialog.name.set('Annie — custom art');dialog.version.set('2.0-beta');dialog.description.delete('1.0','end');dialog.description.insert('1.0','First line\nSecond line: café')
   dialog.export_button.invoke();await_ui();assert not dialog.winfo_exists()
   named=next((root/'Named mod ZIPs').rglob('annie-sprites.zip'))
   with zipfile.ZipFile(named) as archive:
    custom=json.loads(archive.read('mod.json'))
    assert custom['name']=='Annie — custom art' and custom['version']=='2.0-beta' and custom['desc']=='First line\nSecond line: café'
    assert custom['id']==info['id'] and custom['author']==info['author']
    with zipfile.ZipFile(mod_folder/mods[0]['file']) as baseline:
     assert all(archive.read(n)==baseline.read(n) for n in archive.namelist() if n!='mod.json')
   app.start_mod_export();dialog=app.mod_dialog;dialog.withdraw();assert dialog.name.get()==custom['name'];dialog.destroy()
   assert {p.name:sha(p) for p in (game/'data01').glob('*.gfs')}==original
  finally:ui.filedialog.askdirectory=old_directory;app.destroy()
  passed.append('mod details window validates fields, retains drafts and exports Unicode multiline metadata with unchanged art and game files')
  app=App();app.withdraw();app.project.set(str(project));app.prepared=prepared;app.plan={'patches':[{'character':'annie'},{'character':'filia'}]}
  try:
   app.start_mod_export();dialog=app.mod_dialog;dialog.withdraw();dialog.name.set('Annie draft');dialog.version.set('3');dialog.description.delete('1.0','end')
   dialog.character_box.current(1);dialog.switch_character();assert dialog.name.get()=='Filia sprite replacements';dialog.name.set('Filia draft')
   dialog.character_box.current(0);dialog.switch_character();assert dialog.name.get()=='Annie draft' and dialog.version.get()=='3' and dialog.description.get('1.0','end-1c')==''
   captured=[];app.export_mods=lambda metadata:captured.append(metadata) or False
   dialog.submit();assert dialog.winfo_exists() and captured[0]['filia']['name']=='Filia draft' and captured[0]['annie']['desc']==''
   dialog.update_idletasks();assert dialog.winfo_reqheight()<=480;dialog.destroy();assert not app.busy
   from workshop import mod_details
   expect_error(lambda:mod_details('annie',{'version':'  '}),'enter a mod version')
   expect_error(lambda:export_mod_zips(prepared,root/'Invalid mod ZIPs',metadata={'annie':{'name':''}}),'enter a mod name')
   assert not (root/'Invalid mod ZIPs').exists()
  finally:app.destroy()
  passed.append('per-character metadata drafts stay separate; cancelling export preserves the dialog; invalid metadata creates no export folder')
  saved_input=(project/'Input'/route).read_bytes();(project/'Input'/route).write_bytes(saved_input+b'extra');expect_error(lambda:apply_import(prepared,check_running=False),'Input PNG changed');expect_error(lambda:export_mod_zips(prepared,root/'Mod ZIPs'),'Input PNG changed');(project/'Input'/route).write_bytes(saved_input);passed.append('stale Input refused')
  payload=prepared/plan['patches'][0]['payload'];saved=payload.read_bytes();payload.write_bytes(bytes([saved[0]^1])+saved[1:]);expect_error(lambda:apply_import(prepared,check_running=False),'payload was altered');expect_error(lambda:export_mod_zips(prepared,root/'Mod ZIPs'),'payload was altered');payload.write_bytes(saved);passed.append('tampered prepared payload refused')
  plan_file=prepared/'plan.json';saved_plan=plan_file.read_bytes();tampered=json.loads(saved_plan);tampered['patches'][0]['offset']+=1;write_json(plan_file,tampered);expect_error(lambda:apply_import(prepared,check_running=False),'art slot');plan_file.write_bytes(saved_plan);passed.append('tampered destination offset refused')
  protected=game/'data01'/'characters-foits.gfs';saved_metadata=protected.read_bytes();protected.write_bytes(saved_metadata[:-1]+b'X');expect_error(lambda:apply_import(prepared,check_running=False),'game files changed');protected.write_bytes(saved_metadata);passed.append('changed verified metadata refused')
  import workshop as engine
  original_check=engine.game_running
  try:
   engine.game_running=lambda:True;expect_error(lambda:apply_import(prepared),'Close Skullgirls')
  finally:engine.game_running=original_check
  passed.append('running game blocks writes')
  before={p.name:sha(p) for p in (game/'data01').glob('*.gfs')};assert before==original
  backup,receipt=apply_import(prepared,check_running=False);assert receipt['status']=='installed';assert sha(game/'data01'/'sprites.gfs')==original['sprites.gfs']
  with GFS(game/'data01'/'characters-foits.gfs') as changed,GFS(backup/'characters-foits.gfs') as old:
   old_data=old.read('characters/annie.foit');new_data=changed.read('characters/annie.foit');fs,positions=parse_frames_data('annie',old_data,100000,with_locations=True);allowed=set()
   for record in plan['patches']:
    for j,k in record['affected_references']:
     pos=positions[j,k];allowed.update(range(pos,pos+16));meta=fs[j]['images'][k]
     allowed.add(pos-len(bytes.fromhex(meta['mask']))-(8 if meta['flags']&4 else 0)-1)
   assert len(old_data)==len(new_data) and all(a==b or i in allowed for i,(a,b) in enumerate(zip(old_data,new_data)))
  passed.append('relocated apply verified; only art storage references change in metadata; palettes byte-identical')
  expect_error(lambda:apply_import(prepared,check_running=False),'no prepared replacements');passed.append('double apply refused')
  # Refuse restoring over newer modifications.
  path=game/'data01'/'characters-art.gfs';saved_archive=path.read_bytes();path.write_bytes(saved_archive[:-1]+bytes([saved_archive[-1]^1]));expect_error(lambda:restore_import(backup,check_running=False),'game has changed');path.write_bytes(saved_archive);passed.append('restore over newer changes refused')
  restore_import(backup,check_running=False);assert {p.name:sha(p) for p in (game/'data01').glob('*.gfs')}==original;passed.append('restore returns every archive to original hashes')
  for frame,color in [(1,[180,35,35,254]),(4,[35,80,180,254])]:
   rel=next(k for k,v in manifest['exports'].items() if v['frame']==frame);pixels=np.array(Image.open(project/'Output'/rel).convert('RGBA'));pixels[4:12,4:12]=color;Image.fromarray(pixels).save(project/'Input'/rel)
  prepared,plan=prepare_import(game,project);assert len(plan['patches'])==2 and len(plan['errors'])==2,plan;passed.append('conflicting edits to shared art are both skipped')
  # Exercise the preview widgets using a real prepared fixture plan.
  from workshop_app import App
  app=App();app.withdraw();app.project.set(str(project));app.game.set(str(game));app.events.put(('prepare',(prepared,plan)));app.poll();app.update_idletasks();assert len(app.photos)==2;assert 'disabled' not in app.apply_button.state();assert app.winfo_reqheight()<=900;app.destroy();passed.append('prepared previews and Apply control render within window')
  Image.new('RGBA',(16,16),(0,0,0,0)).save(project/'Input'/route);empty_prepared,empty_plan=prepare_import(game,project);empty_record=next(p for p in empty_plan['patches'] if p['frame']==0)
  with Image.open(empty_prepared/empty_record['after']) as im:assert im.getbbox() is None
  passed.append('fully transparent replacement fits original compression slots')
  cancel=threading.Event();cancel.set();_,cancelled_plan=prepare_import(game,project,cancel=cancel);assert cancelled_plan['status']=='cancelled' and not cancelled_plan['patches'];passed.append('cancelled preparation cannot apply')
  cancel=threading.Event();cancel.set();cancelled,m=export_project(game,root/'Projects',['annie'],cancel=cancel);assert m['status']=='cancelled';assert not list((cancelled/'Input').rglob('*.png'));passed.append('cancelled export leaves valid empty Input')
  review_regressions(root,passed)
  mod_zip_regressions(root,passed)
  relocation_regressions(root,passed)
  art_memory_regressions(root,passed)
  select_preview_regressions(root,passed)
  outline_matching_regressions(root,passed)
  approval_regressions(root,passed)
  result=dict(status='passed',native_cpu_available=codec.native_optimal is not None,checks=passed,project=str(project),game_fixture=str(game))
 except Exception as exc:
  import traceback
  result=dict(status='failed',checks=passed,error=str(exc),traceback=traceback.format_exc(),test_root=str(root));write_json(report,result);raise
 write_json(report,result);print(json.dumps(result,indent=2),flush=True);return result

def approval_regressions(root,passed):
 from unittest.mock import patch
 import match_review as review
 import workshop_app as ui
 from project_match import copy_matches
 area=root/'ReviewApproval';area.mkdir();game=fixture(area)
 source,sm=export_project(game,area/'Projects',['annie'],limit=4);target,tm=export_project(game,area/'Projects',['annie'],limit=4)
 routes={e['frame']:r for r,e in sm['exports'].items() if e['layer']==0}
 for frame,color in [(0,[200,20,20]),(1,[20,20,200])]:
  path=source/'Output'/routes[frame];pixels=np.array(Image.open(path).convert('RGBA'));pixels[:,:,:3]=color;Image.fromarray(pixels).save(path)
 def record(old,new):
  result=dict(character='annie',source_frame=old,target_frame=new,distance=2.,reason='Review this pose',copies=[])
  for route,e in sm['exports'].items():
   if e['frame']!=old or e['layer'] is None:continue
   tr=next(r for r,v in tm['exports'].items() if v['frame']==new and v['layer']==e['layer'])
   with Image.open(source/'Output'/route) as im:a=pixel_hash(im)
   with Image.open(target/'Output'/tr) as im:b=pixel_hash(im)
   result['copies'].append(dict(source=route,target=tr,source_sha256=sha(source/'Output'/route),target_sha256=sha(target/'Output'/tr),identical_pixels=a==b))
  return result
 def report(ready,uncertain):
  folder=unique(target/'Matches','Review fixture');data=dict(source=str(source),target=str(target),source_manifest_sha256=sha(source/'project.json'),target_manifest_sha256=sha(target/'project.json'),matches=ready,review=uncertain,unmatched=[],missing_exports=[],status='matched');write_json(folder/'matches.json',data);return folder
 r0=record(0,0);r1=record(1,1);r10=record(1,0);r3=record(3,3)
 original={str(p):sha(p) for root in [source,target] for p in (root/'Output').rglob('*.png')}
 folder=report([], [r0,r1]);keys=[review.key(r0),review.key(r1)]
 planned=review.approval_plan(folder,keys);assert not planned['conflicts']
 approved=review.approve(folder,keys,expected_sha256=planned['report_sha256'])
 assert len(approved['matches'])==2 and not approved['review'] and all(r['approved'] for r in approved['matches'])
 assert not list((target/'Input').rglob('*.png'))
 loaded,*_=review.load_report(folder);assert loaded['review_history'][-1]['action']=='approve'
 review.return_to_review(folder,keys);assert not review.load_report(folder)[0]['matches']
 review.approve(folder,keys);_,copied=copy_matches(folder);assert len(copied['copied'])==2
 passed.append('batch review approvals persist, return to review, and stage only after Copy ready; Output remains untouched')
 conflict=report([], [record(0,0),record(1,0)]);unchanged=(conflict/'matches.json').read_bytes()
 expect_error(lambda:review.approve(conflict,[review.key(r0),review.key(r10)]),'one variant per target');assert (conflict/'matches.json').read_bytes()==unchanged
 conflict=report([record(0,0)],[record(1,0)]);unchanged=(conflict/'matches.json').read_bytes()
 expect_error(lambda:review.approve(conflict,[review.key(r10)]),'conflicts');assert (conflict/'matches.json').read_bytes()==unchanged
 plan=review.approval_plan(conflict,[review.key(r10)]);assert plan['conflicts'] and plan['overwrites']
 chosen=review.approve(conflict,[review.key(r10)],True,plan['report_sha256'])
 assert chosen['matches'][0]['source_frame']==1 and chosen['review'][0]['source_frame']==0
 target_route=r10['copies'][0]['target'];old_bytes=(target/'Input'/target_route).read_bytes()
 _,switched=copy_matches(conflict);assert len(switched['approved_replaced'])==1
 assert (Path(switched['approval_backup'])/target_route).read_bytes()==old_bytes
 assert (target/'Input'/target_route).read_bytes()==(source/'Output'/r10['copies'][0]['source']).read_bytes()
 review.return_to_review(conflict,[review.key(r10)])
 plan=review.approval_plan(conflict,[review.key(r0)]);assert plan['input_conflicts'] and not plan['conflicts']
 review.approve(conflict,[review.key(r0)],True,plan['report_sha256'])
 edited=target/'Input'/target_route;edited.write_bytes(b'preserve my later edit');_,protected=copy_matches(conflict)
 assert protected['existing']==[target_route] and edited.read_bytes()==b'preserve my later edit'
 passed.append('shared-target choices require explicit replacement, demote other ready variants, back up staged copies and preserve later Input edits')
 invalid=record(3,3);invalid['copies']=invalid['copies'][:1];bad=report([], [invalid]);saved=(bad/'matches.json').read_bytes()
 expect_error(lambda:review.approve(bad,[review.key(invalid)]),'incomplete');assert (bad/'matches.json').read_bytes()==saved
 stale=report([], [record(0,0)]);saved=(stale/'matches.json').read_bytes();source_png=source/'Output'/r0['copies'][0]['source'];saved_png=source_png.read_bytes();source_png.write_bytes(saved_png+b'changed')
 expect_error(lambda:review.approve(stale,[review.key(r0)]),'PNG changed');source_png.write_bytes(saved_png)
 expect_error(lambda:review.approve(stale,[review.key(r0)],expected_sha256='0'*64),'report changed')
 assert (stale/'matches.json').read_bytes()==saved
 original_replace=Path.replace
 def fail_report(path,destination):
  if Path(destination)==stale/'matches.json':raise OSError('injected report write failure')
  return original_replace(path,destination)
 with patch.object(Path,'replace',fail_report):expect_error(lambda:review.approve(stale,[review.key(r0)]),'injected report')
 assert (stale/'matches.json').read_bytes()==saved
 passed.append('approval rejects incomplete layers, stale PNGs and changed report revisions; interrupted saves preserve the previous report')
 # Exercise the real UI controls, saved-report loading and layer previews.
 ui_folder=report([], [record(0,0),record(1,1)]);layer_folder=report([], [record(3,3)]);clash_folder=report([record(0,0)],[record(1,0)])
 settings=json.loads((ui_folder/'matches.json').read_text());settings['min_overlap']=.87;write_json(ui_folder/'matches.json',settings)
 before_input={str(p):sha(p) for p in (target/'Input').rglob('*.png')};errors=[]
 app=ui.App();app.geometry('930x900');app.tabs.select(2)
 try:
  with patch.object(ui.messagebox,'showerror',side_effect=lambda *a:errors.append(a)):
   with patch.object(ui.filedialog,'askopenfilename',return_value=str(ui_folder/'matches.json')):app.load_report_button.invoke()
   app.update();assert app.match_folder==ui_folder and app.overlap_label.get()=='87%'
   app.overlap.set(95);assert app.match_folder==ui_folder and len(app.match_report['review'])==2
   app.match_table.selection_set('review-0');app.refresh_review_buttons();assert 'disabled' not in app.approve_button.state()
   app.open_match_preview();app.update();dialog=app.match_preview;assert len(dialog.photos)==2
   dialog.approve_button.invoke();app.update();assert len(app.match_report['matches'])==1 and 'Nothing copied yet' in app.status.get()
   app.match_table.selection_set('review-0');app.refresh_review_buttons();app.approve_button.invoke();assert len(app.match_report['matches'])==2
   app.match_table.selection_set(['matches-0','matches-1']);app.refresh_review_buttons();app.unapprove_button.invoke();assert not app.match_report['matches']
   app.match_table.selection_set(['review-0','review-1']);app.refresh_review_buttons();app.approve_button.invoke();assert len(app.match_report['matches'])==2
   with patch.object(ui.filedialog,'askopenfilename',return_value=str(ui_folder/'matches.json')):app.load_report_button.invoke()
   assert all(r['approved'] for r in app.match_report['matches'])
   with patch.object(ui.filedialog,'askopenfilename',return_value=str(layer_folder/'matches.json')):app.load_report_button.invoke()
   assert app.overlap_label.get()=='94%'
   app.match_table.selection_set('review-0');app.open_match_preview();dialog=app.match_preview;assert len(dialog.layer_box['values'])==3
   dialog.view.set('Layer 1');dialog.select_view();assert len(dialog.photos)==2;dialog.destroy()
   with patch.object(ui.filedialog,'askopenfilename',return_value=str(clash_folder/'matches.json')):app.load_report_button.invoke()
   app.match_table.selection_set('review-0');app.refresh_review_buttons();saved=(clash_folder/'matches.json').read_bytes()
   with patch.object(ui.messagebox,'askyesno',return_value=False):app.approve_button.invoke()
   assert (clash_folder/'matches.json').read_bytes()==saved
   with patch.object(ui.messagebox,'askyesno',return_value=True):app.approve_button.invoke()
   assert app.match_report['matches'][0]['source_frame']==1
   app.update();assert app.winfo_reqheight()<=900
   assert app.unapprove_button.winfo_x()+app.unapprove_button.winfo_width()<=app.copy_button.winfo_x()
   assert not errors,errors
   assert {str(p):sha(p) for p in (target/'Input').rglob('*.png')}==before_input
   app.match_target.set('changed project');assert 'disabled' in app.approve_button.state() and not app.match_rows
 finally:app.destroy()
 assert all(sha(Path(p))==digest for p,digest in original.items())
 passed.append('actual preview, approve, return, reload and conflict-choice controls persist decisions, fit the window and never copy Input implicitly')


def outline_matching_regressions(root,passed):
 from PIL import ImageDraw
 from layout import descriptor
 from project_match import project_descriptor,match_projects,copy_matches
 area=root/'OutlineMatching';area.mkdir();game=fixture(area)
 pose=Image.new('RGBA',(32,32));d=ImageDraw.Draw(pose)
 d.polygon([(15,1),(22,7),(26,14),(20,18),(27,29),(17,30),(14,22),(10,30),(3,29),(8,18),(4,13),(10,7)],fill='white')
 revised=pose.copy();d=ImageDraw.Draw(revised)
 for x,y in [(5,13),(24,14)]:d.rectangle((x,y,x+1,y+1),fill=(0,0,0,0))
 # Two small edge revisions previously cost more than dropping the frame.
 assert np.linalg.norm(descriptor(pose)-descriptor(revised))>2.5
 assert np.linalg.norm(project_descriptor(pose)-project_descriptor(revised))<1.5
 assert descriptor(pose)[-1]==project_descriptor(pose)[-1]
 blank=Image.new('RGBA',(32,32));assert project_descriptor(blank) is None
 wide=blank.copy();ImageDraw.Draw(wide).rectangle((2,10,29,20),fill='white')
 tall=blank.copy();ImageDraw.Draw(tall).rectangle((13,1,18,30),fill='white')
 extra=blank.copy();ImageDraw.Draw(extra).rectangle((1,15,30,18),fill='white')
 def project(images):
  p,m=export_project(game,area/'Projects',['annie'],limit=1);m['exports']={}
  for frame,image in images:
   route=f'annie/annie/data/unmapped/internal_frames/frames/frame_{frame:04d}_annie_1p.png'
   destination=safe_path(p/'Output',route);destination.parent.mkdir(parents=True,exist_ok=True);image.save(destination)
   m['exports'][route]=dict(character='annie',frame=frame,layer=0,art_bank=5,size=list(image.size),pixel_sha256=pixel_hash(image),match_distance=None)
  write_json(p/'project.json',m);return p,m
 source,sm=project([(0,blank),(10,wide),(14,pose),(20,tall)])
 target,tm=project([(0,blank),(10,wide),(14,revised),(17,extra),(21,tall)])
 before={str(p):sha(p) for root in [source,target] for p in (root/'Output').rglob('*.png')}
 folder,result=match_projects(source,target)
 assert [(r['source_frame'],r['target_frame']) for r in result['matches']]==[(0,0),(10,10),(14,14),(20,21)],result
 assert not result['review'] and not result['unmatched'] and all(c['identical_pixels'] for r in result['matches'] if r['source_frame']==0 for c in r['copies'])
 assert result['matching_method']=='registered-pose-v2'
 assert all(sha(Path(p))==digest for p,digest in before.items())
 assert not list((source/'Input').rglob('*.png')) and not list((target/'Input').rglob('*.png'))
 passed.append('cross-version edge revisions match frame 14 and preserve sequence insertions, aspect ratio, transparent no-copy matches and untouched PNGs')
 _,strict=match_projects(source,target,min_overlap=1.)
 assert strict['min_overlap']==1. and any(r['source_frame']==14 and 'below the selected 100%' in r['reason'] for r in strict['review'])
 assert {r['source_frame'] for r in strict['matches']}=={0,10,20}
 _,tolerant=match_projects(source,target,min_overlap=.5)
 assert len(tolerant['matches'])==4 and not tolerant['review']
 for value in [.49,1.01,float('nan')]:expect_error(lambda:match_projects(source,target,min_overlap=value),'between 50% and 100%')
 passed.append('selected overlap minimum gates sequence pairs as well as recovered poses; exact and transparent shapes pass 100%, invalid thresholds fail')
 # Softening edges must not force unrelated silhouettes or ambiguous duplicates.
 wrong,_=project([(14,wide)]);_,mismatch=match_projects(source,wrong)
 assert all(r['source_frame']!=14 for r in mismatch['matches'])
 tinted=pose.copy();tinted.paste((200,20,20,255),(0,0,32,32),pose.getchannel('A'))
 duplicate_source,_=project([(50,pose)]);duplicate_target,_=project([(51,pose),(52,tinted)])
 _,ambiguous=match_projects(duplicate_source,duplicate_target)
 assert not ambiguous['matches'] and any('neighboring' in r['reason'] for r in ambiguous['review'])
 passed.append('soft project matching still rejects unrelated aspect ratios and reviews ambiguous neighboring poses')
 route=next(r for r,e in tm['exports'].items() if e['frame']==14)
 overlay=route.replace('.png','_layer1.png');shutil.copy2(target/'Output'/route,target/'Output'/overlay)
 tm['exports'][overlay]={**tm['exports'][route],'layer':1};write_json(target/'project.json',tm)
 _,layered=match_projects(source,target)
 assert any(r['source_frame']==14 and r['reason']=='Editable layers differ between versions' for r in layered['review'])
 passed.append('cross-version outline tolerance preserves editable-layer mismatch review')
 # An emblem extending the bounding box must not rescale the whole pose.
 extended=Image.new('RGBA',(64,32));extended.paste(pose,(0,0));extended.putpixel((50,15),(255,255,255,255))
 assert np.linalg.norm(project_descriptor(pose)-project_descriptor(extended))>2.5
 native_source,_=project([(383,pose)]);native_target,_=project([(388,extended)])
 _,native=match_projects(native_source,native_target)
 assert not native['unmatched'] and len(native['matches'])==1 and native['matches'][0]['registered_overlap']>.98,native
 _,strict_native=match_projects(native_source,native_target,min_overlap=1.)
 assert not strict_native['matches'] and len(strict_native['review'])==1
 passed.append('native-size registration recovers a pose whose small protrusion changes the normalized bounding box')
 # A reordered pose and repeated identical art can share one target safely.
 red=tall.copy();red.paste((200,20,20,255),(0,0,32,32),tall.getchannel('A'))
 reordered_source,_=project([(10,wide),(14,pose),(20,red),(21,red)])
 reordered_target,_=project([(10,wide),(11,tall),(14,pose)])
 rf,reordered=match_projects(reordered_source,reordered_target)
 assert {r['source_frame']:r['target_frame'] for r in reordered['matches']}=={10:10,14:14,20:11,21:11},reordered
 assert not reordered['unmatched'] and not reordered['review']
 _,copied=copy_matches(rf);assert len(copied['copied'])==1 and not copied['existing'],copied
 passed.append('reordered and repeated identical source artwork recovers many-to-one matches and stages each destination only once')
 # Same silhouette does not justify discarding a different source variant.
 blue=tall.copy();blue.paste((20,20,200,255),(0,0,32,32),tall.getchannel('A'))
 variant_source,_=project([(20,red),(21,blue)]);variant_target,_=project([(30,tall)])
 vf,variants=match_projects(variant_source,variant_target)
 assert len(variants['matches'])==1 and len(variants['review'])==1 and 'shares this target' in variants['review'][0]['reason'],variants
 variants['matches'].extend(variants['review']);variants['review']=[];write_json(vf/'matches.json',variants)
 expect_error(lambda:copy_matches(vf),'same target')
 assert not list((variant_target/'Input').rglob('*.png'))
 passed.append('different source variants sharing a target remain in review; conflicting copy plans fail before any Input writes')
 faint=pose.copy();faint.putalpha(pose.getchannel('A').point([0]+[32]*255))
 brighter=pose.copy();brighter.putalpha(pose.getchannel('A').point([0]+[64]*255))
 assert project_descriptor(faint) is None and project_descriptor(brighter) is None
 faint_source,_=project([(40,faint)]);faint_target,_=project([(50,brighter)])
 _,faded=match_projects(faint_source,faint_target)
 assert not faded['unmatched'] and not faded['review'] and faded['matches'][0]['registered_overlap']>.99
 assert not faded['matches'][0]['copies'][0]['identical_pixels']
 passed.append('relative opacity recovers faint effects below the old alpha cutoff without treating visible artwork as blank')


def select_preview_regressions(root,passed):
 from select_preview import pack,unpack,read_preview,build_preview,EMPTY
 from unittest.mock import patch
 import repacking
 import select_preview
 area=root/'SelectPreview';area.mkdir();game=fixture(area);source=game/'data01'
 for path in source.glob('*.gfs'):
  with GFS(path) as a:entries={k.replace('annie','filia'):a.read(k) for k in a.entries}
  make_gfs(path,entries)
 with GFS(source/'characters-art.gfs') as a,GFS(source/'characters-foits.gfs') as f:
  main=a.read('characters/filia.art');frames=parse_frames_data('filia',f.read('characters/filia.foit'),len(main))
 raw=decode_image(frames[1]['images'][0],main);canvas=pack(raw)
 def text(s):return struct.pack('>Q',len(s))+s
 sprite=text(b'2.0')+text(b'character_select_filia')+struct.pack('>I',25)+text(b'unigned char tile_x, tile_y, tile_u, tile_v;')
 count_pos=len(sprite)+8
 header=sprite+struct.pack('>6Q',4,2,2,1,16,16)
 tail=b'original animation names and loop metadata'
 records=[(0,1,4,3.5,7.25),(1,1,7,-2.,9.)]
 sprite=header+bytes([0,0,0,0])*2+b''.join(struct.pack('>IIIff',*r) for r in records)+tail
 dds=bytearray(128);dds[:4]=b'DDS ';struct.pack_into('<I',dds,4,124);struct.pack_into('<III',dds,12,16,16,32)
 struct.pack_into('<8I',dds,76,32,64,0,16,0xf800,0x7e0,0x1f,0)
 dds=bytes(dds)+canvas.astype('<u2').tobytes()
 with GFS(source/'sprites.gfs') as a:entries={k:a.read(k) for k in a.entries}
 entries.update({'sprites/character_select_filia.spr.msb':sprite,'sprites/character_select_filia.dds':dds,'sprites/unrelated.dds':b'unrelated menu art'})
 make_gfs(source/'sprites.gfs',entries)
 project,manifest=export_project(game,area/'Projects',['filia'],limit=2)
 route=next(r for r,e in manifest['exports'].items() if e['frame']==1)
 pixels=np.array(Image.open(project/'Output'/route).convert('RGBA'));pixels[3:12,3:12]=[220,45,45,254];Image.fromarray(pixels).save(project/'Input'/route)
 prepared,plan=prepare_import(game,project);assert len(plan['patches'])==1 and not plan['errors'],plan
 original={p.name:sha(p) for p in source.glob('*.gfs')}
 folder,result=export_mod_zips(prepared,area/'Mods')
 with zipfile.ZipFile(folder/result[0]['file']) as z:
  newsprite=z.read('sprites.gfs/sprites/character_select_filia.spr.msb');newdds=z.read('sprites.gfs/sprites/character_select_filia.dds')
  decoded,newrecords,newheader,newcount,newtail=read_preview(newsprite,newdds)
  assert not np.array_equal(decoded[0],canvas) and np.array_equal(decoded[1],canvas)
  assert [r[2:] for r in newrecords]==[r[2:] for r in records] and newtail==tail
  assert newheader[:count_pos]==header[:count_pos] and newheader[count_pos+8:]==header[count_pos+8:]
  # The update uses the actual encoded result, including transparency/outline.
  foit=z.read('characters-foits.gfs/characters/filia.foit');art=z.read('characters-art.gfs/characters/filia.art')
  updated=parse_frames_data('filia',foit,len(art));expected=pack(decode_image(updated[1]['images'][0],art))
  assert np.array_equal(decoded[0],expected)
 assert {p.name:sha(p) for p in source.glob('*.gfs')}==original
 passed.append('Filia menu ZIP uses encoded idle art, preserves untouched frames, timing, origins and animation metadata; export is read-only')
 backup,receipt=apply_import(prepared,check_running=False)
 assert 'sprites.gfs' in receipt['before'] and 'sprites.gfs' not in receipt['protected']
 with GFS(source/'sprites.gfs') as a:
  assert a.read('sprites/character_select_filia.spr.msb')==newsprite and a.read('sprites/character_select_filia.dds')==newdds
  assert a.read('sprites/unrelated.dds')==entries['sprites/unrelated.dds'] and a.read('sprites/filia_1p.dds')==entries['sprites/filia_1p.dds']
 assert project_info(project)[1]['palette_archive_sha256']==sha(source/'sprites.gfs')
 restore_import(backup,check_running=False);assert {p.name:sha(p) for p in source.glob('*.gfs')}==original
 passed.append('direct Apply includes backed-up menu atlas, preserves every unrelated texture and palette, and Restore recovers exact archive bytes')
 prepared,plan=prepare_import(game,project)
 original_replace=Path.replace;calls=[]
 def fail_menu(path,target):
  if Path(target).resolve()==(source/'sprites.gfs').resolve():raise OSError('injected menu install failure')
  return original_replace(path,target)
 with patch.object(Path,'replace',fail_menu):expect_error(lambda:apply_import(prepared,check_running=False),'injected menu')
 assert {p.name:sha(p) for p in source.glob('*.gfs')}==original
 passed.append('menu install failure rolls back all character archives and the menu archive')
 with patch.object(select_preview,'signature',side_effect=[np.zeros((2,2,4)),np.ones((2,2,4))]):
  expect_error(lambda:export_mod_zips(prepared,area/'Refused'),'Cannot verify')
 assert {p.name:sha(p) for p in source.glob('*.gfs')}==original
 passed.append('mismatched menu artwork refuses synchronization before any game writes')
 # Atlas growth and transparency must not corrupt 8-bit tile coordinates.
 blank=np.full((16,16),EMPTY,np.uint16)
 built=build_preview([blank,canvas],records,header,count_pos,tail,dds,'sprites/check')
 cs,rs,*_=read_preview(built['sprites.gfs/sprites/check.spr.msb'],built['sprites.gfs/sprites/check.dds'])
 assert np.array_equal(cs[0],blank) and np.array_equal(cs[1],canvas)
 expect_error(lambda:read_preview(sprite,dds[:128]+b'bad'),'dimensions')
 bad=bytearray(dds);struct.pack_into('<I',bad,80,4);expect_error(lambda:read_preview(sprite,bad),'RGB565')
 passed.append('menu atlas grows for new tiles, round-trips blank frames, and rejects truncated or unsupported textures')


def art_memory_regressions(root,passed):
 import zipfile
 from unittest.mock import patch
 from repacking import art_memory_fields,character_assets
 folder=root/'ArtMemory';folder.mkdir();game=fixture(folder);data=game/'data01'
 with GFS(data/'characters-foits.gfs') as archive:original=archive.read('characters/annie.foit')
 sizes={}
 for bank,(archive,suffix) in ART_FILES.items():
  with GFS(data/archive) as packed:sizes[bank]=len(packed.read('characters/annie'+suffix))
 label=b'annie_1p.pal'
 table=struct.pack('<5iH',101,102,sizes[5],sizes[4],103,1)+bytes([len(label)])+label
 metadata=original[:16]+table+original[16:]
 make_gfs(data/'characters-foits.gfs',{'characters/annie.foit':metadata,'untouched.bin':b'untouched'})
 fields=art_memory_fields(metadata,'annie');assert fields=={5:24,4:28}
 assert not art_memory_fields(metadata[:35],'annie') and not art_memory_fields(metadata,'filia')
 assert not art_memory_fields(metadata+bytes([len(label)])+label,'annie')
 bad=bytearray(metadata);struct.pack_into('<H',bad,36,257);assert not art_memory_fields(bad,'annie')
 for version in [3,10]:
  bad=bytearray(metadata);struct.pack_into('<I',bad,8,version);assert not art_memory_fields(bad,'annie')
 assert not art_memory_fields(b'legacy'+metadata[6:],'annie')
 passed.append('art-memory lookup validates VRSN 9 and complete unique palette tables; truncated and unsupported layouts stay unchanged')
 project,manifest=export_project(game,folder/'Projects',['annie'])
 for index in [0,2]:
  route=next(k for k,v in manifest['exports'].items() if v['frame']==index)
  with Image.open(project/'Output'/route) as image:pixels=np.array(image.convert('RGBA'))
  pixels[4:12,4:12]=[180,35,35,254];Image.fromarray(pixels).save(project/'Input'/route)
 prepared,plan=prepare_import(game,project);assert len(plan['patches'])==2 and not plan['errors']
 baseline={p.name:sha(p) for p in data.glob('*.gfs')}
 output,mods=export_mod_zips(prepared,folder/'Mods')
 with zipfile.ZipFile(output/mods[0]['file']) as archive:assets={p:archive.read(p) for p in archive.namelist() if p!='mod.json'}
 changed=assets['characters-foits.gfs/characters/annie.foit']
 parsed=parse_frames_data('annie',changed,len(assets['characters-art.gfs/characters/annie.art']))
 streamed=assets['characters-art-pt.gfs/characters/annie.art-pt']
 for frame in parsed:
  if frame['art_bank']!=4:continue
  for image in frame['images'].values():
   if image['offset']>=0:assert streamed[image['offset']+sum(image['sizes'])]==0xbb
 # Model the actual renderer's completion check, which the preview decoder
 # does not perform. The old exporter left EOF or another RLE packet here.
 target=next(r for r in plan['patches'] if r['art_bank']==4)
 image=parsed[target['frame']]['images'][target['layer']];end=image['offset']+sum(image['sizes'])
 missing=streamed[:end]+b'\0'+streamed[end+1:]
 assert missing[end]!=0xbb and streamed[end]==0xbb
 passed.append('every streamed layer retains its runtime 0xBB completion marker outside compressed channel lengths')
 allowed=set()
 for bank,(archive,suffix) in ART_FILES.items():
  size=len(assets[archive+'/characters/annie'+suffix]);assert size>sizes[bank]
  assert struct.unpack_from('<i',changed,fields[bank])[0]==size
  allowed.update(range(fields[bank],fields[bank]+4))
 frames,positions=parse_frames_data('annie',metadata,sizes[5],with_locations=True)
 for record in plan['patches']:
  for key in map(tuple,record['affected_references']):
   pos=positions[key];allowed.update(range(pos,pos+16));meta=frames[key[0]]['images'][key[1]]
   allowed.add(pos-len(bytes.fromhex(meta['mask']))-(8 if meta['flags']&4 else 0)-1)
 assert len(metadata)==len(changed) and all(a==b or i in allowed for i,(a,b) in enumerate(zip(metadata,changed)))
 assert {p.name:sha(p) for p in data.glob('*.gfs')}==baseline
 passed.append('mod ZIP grows both art-memory sizes while preserving all non-storage metadata and source archives')
 # Oversized reservations are retained rather than reduced to payload length.
 reserved=bytearray(metadata)
 for pos in fields.values():struct.pack_into('<i',reserved,pos,1_000_000)
 make_gfs(data/'characters-foits.gfs',{'characters/annie.foit':reserved,'untouched.bin':b'untouched'})
 large=character_assets(data,prepared,'annie',plan['patches'])['characters-foits.gfs/characters/annie.foit']
 assert all(struct.unpack_from('<i',large,pos)[0]==1_000_000 for pos in fields.values())
 make_gfs(data/'characters-foits.gfs',{'characters/annie.foit':metadata,'untouched.bin':b'untouched'})
 passed.append('relocation preserves larger existing art-memory reservations')
 replace=Path.replace;installs=[]
 def fail_second(path,target):
  if path.parent.name.startswith('.workshop-import-'):
   installs.append(path)
   if len(installs)==2:raise OSError('injected memory-size install failure')
  return replace(path,target)
 with patch.object(Path,'replace',fail_second):expect_error(lambda:apply_import(prepared,check_running=False),'injected memory-size')
 assert {p.name:sha(p) for p in data.glob('*.gfs')}==baseline
 backup,receipt=apply_import(prepared,check_running=False);assert receipt['status']=='installed'
 for archive in plan['source_hashes']:
  with GFS(data/archive) as packed:
   for route,content in assets.items():
    if route.startswith(archive+'/'):assert packed.read(route.split('/',1)[1])==content
 restore_import(backup,check_running=False)
 assert {p.name:sha(p) for p in data.glob('*.gfs')}==baseline
 passed.append('direct Apply matches ZIP art and size metadata; failed install rolls back; Restore returns every original archive byte')


def relocation_regressions(root,passed):
 """A detailed translucent edit must grow, not be recolored to fit 12 bytes."""
 from compression import header
 from unittest.mock import patch
 import repacking
 root=root/'Oversized';root.mkdir();game=fixture(root);data=game/'data01'
 with GFS(data/'characters-foits.gfs') as archive:metadata=bytearray(archive.read('characters/annie.foit'))
 frames,positions=parse_frames_data('annie',metadata,100000,with_locations=True)
 streams=[header(256,True)+bytes([v]) for v in [0,0,1]]
 with GFS(data/'characters-art.gfs') as archive:bank=bytearray(archive.read('characters/annie.art'))
 bank[:12]=b''.join(streams);struct.pack_into('<4i',metadata,positions[0,0],0,4,4,4);metadata[positions[0,0]-2]|=64
 make_gfs(data/'characters-art.gfs',{'characters/annie.art':bank,'untouched.bin':b'unchanged payload'})
 make_gfs(data/'characters-foits.gfs',{'characters/annie.foit':metadata,'untouched.bin':b'unchanged metadata'})
 with GFS(data/'sprites.gfs') as archive:
  with Image.open(io.BytesIO(archive.read('sprites/annie_1p.dds'))) as image:palette=np.array(image.convert('RGBA'))
 palette[3,:,3]=192;dds=io.BytesIO();Image.fromarray(palette).save(dds,format='DDS');make_gfs(data/'sprites.gfs',{'sprites/annie_1p.dds':dds.getvalue()})
 project,manifest=export_project(game,root/'Projects',['annie'],limit=1);route=next(iter(manifest['exports']))
 raw=np.zeros((16,16,3),np.uint8);rng=np.random.default_rng(734);raw[:,:,1]=rng.integers(0,32,(16,16));raw[:,:,2]=rng.integers(1,4,(16,16))
 expected=np.array(colorize(raw,palette));Image.fromarray(expected).save(project/'Input'/route)
 baseline={p.name:sha(p) for p in data.glob('*.gfs')}
 prepared,plan=prepare_import(game,project);assert not plan['errors'] and len(plan['patches'])==1
 record=plan['patches'][0];assert record['bytes']>12
 with Image.open(prepared/record['after']) as preview:assert np.array_equal(np.array(preview),expected)
 assert not record['warnings'] and record['statistics']['brightness_levels']==32 and not record['encoded_flags']&64
 # Reject fabricated channel sizes, even if the payload hash is still valid.
 saved=(prepared/'plan.json').read_bytes();record['encoded_sizes'][1]+=1;write_json(prepared/'plan.json',plan)
 expect_error(lambda:validate_prepared(prepared),'art slot');(prepared/'plan.json').write_bytes(saved)
 # Fail after the first archive replacement and prove full rollback.
 replace=Path.replace;calls=[]
 def fail_second(path,target):
  if path.parent.name.startswith('.workshop-import-'):
   calls.append(path)
   if len(calls)==2:raise OSError('injected install failure')
  return replace(path,target)
 with patch.object(Path,'replace',fail_second):expect_error(lambda:apply_import(prepared,check_running=False),'injected install failure')
 assert {p.name:sha(p) for p in data.glob('*.gfs')}==baseline
 backup,receipt=apply_import(prepared,check_running=False)
 with GFS(data/'characters-art.gfs') as art,GFS(data/'characters-foits.gfs') as foit:
  assert art.read('untouched.bin')==b'unchanged payload' and foit.read('untouched.bin')==b'unchanged metadata'
  fs=parse_frames_data('annie',foit.read('characters/annie.foit'),len(art.read('characters/annie.art')))
  decoded=decode_image(fs[0]['images'][0],art.read('characters/annie.art'))
  assert np.array_equal(np.array(colorize(decoded,palette)),expected)
  assert np.all(decoded[:,:,0]==0)
 # The same project remains usable after its own pointer updates.
 _,again=prepare_import(game,project);assert not again['patches'] and not again['errors']
 restore_import(backup,check_running=False);assert {p.name:sha(p) for p in data.glob('*.gfs')}==baseline
 _,again=prepare_import(game,project);assert len(again['patches'])==1 and not again['errors']
 passed.append('oversized translucent artwork grows without color correction; exact rendered pixels, untouched assets, rollback and restore verified')


def mod_zip_regressions(root,passed):
 import zipfile,time
 from unittest.mock import patch
 import workshop_app as ui
 game=fixture(root/'ModFixtures')
 for path in (game/'data01').glob('*.gfs'):
  with GFS(path) as archive:entries={k:archive.read(k) for k in archive.entries}
  entries.update({k.replace('annie','filia'):v for k,v in list(entries.items())});make_gfs(path,entries)
 project,manifest=export_project(game,root/'ModProjects',['annie','filia'],limit=3)
 for route,entry in manifest['exports'].items():
  if entry['frame'] not in [0,2]:continue
  pixels=np.array(Image.open(project/'Output'/route).convert('RGBA'));pixels[4:12,4:12]=[220,45,45,254];Image.fromarray(pixels).save(project/'Input'/route)
 prepared,plan=prepare_import(game,project);assert len(plan['patches'])==4 and not plan['errors']
 before={p.name:sha(p) for p in (game/'data01').glob('*.gfs')}
 folder,records=export_mod_zips(prepared,root/'MultiMods');assert {r['character'] for r in records}=={'annie','filia'}
 ids=[]
 for record in records:
  with zipfile.ZipFile(folder/record['file']) as archive:
   ids.append(json.loads(archive.read('mod.json'))['id'])
   assert all(record['character'] in name for name in archive.namelist() if name!='mod.json')
 assert len(set(ids))==2
 cancelled=threading.Event()
 def cancel_after_first(done,total,label):
  if done==1:cancelled.set()
 try:export_mod_zips(prepared,root/'CancelledMods',cancel_after_first,cancelled)
 except Cancelled:pass
 else:raise AssertionError('Mod ZIP cancellation was ignored')
 assert not list((root/'CancelledMods').iterdir())
 # Legacy entry names must remain temp paths in manager packages.
 modern_archives={p.name:p.read_bytes() for p in (game/'data01').glob('*.gfs')}
 for path in (game/'data01').glob('*.gfs'):
  with GFS(path) as archive:entries={k.replace('characters/','temp/').replace('sprites/','temp/true_color_sprites/'):archive.read(k) for k in archive.entries}
  if path.name=='characters-foits.gfs':entries={k:v[:8]+struct.pack('<I',3)+v[12:] for k,v in entries.items()}
  make_gfs(path,entries)
 legacy,legacy_manifest=export_project(game,root/'ModProjects',['annie'],limit=1)
 route=next(iter(legacy_manifest['exports']));pixels=np.array(Image.open(legacy/'Output'/route).convert('RGBA'));pixels[4:12,4:12]=[220,45,45,254];Image.fromarray(pixels).save(legacy/'Input'/route)
 lp,_=prepare_import(game,legacy);lf,lr=export_mod_zips(lp,root/'LegacyMods')
 with zipfile.ZipFile(lf/lr[0]['file']) as archive:assert 'characters-art.gfs/temp/annie.art' in archive.namelist()
 for name,content in modern_archives.items():(game/'data01'/name).write_bytes(content)
 assert {p.name:sha(p) for p in (game/'data01').glob('*.gfs')}==before
 prepared,plan=prepare_import(game,project)
 app=ui.App();app.project.set(str(project));app.game.set(str(game));app.geometry('930x900');app.tabs.select(1);app.events.put(('prepare',(prepared,plan)))
 deadline=time.monotonic()+10
 while app.plan is None:
  app.update();time.sleep(.01);assert time.monotonic()<deadline
 errors=[]
 try:
  assert 'disabled' not in app.mod_button.state()
  assert app.mod_button.winfo_x()+app.mod_button.winfo_width()<=app.apply_button.winfo_x()
  assert app.mod_button.winfo_x()>=app.prepare_button.winfo_x()+app.prepare_button.winfo_width()
  with patch.object(ui.filedialog,'askdirectory',return_value=str(root/'UIMods')),patch.object(ui.messagebox,'showerror',side_effect=lambda *a:errors.append(a)):
   app.mod_button.invoke();app.mod_dialog.export_button.invoke();deadline=time.monotonic()+20
   while app.busy:
    app.update();time.sleep(.01);assert time.monotonic()<deadline
  assert not errors and 'Saved 2 character mod ZIPs' in app.status.get(),errors
  assert 'disabled' not in app.mod_button.state() and 'disabled' not in app.apply_button.state()
  app.project.set(str(root));assert 'disabled' in app.mod_button.state()
 finally:app.destroy()
 passed.append('per-character mod ZIPs isolate assets, preserve legacy paths, cancel cleanly, and export through adjacent UI button')


def review_regressions(root,passed):
 from unittest.mock import patch
 import workshop as engine
 import project_match as matching
 import layout
 root=root/'Recovery';root.mkdir();game=fixture(root)
 project,manifest=export_project(game,root/'Projects',['annie'],limit=3)
 routes=[]
 for index in [0,2]:
  route=next(r for r,e in manifest['exports'].items() if e['frame']==index);routes.append(route)
  with Image.open(project/'Output'/route) as im:pixels=np.array(im.convert('RGBA'))
  pixels[4:12,4:12]=[180,35,35,254];Image.fromarray(pixels).save(project/'Input'/route)
 prepared,plan=prepare_import(game,project);assert len(plan['patches'])==2
 # The relocation path rebuilds complete assets and verifies untouched entries.
 backup,receipt=apply_import(prepared,check_running=False)
 original_copy=shutil.copy2;calls=[]
 def fail_second(src,dst,*args,**kwargs):
  calls.append(src)
  if len(calls)==2:
   Path(dst).write_bytes(b'partial');raise OSError('injected restore interruption')
  return original_copy(src,dst,*args,**kwargs)
 with patch.object(engine.shutil,'copy2',fail_second):
  expect_error(lambda:restore_import(backup,check_running=False),'injected restore')
 saved=json.loads((backup/'restore.json').read_text());assert saved['status']=='restoring'
 names=list(receipt['after']);data=game/'data01'
 assert sha(data/names[0])==receipt['before'][names[0]]
 assert sha(data/names[1])==receipt['after'][names[1]]
 assert not list(data.glob('*.restore-*'))
 # Resumption must still reject unrelated changes.
 original=(data/names[1]).read_bytes();(data/names[1]).write_bytes(original+b'changed')
 expect_error(lambda:restore_import(backup,check_running=False),'game has changed')
 (data/names[1]).write_bytes(original)
 restore_import(backup,check_running=False)
 assert all(sha(data/name)==digest for name,digest in receipt['before'].items())
 passed.append('interrupted restore preserves complete archives, resumes safely, and rejects newer changes after art relocation')
 # Cancel on the last unresolved route, after another patch is ready.
 manifest['exports'][routes[1]]['frame']=None;write_json(project/'project.json',manifest)
 event=threading.Event()
 def cancel_matching(*args):event.set();raise Cancelled()
 with patch.object(engine,'resolve_frame_routes',side_effect=cancel_matching):
  cancelled,plan=prepare_import(game,project,cancel=event)
 assert plan['status']=='cancelled' and not plan['patches'] and not plan['errors']
 expect_error(lambda:apply_import(cancelled,check_running=False),'no prepared replacements')
 passed.append('cancellation during final reference matching clears previously prepared patches')
 reference=game/'Digital Art Compendium'/'Frame Dump'/'annie'/'idle';reference.mkdir(parents=True)
 Image.new('RGBA',(8,8),'red').save(reference/'idle01_annie_1p.png')
 cache=root/'cache';catalog=layout.Catalog(game,'annie',cache);cache_file=next(cache.glob('*.npz'))
 for corrupt in [b'partial zip',b'PK\x03\x04truncated']:
  cache_file.write_bytes(corrupt);rebuilt=layout.Catalog(game,'annie',cache)
  assert rebuilt.paths==catalog.paths and np.array_equal(rebuilt.vectors,catalog.vectors)
 np.savez_compressed(cache_file,paths=np.array(catalog.paths),vectors=np.zeros((1,3)))
 assert layout.Catalog(game,'annie',cache).vectors.shape==(1,1025)
 # A failed cache publication leaves no partial .npz at its destination.
 cache_file.unlink()
 def fail_cache(stream,**kwargs):stream.write(b'partial');raise OSError('injected cache interruption')
 with patch.object(layout.np,'savez_compressed',fail_cache):
  expect_error(lambda:layout.Catalog(game,'annie',cache),'injected cache')
 assert not list(cache.iterdir());layout.Catalog(game,'annie',cache)
 passed.append('truncated and invalid catalog caches rebuild; failed cache writes leave no partial file')
 source,sm=export_project(game,root/'Projects',['annie'],limit=1)
 target,tm=export_project(game,root/'Projects',['annie'],limit=1)
 route=next(iter(sm['exports']));src=source/'Output'/route;dest=target/'Input'/route
 with Image.open(src) as im:pixels=np.array(im.convert('RGBA'))
 pixels[4:12,4:12]=[180,35,35,254];Image.fromarray(pixels).save(src)
 folder,_=matching.match_projects(source,target)
 def fail_copy(inp,out):out.write(inp.read(8));raise OSError('injected PNG interruption')
 with patch.object(matching.shutil,'copyfileobj',fail_copy):
  expect_error(lambda:matching.copy_matches(folder),'injected PNG')
 assert not dest.exists() and not list(dest.parent.glob('*.matching.tmp'))
 _,copied=matching.copy_matches(folder);assert copied['copied']==[route] and sha(dest)==sha(src)
 original_copy(target/'Output'/route,dest);reference_hash=sha(dest)
 with patch.object(matching.shutil,'copyfileobj',fail_copy):
  expect_error(lambda:matching.copy_matches(folder),'injected PNG')
 assert sha(dest)==reference_hash and not list(dest.parent.glob('*.matching.tmp'))
 _,copied=matching.copy_matches(folder);assert copied['replaced_references']==[route]
 passed.append('failed PNG copies preserve missing or existing destinations, clean temporary files, and retry successfully')
 # Batch boundaries preserve exactly the original distance calculation.
 rng=np.random.default_rng(42);vectors=list(rng.random((130,1025)))
 pairs,distances=matching.align_sequences(vectors,vectors,None)
 assert np.array_equal(distances,matching.cdist(vectors,vectors).astype(np.float32))
 assert [(i,j) for i,j,_ in pairs]==[(i,i) for i in range(130)]
 event=threading.Event();original_cdist=matching.cdist;calls=[]
 def cancel_distance(*args):
  calls.append(1);event.set();return original_cdist(*args)
 with patch.object(matching,'cdist',cancel_distance):
  try:matching.align_sequences(vectors,vectors,event)
  except Cancelled:pass
  else:raise AssertionError('Distance batching ignored cancellation')
 assert len(calls)==1
 passed.append('batched matching distances and pairings are unchanged; cancellation stops between batches')

if __name__=='__main__':run(Path('workshop-tests.json'))
