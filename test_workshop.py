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
   app.match_button.invoke();await_ui();assert app.match_folder and 'disabled' not in app.copy_button.state()
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
  saved_input=(project/'Input'/route).read_bytes();(project/'Input'/route).write_bytes(saved_input+b'extra');expect_error(lambda:apply_import(prepared,check_running=False),'Input PNG changed');(project/'Input'/route).write_bytes(saved_input);passed.append('stale Input refused')
  payload=prepared/plan['patches'][0]['payload'];saved=payload.read_bytes();payload.write_bytes(bytes([saved[0]^1])+saved[1:]);expect_error(lambda:apply_import(prepared,check_running=False),'payload was altered');payload.write_bytes(saved);passed.append('tampered prepared payload refused')
  plan_file=prepared/'plan.json';saved_plan=plan_file.read_bytes();tampered=json.loads(saved_plan);tampered['patches'][0]['offset']+=1;write_json(plan_file,tampered);expect_error(lambda:apply_import(prepared,check_running=False),'art slot');plan_file.write_bytes(saved_plan);passed.append('tampered destination offset refused')
  protected=game/'data01'/'characters-foits.gfs';saved_metadata=protected.read_bytes();protected.write_bytes(saved_metadata[:-1]+b'X');expect_error(lambda:apply_import(prepared,check_running=False),'game files changed');protected.write_bytes(saved_metadata);passed.append('changed verified metadata refused')
  import workshop as engine
  original_check=engine.game_running
  try:
   engine.game_running=lambda:True;expect_error(lambda:apply_import(prepared),'Close Skullgirls')
  finally:engine.game_running=original_check
  passed.append('running game blocks writes')
  before={p.name:sha(p) for p in (game/'data01').glob('*.gfs')};assert before==original
  backup,receipt=apply_import(prepared,check_running=False);assert receipt['status']=='installed';assert sha(game/'data01'/'characters-foits.gfs')==original['characters-foits.gfs'];assert sha(game/'data01'/'sprites.gfs')==original['sprites.gfs'];passed.append('apply verified; metadata and palettes byte-identical')
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
  result=dict(status='passed',native_cpu_available=codec.native_optimal is not None,checks=passed,project=str(project),game_fixture=str(game))
 except Exception as exc:
  import traceback
  result=dict(status='failed',checks=passed,error=str(exc),traceback=traceback.format_exc(),test_root=str(root));write_json(report,result);raise
 write_json(report,result);print(json.dumps(result,indent=2),flush=True);return result

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
 # Apply validates slot payloads without reading full art banks.
 original_read=GFS.read
 def slot_read(self,name):
  assert not name.endswith(('.art','.art-pt')),'Apply read a complete art bank'
  return original_read(self,name)
 with patch.object(GFS,'read',slot_read):backup,receipt=apply_import(prepared,check_running=False)
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
 passed.append('interrupted restore preserves complete archives, resumes safely, and rejects newer changes; apply validates slots only')
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
