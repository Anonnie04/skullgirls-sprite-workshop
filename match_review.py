"""Persist explicit review decisions without copying or applying sprites."""
from pathlib import Path
import json,datetime,hashlib
from PIL import Image
from workshop import project_info,safe_path,sha,pixel_hash,write_json


def key(record):
 return f'{record["character"]}:{record["source_frame"]}:{record.get("target_frame", "")}'


def load_report(folder):
 path=Path(folder)/'matches.json';raw=path.read_bytes();report=json.loads(raw.decode('utf-8'))
 source,sm=project_info(report['source']);target,tm=project_info(report['target'])
 if sha(source/'project.json')!=report['source_manifest_sha256'] or sha(target/'project.json')!=report['target_manifest_sha256']:
  raise ValueError('Project metadata changed. Match projects again.')
 return report,source,sm,target,tm,hashlib.sha256(raw).hexdigest()


def validate_record(record,source,sm,target,tm,complete=True):
 copies=record.get('copies',[])
 if not copies:raise ValueError('This pairing has no editable layers to approve.')
 expected=[]
 for manifest,frame in [(sm,record['source_frame']),(tm,record['target_frame'])]:
  expected.append({e['layer'] for e in manifest['exports'].values() if e['character']==record['character'] and e['frame']==frame and e['layer'] is not None})
 layers=[]
 for c in copies:
  se=sm['exports'].get(c['source']);te=tm['exports'].get(c['target'])
  if se is None or te is None:raise ValueError('A reviewed route is absent from its project.')
  if se['character']!=record['character'] or te['character']!=record['character'] or se['frame']!=record['source_frame'] or te['frame']!=record['target_frame'] or se['layer'] is None or se['layer']!=te['layer']:
   raise ValueError('The reviewed frame or editable layer does not match its project.')
  if sha(safe_path(source/'Output',c['source']))!=c['source_sha256'] or sha(safe_path(target/'Output',c['target']))!=c['target_sha256']:
   raise ValueError('An exported PNG changed. Match projects again.')
  layers.append(se['layer'])
 if complete and (expected[0]!=expected[1] or set(layers)!=expected[0] or len(layers)!=len(set(layers))):
  raise ValueError('Editable layers differ or are incomplete. This pairing cannot be approved as a whole.')


def preview_pair(folder,record_key):
 report,source,sm,target,tm,_=load_report(folder)
 record=next((r for group in ['matches','review'] for r in report[group] if key(r)==record_key),None)
 if record is None:raise ValueError('Choose a pairing with a target frame.')
 validate_record(record,source,sm,target,tm,False)
 views=[]
 composites=[]
 for manifest,frame,root in [(sm,record['source_frame'],source),(tm,record['target_frame'],target)]:
  route=next((r for r,e in manifest['exports'].items() if e['character']==record['character'] and e['frame']==frame and e['layer'] is None),None)
  composites.append(safe_path(root/'Output',route) if route else None)
 if all(composites):views.append(('Composite',*composites))
 for c in record['copies']:
  views.append((f'Layer {sm["exports"][c["source"]]["layer"]}',safe_path(source/'Output',c['source']),safe_path(target/'Output',c['target'])))
 return record,views


def approval_plan(folder,selected):
 report,source,sm,target,tm,digest=load_report(folder);selected=set(selected)
 records=[r for r in report['review'] if key(r) in selected]
 if not records or len(records)!=len(selected):raise ValueError('Choose frames that still require review.')
 routes={};pixels={}
 def artwork(c):
  if c['source'] not in pixels:
   with Image.open(safe_path(source/'Output',c['source'])) as image:pixels[c['source']]=pixel_hash(image)
  return pixels[c['source']]
 for r in records:
  validate_record(r,source,sm,target,tm)
  for c in r['copies']:
   if c['target'] in routes and artwork(c)!=artwork(routes[c['target']]):
    raise ValueError('The selected frames contain different variants for the same target. Select one variant per target.')
   routes[c['target']]=c
 conflicts=[];input_conflicts=[];overwrites={}
 inputs={p:sha(safe_path(target/'Input',p)) for p in routes if safe_path(target/'Input',p).is_file()}
 for group in ['matches','review']:
  for r in report[group]:
   different=[c for c in r['copies'] if c['target'] in routes and artwork(c)!=artwork(routes[c['target']])]
   staged=[c for c in different if inputs.get(c['target'])==c['source_sha256']]
   if different and group=='matches':validate_record(r,source,sm,target,tm,False);conflicts.append(r)
   if staged:
    validate_record(r,source,sm,target,tm,False);input_conflicts.append(r)
    for c in staged:overwrites[c['target']]=dict(before=c['source_sha256'],source_sha256=routes[c['target']]['source_sha256'])
 return dict(report=report,report_sha256=digest,records=records,conflicts=conflicts,input_conflicts=input_conflicts,overwrites=overwrites)


def prune_overwrites(report):
 active={(c['target'],c['source_sha256']) for r in report['matches'] for c in r['copies']}
 report['approved_overwrites']={p:g for p,g in report.get('approved_overwrites',{}).items() if (p,g['source_sha256']) in active}


def approve(folder,selected,replace_conflicts=False,expected_sha256=None):
 plan=approval_plan(folder,selected);report=plan['report'];path=Path(folder)/'matches.json'
 if expected_sha256 is not None and plan['report_sha256']!=expected_sha256:raise ValueError('The matching report changed. Review the selection again.')
 if (plan['conflicts'] or plan['input_conflicts']) and not replace_conflicts:raise ValueError('This choice conflicts with ready or staged frames. Confirm which source variant to keep.')
 chosen={key(r) for r in plan['records']};superseded={key(r) for r in plan['conflicts']}
 report['review']=[r for r in report['review'] if key(r) not in chosen]
 report['matches']=[r for r in report['matches'] if key(r) not in superseded]
 for r in plan['conflicts']:
  r['approved']=False;r['reason']='Another source variant was explicitly approved for this target';report['review'].append(r)
 for r in plan['records']:
  r['review_reason']=r.pop('reason','Manual review');r['approved']=True;report['matches'].append(r)
 report.setdefault('approved_overwrites',{}).update(plan['overwrites']);prune_overwrites(report)
 report.setdefault('review_history',[]).append(dict(action='approve',frames=sorted(chosen),superseded=sorted(superseded),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 if sha(path)!=plan['report_sha256']:raise ValueError('The matching report changed. Review the selection again.')
 write_json(path,report);return report


def return_to_review(folder,selected):
 report,_,_,_,_,digest=load_report(folder);selected=set(selected)
 records=[r for r in report['matches'] if key(r) in selected]
 if not records or len(records)!=len(selected):raise ValueError('Choose ready frames to return to review.')
 report['matches']=[r for r in report['matches'] if key(r) not in selected]
 for r in records:r['approved']=False;r['reason']='Returned to review';report['review'].append(r)
 prune_overwrites(report)
 report.setdefault('review_history',[]).append(dict(action='return-to-review',frames=sorted(selected),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 path=Path(folder)/'matches.json'
 if sha(path)!=digest:raise ValueError('The matching report changed. Review the selection again.')
 write_json(path,report);return report
