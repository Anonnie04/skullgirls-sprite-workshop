from version import __version__
from animation_sequence import animations,plan_sequence,stage_sequence,natural_key
import os,sys,json,threading,queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk,ImageDraw
from decoder import NAMES,available_characters
from project_match import match_projects,copy_matches,copy_required
import match_review
from workshop import generate_input_tree,export_project,scan_input,prepare_import,apply_import,restore_import,project_info,export_mod_zips,mod_details

# Original art-deco styling: no game artwork or external fonts required.
BG='#181416';PANEL='#292124';TEXT='#f5ead5';MUTED='#c2b39e';ACCENT='#e6bc68'
BURGUNDY='#542733';BORDER='#806345';HOVER='#403038';DISABLED='#8f827b'

def configure_theme(root):
 style=ttk.Style(root);style.theme_use('clam')
 root.option_add('*Font',('Segoe UI',10))
 root.option_add('*Listbox.background',PANEL);root.option_add('*Listbox.foreground',TEXT)
 root.option_add('*Listbox.selectBackground',BURGUNDY);root.option_add('*Listbox.selectForeground',TEXT)
 style.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10),bordercolor=BORDER,lightcolor=BORDER,darkcolor=BG,focuscolor=ACCENT)
 for name in ('TEntry','TCombobox'):
  style.configure(name,fieldbackground=PANEL,foreground=TEXT,insertcolor=TEXT,padding=7,arrowcolor=ACCENT)
  style.map(name,fieldbackground=[('disabled',BG),('readonly',PANEL)],foreground=[('disabled',DISABLED),('readonly',TEXT)],bordercolor=[('focus',ACCENT)])
 style.configure('TButton',background=PANEL,foreground=TEXT,padding=(12,8),borderwidth=1)
 style.map('TButton',background=[('disabled',BG),('pressed',BURGUNDY),('active',HOVER)],foreground=[('disabled',DISABLED)],bordercolor=[('focus',ACCENT),('active',ACCENT)])
 style.configure('Accent.TButton',background=ACCENT,foreground=BG,font=('Segoe UI',11,'bold'))
 style.map('Accent.TButton',background=[('disabled',PANEL),('pressed','#c79b4e'),('active','#f6d897')],foreground=[('disabled',DISABLED),('!disabled',BG)])
 style.configure('TCheckbutton',background=PANEL,foreground=TEXT,padding=4,indicatorbackground=BG,indicatorforeground=BG)
 style.map('TCheckbutton',background=[('active',HOVER)],foreground=[('disabled',DISABLED)],indicatorbackground=[('disabled',PANEL),('selected',ACCENT)],bordercolor=[('focus',ACCENT)])
 style.configure('TProgressbar',troughcolor=PANEL,background=ACCENT,bordercolor=BORDER,lightcolor=ACCENT,darkcolor=ACCENT)
 style.configure('TNotebook',background=BG,borderwidth=1,tabmargins=(0,0,0,0))
 style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(20,10),font=('Segoe UI',10,'bold'))
 style.map('TNotebook.Tab',background=[('selected',BURGUNDY),('active',HOVER)],foreground=[('selected',ACCENT),('active',TEXT)])
 style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=28)
 style.map('Treeview',background=[('selected',BURGUNDY)],foreground=[('selected',TEXT)])
 style.configure('Treeview.Heading',background=BURGUNDY,foreground=ACCENT,font=('Segoe UI',10,'bold'),padding=(8,6))
 style.map('Treeview.Heading',background=[('active',HOVER)])
 style.configure('TScrollbar',background=PANEL,troughcolor=BG,arrowcolor=ACCENT)
 style.map('TScrollbar',background=[('active',HOVER),('pressed',BURGUNDY)])

def workshop_header(parent):
 banner=tk.Canvas(parent,height=100,bg=BG,highlightthickness=0)
 # Supersample the straight diamond edges; Tk canvas polygons are not antialiased.
 scale=4
 diamond=Image.new('RGB',(24*scale,34*scale),BURGUNDY)
 ImageDraw.Draw(diamond).polygon([(12*scale,3*scale),(21*scale,17*scale),(12*scale,31*scale),(3*scale,17*scale)],fill=ACCENT)
 banner.diamond=ImageTk.PhotoImage(diamond.resize((24,34),Image.Resampling.LANCZOS),master=banner)
 def draw(event):
  banner.delete('all');w=event.width
  banner.create_polygon(0,0,w,0,w,76,w-24,100,24,100,0,76,fill=BURGUNDY,outline=BORDER)
  banner.create_line(14,12,w-14,12,fill=ACCENT)
  banner.create_line(28,88,w-28,88,fill=BORDER)
  for x in (32,w-32):
   banner.create_image(x,50,image=banner.diamond)
   banner.create_line(x,20,x,31,fill=ACCENT);banner.create_line(x,69,x,80,fill=ACCENT)
  banner.create_text(w/2,30,text='S K U L L G I R L S',fill=ACCENT,font=('Georgia',12,'bold'))
  banner.create_text(w/2,58,text='SPRITE WORKSHOP',fill=TEXT,font=('Georgia',25,'bold'))
  banner.create_text(w/2,80,text='E X P O R T   /   E D I T   /   I M P O R T',fill=MUTED,font=('Segoe UI',8))
 banner.bind('<Configure>',draw)
 return banner

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title(f'Skullgirls Sprite Workshop {__version__}');self.geometry('1050x900');self.minsize(930,880);self.configure(bg=BG)
  self.events=queue.Queue();self.cancel_event=threading.Event();self.busy=False;self.prepared=None;self.plan=None;self.last_output=None;self.last_backup=None;self.photos=[];self.fields=[]
  configure_theme(self)
  self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
  top=workshop_header(self);top.grid(row=0,column=0,sticky='ew',padx=24,pady=(10,10))
  candidates=[]
  if os.name=='nt':
   import winreg
   try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:candidates.append(Path(winreg.QueryValueEx(key,'SteamPath')[0])/'steamapps'/'common'/'Skullgirls')
   except OSError:pass
  candidates.append(Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Steam'/'steamapps'/'common'/'Skullgirls')
  guess=next((p for p in candidates if p.is_dir()),Path.home());self.game=tk.StringVar(value=str(guess));self.output=tk.StringVar(value=str(Path.home()/'Pictures'/'Skullgirls Projects'));self.project=tk.StringVar()
  paths=tk.Frame(self,bg=BG);paths.grid(row=1,column=0,sticky='ew',padx=24,pady=(0,10));paths.columnconfigure(1,weight=1);self.path_row(paths,0,'GAME FOLDER',self.game)
  self.tabs=ttk.Notebook(self);self.tabs.grid(row=2,column=0,sticky='nsew',padx=24);export=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);imports=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);self.tabs.add(export,text='Export project');self.tabs.add(imports,text='Import replacements')
  export.columnconfigure(1,weight=1);self.path_row(export,0,'SAVE PROJECTS TO',self.output)
  tk.Label(export,text='Output  /  exported PNGs        Input  /  empty folders for replacements',bg=PANEL,fg=ACCENT,font=('Segoe UI',11,'bold'),padx=14,pady=14,anchor='w').grid(row=1,column=0,columnspan=3,sticky='ew',pady=(14,7))
  tk.Label(export,text='Both use: character / character / data / category / animation / frames',bg=BG,fg=MUTED,anchor='w').grid(row=2,column=0,columnspan=3,sticky='ew',pady=(0,12))
  tools=tk.Frame(export,bg=BG);tools.grid(row=3,column=0,columnspan=3,sticky='ew');tk.Label(tools,text='CHARACTERS',bg=BG,fg=MUTED).pack(side='left')
  ttk.Button(tools,text='Scan game',command=self.scan).pack(side='right',padx=4);ttk.Button(tools,text='Clear',command=lambda:self.select(False)).pack(side='right',padx=4);ttk.Button(tools,text='Select all',command=lambda:self.select(True)).pack(side='right',padx=4)
  selection=tk.Frame(export,bg=PANEL,padx=12,pady=8,highlightbackground=BORDER,highlightthickness=1);selection.grid(row=4,column=0,columnspan=3,sticky='ew',pady=10);self.vars={};self.checks={}
  for i,(name,label) in enumerate(NAMES.items()):
   self.vars[name]=tk.BooleanVar(value=True);check=ttk.Checkbutton(selection,text=label,variable=self.vars[name]);check.grid(row=i//3,column=i%3,sticky='w',padx=8);self.checks[name]=check
  for i in range(3):selection.columnconfigure(i,weight=1)
  tk.Label(export,text='Animation names come from the installed Digital Art Compendium. Unmatched frames stay importable in an unmapped folder.\nLayered frames include individual layer PNGs. The first export builds an animation-name index.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=5,column=0,columnspan=3,sticky='w',pady=12)
  buttons=tk.Frame(export,bg=BG);buttons.grid(row=6,column=0,columnspan=3,sticky='ew');self.tree_button=ttk.Button(buttons,text='Generate full empty Input tree',command=self.start_tree);self.tree_button.pack(side='left')
  self.export_button=ttk.Button(buttons,text='Create Output + empty Input',style='Accent.TButton',command=self.start_export);self.export_button.pack(side='right')
  imports.columnconfigure(1,weight=1);imports.rowconfigure(3,weight=1);self.path_row(imports,0,'PROJECT FOLDER',self.project)
  tk.Label(imports,text='Place edited PNGs in Input at their Output paths. Filia and Valentine idle edits also update the selection preview.\nReview prepared previews first. Close Skullgirls before applying or restoring.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=1,column=0,columnspan=3,sticky='ew',pady=10)
  actions=tk.Frame(imports,bg=BG);actions.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(0,8));self.sequence_button=ttk.Button(actions,text='Import animation sequence…',command=self.start_sequence);self.sequence_button.pack(side='left',padx=(0,8));self.scan_button=ttk.Button(actions,text='Check Input',command=self.check_input);self.scan_button.pack(side='left');self.prepare_button=ttk.Button(actions,text='Prepare previews',command=self.start_prepare);self.prepare_button.pack(side='left',padx=8);self.apply_button=ttk.Button(actions,text='Apply ready replacements',style='Accent.TButton',command=self.start_apply,state='disabled');self.apply_button.pack(side='right')
  self.mod_button=ttk.Button(actions,text='Save mod ZIPs…',command=self.start_mod_export,state='disabled');self.mod_button.pack(side='right',padx=8)
  tableframe=tk.Frame(imports,bg=BG);tableframe.grid(row=3,column=0,columnspan=3,sticky='nsew');tableframe.columnconfigure(0,weight=1);tableframe.rowconfigure(0,weight=1);self.table=ttk.Treeview(tableframe,columns=('path','result'),show='headings',height=3);self.table.heading('path',text='Input file');self.table.heading('result',text='Result');self.table.column('path',width=500);self.table.column('result',width=360);self.table.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(tableframe,orient='vertical',command=self.table.yview);scroll.grid(row=0,column=1,sticky='ns');self.table.configure(yscrollcommand=scroll.set);self.table.bind('<<TreeviewSelect>>',self.preview_selection);self.table.bind('<Double-1>',self.open_preview)
  previews=tk.Frame(imports,bg=BG);previews.grid(row=4,column=0,columnspan=3,sticky='ew',pady=(10,4));self.preview_labels=[]
  for col,title in enumerate(['Current game frame','Prepared replacement']):
   previews.columnconfigure(col,weight=1);tk.Label(previews,text=title,bg=BG,fg=MUTED).grid(row=0,column=col,sticky='w');label=tk.Label(previews,bg=PANEL,width=40,height=6);label.grid(row=1,column=col,sticky='ew',padx=5);self.preview_labels.append(label)
  self.details=tk.StringVar(value='Preparation checks fitting and compression without modifying game files.');tk.Label(imports,textvariable=self.details,bg=BG,fg=MUTED,wraplength=920,justify='left').grid(row=5,column=0,columnspan=3,sticky='ew',pady=7)
  restore=tk.Frame(imports,bg=BG);restore.grid(row=6,column=0,columnspan=3,sticky='ew');self.restore_button=ttk.Button(restore,text='Restore an import backup…',command=self.start_restore);self.restore_button.pack(side='left');ttk.Button(restore,text='Open Input',command=lambda:self.open_branch('Input')).pack(side='right');ttk.Button(restore,text='Open Output',command=lambda:self.open_branch('Output')).pack(side='right',padx=8)
  matching=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);matching.columnconfigure(1,weight=1);matching.rowconfigure(4,weight=1);self.tabs.add(matching,text='Sort between projects')
  self.match_source=tk.StringVar();self.match_target=tk.StringVar();self.match_folder=None;self.match_report=None;self.match_rows={}
  self.path_row(matching,0,'SOURCE PROJECT',self.match_source);self.path_row(matching,1,'TARGET PROJECT',self.match_target)
  match_options=tk.Frame(matching,bg=BG);match_options.grid(row=2,column=0,columnspan=3,sticky='ew',pady=8);match_options.columnconfigure(1,weight=1)
  tk.Label(match_options,text='Select review rows and approve, or double-click a pairing to compare its images. Decisions are saved in the report.\nCopy ready PNGs stages approved art into target Input. Existing edited files stay protected.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=0,column=0,columnspan=4,sticky='w',pady=(0,5))
  self.overlap=tk.DoubleVar(value=94);self.overlap_label=tk.StringVar(value='94%')
  tk.Label(match_options,text='Minimum shape overlap',bg=BG,fg=TEXT).grid(row=1,column=0,sticky='w',padx=(0,12))
  self.overlap_slider=ttk.Scale(match_options,from_=50,to=100,variable=self.overlap,orient='horizontal');self.overlap_slider.grid(row=1,column=1,sticky='ew')
  tk.Label(match_options,textvariable=self.overlap_label,bg=BG,fg=ACCENT,width=5).grid(row=1,column=2,padx=6)
  tk.Label(match_options,text='Lower = more tolerant. Rematch to apply.',bg=BG,fg=MUTED).grid(row=1,column=3,sticky='e')
  self.overlap.trace_add('write',lambda *args:self.overlap_label.set(f'{round(self.overlap.get())}%'))
  match_actions=tk.Frame(matching,bg=BG);match_actions.grid(row=3,column=0,columnspan=3,sticky='ew',pady=8)
  self.match_button=ttk.Button(match_actions,text='Match frames',command=self.start_match);self.match_button.pack(side='left')
  self.approve_button=ttk.Button(match_actions,text='Approve selected',command=self.approve_records,state='disabled');self.approve_button.pack(side='left',padx=6)
  self.unapprove_button=ttk.Button(match_actions,text='Return to review',command=self.return_records,state='disabled');self.unapprove_button.pack(side='left')
  self.copy_button=ttk.Button(match_actions,text='Copy ready PNGs to target Input',style='Accent.TButton',command=self.start_copy,state='disabled');self.copy_button.pack(side='right')
  self.match_table=ttk.Treeview(matching,columns=('old','new','result'),show='headings',height=6)
  for column,title,width in [('old','Source frame',160),('new','Target frame',420),('result','Result',280)]:self.match_table.heading(column,text=title);self.match_table.column(column,width=width)
  self.match_table.grid(row=4,column=0,columnspan=3,sticky='nsew');match_scroll=ttk.Scrollbar(matching,orient='vertical',command=self.match_table.yview);match_scroll.grid(row=4,column=3,sticky='ns');self.match_table.configure(yscrollcommand=match_scroll.set)
  self.match_table.bind('<<TreeviewSelect>>',lambda e:self.refresh_review_buttons());self.match_table.bind('<Double-1>',self.open_match_preview)
  report_actions=tk.Frame(matching,bg=BG);report_actions.grid(row=5,column=0,columnspan=3,sticky='ew',pady=10)
  self.load_report_button=ttk.Button(report_actions,text='Load report…',command=self.load_match_report);self.load_report_button.pack(side='left')
  ttk.Button(report_actions,text='Open report folder',command=lambda:os.startfile(str(self.match_folder)) if self.match_folder else None).pack(side='left',padx=8)
  self.match_source.trace_add('write',self.invalidate_match);self.match_target.trace_add('write',self.invalidate_match)
  try:
   projects=sorted(Path(self.output.get()).glob('*/project.json'))
   sources=[];targets=[]
   for path in projects:
    m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('exports'):(sources if 'depot_' in m.get('game','') else targets).append(path.parent)
   if sources:self.match_source.set(str(sources[-1]))
   if targets:self.match_target.set(str(targets[-1]))
  except (OSError,ValueError):pass
  bottom=tk.Frame(self,bg=BG);bottom.grid(row=3,column=0,sticky='ew',padx=24,pady=(8,14));bottom.columnconfigure(0,weight=1);self.status=tk.StringVar(value='Ready. Create a project or choose an existing project.');self.count=tk.StringVar();tk.Label(bottom,textvariable=self.status,bg=BG,fg=TEXT,anchor='w',wraplength=1000).grid(row=0,column=0,columnspan=3,sticky='ew');self.progress=ttk.Progressbar(bottom,maximum=100);self.progress.grid(row=1,column=0,columnspan=3,sticky='ew',pady=7);tk.Label(bottom,textvariable=self.count,bg=BG,fg=MUTED,anchor='w').grid(row=2,column=0,sticky='w');self.open_button=ttk.Button(bottom,text='Open project',command=self.open_output,state='disabled');self.open_button.grid(row=2,column=1,padx=8);self.stop_button=ttk.Button(bottom,text='Cancel',command=self.stop,state='disabled');self.stop_button.grid(row=2,column=2)
  self.controls=[self.sequence_button,self.match_button,self.overlap_slider,self.approve_button,self.unapprove_button,self.load_report_button,self.tree_button,self.export_button,self.scan_button,self.prepare_button,self.restore_button]+self.fields;self.game.trace_add('write',self.invalidate);self.project.trace_add('write',self.invalidate);self.protocol('WM_DELETE_WINDOW',self.close);self.poll_after=self.after(100,self.poll)

 def invalidate_match(self,*args):
  self.match_folder=None;self.match_report=None;self.match_rows={};self.copy_button.state(['disabled']);self.approve_button.state(['disabled']);self.unapprove_button.state(['disabled']);self.match_table.delete(*self.match_table.get_children())
 def refresh_copy_button(self):
  ready=bool(self.match_folder and self.match_report and self.match_report.get('matches'))
  self.copy_button.state(['!disabled'] if ready and not self.busy else ['disabled'])
  self.refresh_review_buttons()
 def selected_match_keys(self,group):
  return [self.match_rows[i][1] for i in self.match_table.selection() if i in self.match_rows and self.match_rows[i][0]==group]
 def refresh_review_buttons(self):
  self.approve_button.state(['!disabled'] if not self.busy and self.selected_match_keys('review') else ['disabled'])
  self.unapprove_button.state(['!disabled'] if not self.busy and self.selected_match_keys('matches') else ['disabled'])
 def render_matches(self,selected=()):
  self.match_table.delete(*self.match_table.get_children());self.match_rows={};selected=set(selected);selection=[]
  for group,label in [('matches','Ready to copy'),('review','Review required'),('unmatched','Unmatched')]:
   for i,r in enumerate(self.match_report[group]):
    needed=any(copy_required(self.match_report,c) for c in r.get('copies',[]))
    status=('Ready to copy' if needed else 'Identical pixels — no copy needed') if group=='matches' else label
    if group=='matches' and r.get('approved'):status='Approved — '+('ready to copy' if needed else 'no copy needed')
    if group=='matches' and r.get('recovery')=='transparent':status='Transparent frame — no copy needed'
    if 'reason' in r:status+=' — '+r['reason']
    if 'registered_overlap' in r:status+=f' — aligned shape overlap {r["registered_overlap"]:.1%}'
    iid=f'{group}-{i}';record_key=match_review.key(r);self.match_rows[iid]=(group,record_key)
    targets=', '.join(c['target'] for c in r.get('copies',[]))
    self.match_table.insert('',tk.END,iid=iid,values=(f'{r["character"]} {r["source_frame"]}',targets or str(r.get('target_frame','')),status))
    if record_key in selected:selection.append(iid)
  self.match_table.selection_set(selection)
  if selection:self.match_table.see(selection[0])
  self.refresh_copy_button()
 def load_match_report(self):
  if self.busy:return
  path=filedialog.askopenfilename(title='Load matching report',filetypes=[('Matching report','matches.json')],initialdir=str(self.match_folder or Path(self.match_target.get())/'Matches'))
  if not path:return
  try:
   if Path(path).name!='matches.json':raise ValueError('Choose a matches.json report.')
   folder=Path(path).parent;report,*_=match_review.load_report(folder)
   self.match_source.set(report['source']);self.match_target.set(report['target']);self.overlap.set(report.get('min_overlap',.94)*100);self.match_folder=folder;self.match_report=report;self.render_matches()
   self.status.set(f'Loaded report: {len(report["matches"])} ready frames, {len(report["review"])} for review. Saved approvals retained.')
  except Exception as exc:messagebox.showerror('Cannot load report',str(exc))
 def approve_records(self,selected=None,expected_folder=None):
  if self.busy or not self.match_folder:return False
  if expected_folder is not None and Path(self.match_folder).resolve()!=Path(expected_folder).resolve():
   messagebox.showerror('Report changed','Reopen the preview for the current matching report.');return False
  selected=selected or self.selected_match_keys('review')
  if not selected:return False
  try:
   plan=match_review.approval_plan(self.match_folder,selected);replace=bool(plan['conflicts'] or plan['input_conflicts'])
   if replace:
    other={match_review.key(r):r for r in plan['conflicts']+plan['input_conflicts']}
    labels='\n'.join(f'{r["character"]} {r["source_frame"]} → {r["target_frame"]}' for r in list(other.values())[:8])
    if len(other)>8:labels+=f'\n… and {len(other)-8} more.'
    text=f'Keep the selected source variant instead?\n\n{len(other)} conflicting ready or staged choice(s):\n{labels}\n\nOther ready variants will return to review. Nothing is copied now.'
    if plan['overwrites']:text+='\n\nWhen you click Copy ready PNGs, unchanged copies of these older choices can be backed up and replaced. Files edited since copying stay protected.'
    if not messagebox.askyesno('Choose source variant',text):return False
   self.match_report=match_review.approve(self.match_folder,selected,replace,plan['report_sha256']);self.render_matches(selected)
   self.status.set(f'Approved {len(selected)} pairing(s). Nothing copied yet. Click Copy ready PNGs to target Input.');return True
  except Exception as exc:messagebox.showerror('Cannot approve frames',str(exc));return False
 def return_records(self,selected=None,expected_folder=None):
  if self.busy or not self.match_folder:return False
  if expected_folder is not None and Path(self.match_folder).resolve()!=Path(expected_folder).resolve():return False
  selected=selected or self.selected_match_keys('matches')
  if not selected:return False
  try:
   self.match_report=match_review.return_to_review(self.match_folder,selected);self.render_matches(selected)
   self.status.set(f'Returned {len(selected)} pairing(s) to review. Previously copied Input files were left unchanged.');return True
  except Exception as exc:messagebox.showerror('Cannot return frames to review',str(exc));return False
 def open_match_preview(self,event=None):
  if self.busy or not self.match_folder:return
  selection=self.match_table.selection()
  if not selection or selection[0] not in self.match_rows:return
  group,record_key=self.match_rows[selection[0]]
  if group=='unmatched':return
  try:
   record,views=match_review.preview_pair(self.match_folder,record_key)
   self.match_preview=MatchPreviewDialog(self,self.match_folder,record_key,record,views,group=='review')
  except Exception as exc:messagebox.showerror('Cannot preview pairing',str(exc))
 def start_match(self):
  source=self.match_source.get();target=self.match_target.get();minimum=round(self.overlap.get())/100;self.invalidate_match();self.status.set(f'Matching exported projects with {minimum:.0%} minimum shape overlap');self.launch('match',lambda:match_projects(source,target,self.report,self.cancel_event,min_overlap=minimum))
 def start_copy(self):
  if self.busy:return
  if not self.match_folder:
   self.status.set('Match the source and target projects before copying.');return
  self.status.set('Copying matched source PNGs into target Input');folder=self.match_folder;self.prepared=None;self.plan=None;self.copy_button.state(['disabled']);self.launch('copy',lambda:copy_matches(folder,self.report,self.cancel_event))
 def path_row(self,parent,row,label,var):
  tk.Label(parent,text=label,bg=BG,fg=MUTED,font=('Segoe UI',9,'bold')).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5);entry=ttk.Entry(parent,textvariable=var);entry.grid(row=row,column=1,sticky='ew',pady=5);button=ttk.Button(parent,text='Browse…',command=lambda:self.browse(var));button.grid(row=row,column=2,padx=(10,0),pady=5);self.fields.extend([entry,button])
 def invalidate(self,*args):
  if not self.busy:self.prepared=None;self.plan=None;self.apply_button.state(['disabled']);self.mod_button.state(['disabled'])
 def browse(self,var):
  if self.busy:return
  p=filedialog.askdirectory(initialdir=var.get() if Path(var.get()).is_dir() else str(Path.home()))
  if p:
   var.set(p)
   if var is self.project:self.prepared=None;self.plan=None;self.apply_button.state(['disabled'])
 def select(self,value):
  if not self.busy:
   for n,v in self.vars.items():
    if 'disabled' not in self.checks[n].state():v.set(value)
 def scan(self):
  if self.busy:return
  try:
   found=available_characters(self.game.get())
   for n,c in self.checks.items():
    c.state(['!disabled'] if n in found else ['disabled'])
    if n not in found:self.vars[n].set(False)
   self.status.set(f'Found {len(found)} character entries.')
  except Exception as exc:messagebox.showerror('Cannot read game folder',str(exc))
 def launch(self,kind,work,cancellable=True):
  if self.busy:return
  self.busy=True;self.kind=kind;self.cancel_event.clear();self.progress['value']=0;self.count.set('');self.apply_button.state(['disabled']);self.copy_button.state(['disabled'])
  self.mod_button.state(['disabled'])
  for c in self.controls:c.state(['disabled'])
  self.stop_button.state(['!disabled'] if cancellable else ['disabled'])
  def run():
   try:self.events.put((kind,work()))
   except Exception as exc:self.events.put(('error',str(exc) or repr(exc)))
  threading.Thread(target=run,daemon=True).start()
 def report(self,*args):self.events.put(('progress',args))
 def start_tree(self):
  game=self.game.get();output=self.output.get();self.prepared=None;self.plan=None;self.status.set('Creating the full empty Input tree');self.launch('tree',lambda:generate_input_tree(game,output,self.report,self.cancel_event))
 def start_export(self):
  selected=[n for n,v in self.vars.items() if v.get()];game=self.game.get();output=self.output.get()
  if not selected:messagebox.showerror('Choose characters','Select at least one character.');return
  self.prepared=None;self.plan=None;self.status.set('Creating mirrored project…');self.launch('export',lambda:export_project(game,output,selected,self.report,self.cancel_event))
 def check_input(self):
  if self.busy:return
  self.invalidate()
  try:
   found,unknown=scan_input(self.project.get());self.status.set(f'Input: {len(found):,} matching PNGs, {len(unknown):,} unrecognized paths. Empty folders are skipped.');self.table.delete(*self.table.get_children())
   for i,(_,path,entry) in enumerate(found):self.table.insert('',tk.END,iid=f'scan{i}',values=(path,'Ready to prepare' if entry['layer'] is not None else 'Composite: edit individual layers'))
   for i,path in enumerate(unknown):self.table.insert('',tk.END,iid=f'unknown{i}',values=(path,'Path does not match Output'))
  except Exception as exc:messagebox.showerror('Cannot scan Input',str(exc))
 def start_sequence(self):
  if self.busy:return
  try:
   project,_=project_info(self.project.get());groups=animations(project)
   if not groups:raise ValueError('This project has no editable animation routes. Export the character or generate an Input tree first.')
  except Exception as exc:messagebox.showerror('Choose a project',str(exc));return
  files=filedialog.askopenfilenames(title='Select animation PNGs (one frame or a numbered sequence)',filetypes=[('PNG images','*.png')])
  if not files:return
  self.sequence_dialog=SequenceDialog(self,project,files,groups)
 def import_sequence(self,project,files,animation,start,overwrite):
  self.invalidate();self.status.set('Staging animation PNGs into Input')
  self.launch('sequence',lambda:stage_sequence(project,files,animation,start,overwrite,self.report,self.cancel_event))
 def start_prepare(self):
  game=self.game.get();project=self.project.get();self.prepared=None;self.plan=None;self.status.set('Checking replacements…');self.launch('prepare',lambda:prepare_import(game,project,self.report,self.cancel_event))
 def start_apply(self):
  if self.busy or not self.plan or not self.prepared:return
  n=len(self.plan['patches']);warnings=sum(bool(p['warnings']) for p in self.plan['patches']);errors=len(self.plan['errors']);text=f'Apply {n} prepared replacements?\n\n{warnings} have fitting notes; {errors} files will be skipped. Review previews first.\n\nClose Skullgirls. Affected archives will be backed up. Art storage pointers and lengths may change; palettes, timing and hitboxes stay intact.'
  if messagebox.askokcancel('Apply reviewed replacements',text):
   prepared=self.prepared;self.launch('apply',lambda:apply_import(prepared,self.report),False)
 def start_mod_export(self):
  if self.busy or not self.plan or not self.prepared:return
  self.mod_dialog=ModDetailsDialog(self)
 def export_mods(self,metadata):
  if self.busy or not self.plan or not self.prepared:return False
  parent=filedialog.askdirectory(initialdir=str(Path(self.project.get()).parent),title='Save one mod ZIP per applicable character')
  if not parent:return False
  prepared=self.prepared;self.status.set('Building character mod ZIPs without modifying the game…')
  self.launch('mods',lambda:export_mod_zips(prepared,parent,self.report,self.cancel_event,metadata=metadata));return True
 def start_restore(self):
  if self.busy:return
  initial=str(self.last_backup or (Path(self.project.get())/'Backups'));folder=filedialog.askdirectory(initialdir=initial if Path(initial).is_dir() else str(Path.home()),title='Choose a backup containing restore.json')
  if not folder:return
  try:
   r=json.loads((Path(folder)/'restore.json').read_text());text=f'Restore the art from this backup?\n\nThis undoes {r["frames"]} replacements in {r["game"]}.\n\nClose Skullgirls. Restore will refuse if newer changes are present.'
   if messagebox.askokcancel('Restore import',text):self.launch('restore',lambda:restore_import(folder,self.report),False)
  except Exception as exc:messagebox.showerror('Cannot restore backup',str(exc))
 def preview_selection(self,event=None):
  selection=self.table.selection()
  if not selection or not self.plan or not self.prepared:return
  if not selection[0].startswith('patch'):
   key=selection[0]
   if key.startswith('error'):r=self.plan['errors'][int(key[5:])];self.details.set(r['path']+' — '+r['error'])
   elif key.startswith('skip'):r=self.plan['skipped'][int(key[4:])];self.details.set(r['path']+' — '+r['reason'])
   for label in self.preview_labels:label.configure(image='',width=40,height=6)
   self.photos=[];return
  r=self.plan['patches'][int(selection[0][5:])];self.photos=[]
  for label,name in zip(self.preview_labels,[r['before'],r['after']]):
   with Image.open(self.prepared/name) as image:im=image.convert('RGBA')
   im.thumbnail((430,115),Image.Resampling.NEAREST);canvas=Image.new('RGBA',(440,120),(35,42,53,255));draw=ImageDraw.Draw(canvas)
   for y in range(0,120,16):
    for x in range(0,440,16):
     if (x//16+y//16)%2:draw.rectangle((x,y,x+15,y+15),fill=(43,51,63,255))
   canvas.alpha_composite(im,((440-im.width)//2,(120-im.height)//2));photo=ImageTk.PhotoImage(canvas.convert('RGB'));self.photos.append(photo);label.configure(image=photo,width=440,height=120)
  notes='; '.join(r['warnings']) or 'No storage-driven color changes.';self.details.set(f'{NAMES[r["character"]]} · internal frame {r["frame"]} · {r["statistics"]["changed_pixels"]:,} changed pixels · {r["fit"]["mode"]}. {notes}')
 def stop(self):self.cancel_event.set();self.status.set('Stopping after the current frame…');self.stop_button.state(['disabled'])
 def open_preview(self,event=None):
  selection=self.table.selection()
  if selection and selection[0].startswith('patch') and self.plan and self.prepared:
   r=self.plan['patches'][int(selection[0][5:])];os.startfile(str(self.prepared/r['after']))
 def poll(self):
  try:
   while True:
    event,payload=self.events.get_nowait()
    if event=='progress':
     done,total,label=payload;self.status.set(label)
     if total:self.progress['value']=done/total*100;self.count.set(f'{done:,} / {total:,}')
    elif event=='tree':
     self.last_output,m=payload;self.project.set(str(self.last_output));self.finish();self.open_button.state(['!disabled']);self.status.set(f'{m["status"]}: empty Input tree for {len(m["characters"])} characters. No PNGs extracted.');self.progress['value']=100 if m['status']=='complete' else 0;self.tabs.select(1)
    elif event=='export':
     self.last_output,m=payload;self.project.set(str(self.last_output));self.finish();self.open_button.state(['!disabled']);frames=sum(x['exported'] for x in m['characters'].values());unmapped=sum(x['unmapped'] for x in m['characters'].values());self.status.set(f'{m["status"]}: {frames:,} frames exported. Input has empty matching folders.');self.count.set(f'{unmapped:,} frames in unmapped folders; {len(m["errors"]):,} export errors.');self.progress['value']=100 if m['status']=='complete' else self.progress['value']
    elif event=='match':
     self.match_folder,self.match_report=payload;self.finish();self.render_matches()
     ready_pngs=len({c['target'] for r in self.match_report['matches'] for c in r['copies'] if copy_required(self.match_report,c)});identical_pngs=sum(not copy_required(self.match_report,c) for r in self.match_report['matches'] for c in r['copies'])
     missing=len(self.match_report.get('missing_exports',[]))
     self.copy_button.state(['!disabled'] if self.match_report['matches'] else ['disabled']);self.status.set(f'{ready_pngs:,} PNGs ready to copy; {identical_pngs:,} identical PNGs skipped; {len(self.match_report["review"]):,} uncertain frames; {missing:,} frames skipped for missing Output PNGs. Nothing copied yet. Click Copy ready PNGs to target Input.');self.progress['value']=100
    elif event=='copy':
     target,result=payload;self.finish();self.project.set(str(target));self.tabs.select(1);self.status.set(f'Copied {len(result["copied"]):,} PNGs to target Input; {len(result["existing"]):,} existing edits preserved; {len(result.get("replaced_references",[])):,} unchanged references replaced; {result["unchanged"]:,} identical PNGs skipped. Prepare previews next.');self.progress['value']=100
     if result.get('approved_replaced'):self.status.set(self.status.get()+f' {len(result["approved_replaced"])} reviewed choice(s) replaced with backups in {result["approval_backup"]}.')
    elif event=='mods':
     folder,records=payload;self.finish();self.apply_button.state(['!disabled']);self.status.set(f'Saved {len(records)} character mod ZIPs to {folder}. Import the ZIPs into Skullgirls Mod Manager.');self.progress['value']=100
    elif event=='sequence':
     target,result=payload;self.finish();self.project.set(str(target));self.check_input();self.status.set(f'Animation staged: {result["copied"]} PNGs; {result["backed_up"]} previous Input frames backed up; {result["unchanged"]} unchanged. Prepare previews next.');self.progress['value']=100
    elif event=='prepare':
     self.prepared,self.plan=payload;self.finish();self.table.delete(*self.table.get_children())
     for i,r in enumerate(self.plan['patches']):self.table.insert('',tk.END,iid=f'patch{i}',values=(r['path'],'Ready · '+('; '.join(r['warnings']) or 'no storage-driven color changes')))
     for i,r in enumerate(self.plan['errors']):self.table.insert('',tk.END,iid=f'error{i}',values=(r['path'],'Skipped: '+r['error']))
     for i,r in enumerate(self.plan['skipped']):self.table.insert('',tk.END,iid=f'skip{i}',values=(r['path'],'Skipped: '+r['reason']))
     n=len(self.plan['patches']);self.apply_button.state(['!disabled'] if n and self.plan['status']=='prepared' else ['disabled']);self.status.set(f'{n} prepared; {len(self.plan["errors"])} errors; {len(self.plan["skipped"])} unchanged/duplicate files skipped.');self.progress['value']=100
     if n:self.table.selection_set('patch0');self.preview_selection()
    elif event=='apply':self.last_backup,r=payload;self.finish();self.prepared=None;self.plan=None;self.mod_button.state(['disabled']);self.status.set(f'Installed {r["frames"]} replacements. Verified backup: {self.last_backup.name}');self.progress['value']=100
    elif event=='restore':self.finish();self.prepared=None;self.plan=None;self.mod_button.state(['disabled']);self.status.set('Original art restored and verified.');self.progress['value']=100
    elif event=='error':
     self.finish();self.status.set('Operation stopped.')
     if self.plan and self.plan['status']=='prepared' and self.plan['patches']:self.apply_button.state(['!disabled'])
     messagebox.showerror('Sprite Workshop',payload)
  except queue.Empty:pass
  self.poll_after=self.after(100,self.poll)
 def finish(self):
  self.busy=False
  for c in self.controls:c.state(['!disabled'])
  self.stop_button.state(['disabled']);self.refresh_copy_button()
  ready=bool(self.prepared and self.plan and self.plan.get('status')=='prepared' and self.plan.get('patches'))
  self.mod_button.state(['!disabled'] if ready else ['disabled'])
 def open_output(self):
  if self.last_output:os.startfile(str(self.last_output))
 def open_branch(self,branch):
  try:p,_=project_info(self.project.get());os.startfile(str(p/branch))
  except Exception as exc:messagebox.showerror('Choose a project',str(exc))
 def destroy(self):
  if getattr(self,'poll_after',None):
   try:self.after_cancel(self.poll_after)
   except tk.TclError:pass
  super().destroy()
 def close(self):
  if self.busy:
   if self.kind in ['export','tree','prepare','match','copy','sequence']:self.stop()
   self.after(200,self.close_when_idle)
  else:self.destroy()
 def close_when_idle(self):
  if self.busy:self.after(200,self.close_when_idle)
  else:self.destroy()

class MatchPreviewDialog(tk.Toplevel):
 def __init__(self,parent,folder,record_key,record,views,review):
  super().__init__(parent);self.parent=parent;self.folder=folder;self.record_key=record_key;self.views={name:(source,target) for name,source,target in views};self.photos=[]
  self.title(f'{NAMES.get(record["character"],record["character"])} · {record["source_frame"]} → {record["target_frame"]}')
  self.geometry('960x620');self.minsize(780,460);self.configure(bg=BG);self.transient(parent)
  self.columnconfigure(0,weight=1);self.columnconfigure(1,weight=1);self.rowconfigure(2,weight=1)
  detail=record.get('reason','Ready pairing')
  if 'registered_overlap' in record:detail+=f' · aligned shape overlap {record["registered_overlap"]:.1%}'
  tk.Label(self,text=detail,bg=BG,fg=TEXT,wraplength=920,justify='left').grid(row=0,column=0,columnspan=2,sticky='ew',padx=14,pady=10)
  self.view=tk.StringVar(value=views[0][0]);self.layer_box=ttk.Combobox(self,textvariable=self.view,values=list(self.views),state='readonly');self.layer_box.grid(row=1,column=0,columnspan=2,sticky='ew',padx=14,pady=(0,8));self.layer_box.bind('<<ComboboxSelected>>',self.select_view)
  self.canvases=[]
  for col,title in enumerate([f'Source · frame {record["source_frame"]}',f'Target · frame {record["target_frame"]}']):
   frame=tk.Frame(self,bg=BG);frame.grid(row=2,column=col,sticky='nsew',padx=10);frame.columnconfigure(0,weight=1);frame.rowconfigure(1,weight=1)
   tk.Label(frame,text=title,bg=BG,fg=ACCENT).grid(row=0,column=0,sticky='w',pady=6)
   canvas=tk.Canvas(frame,bg=PANEL,highlightthickness=0,width=420,height=360);canvas.grid(row=1,column=0,sticky='nsew');canvas.bind('<Configure>',lambda e:self.redraw());self.canvases.append(canvas)
  tk.Label(self,text='Both images use the same zoom. Approval covers all editable layers; copying is a separate step.',bg=BG,fg=MUTED,wraplength=920).grid(row=3,column=0,columnspan=2,sticky='w',padx=14,pady=8)
  ttk.Button(self,text='Close',command=self.destroy).grid(row=4,column=0,sticky='w',padx=14,pady=10)
  self.approve_button=ttk.Button(self,text='Approve pairing' if review else 'Return to review',style='Accent.TButton',command=self.submit_review if review else self.submit_return);self.approve_button.grid(row=4,column=1,sticky='e',padx=14,pady=10)
  self.select_view()
 def select_view(self,event=None):
  self.images=[]
  for path in self.views[self.view.get()]:
   with Image.open(path) as image:self.images.append(image.convert('RGBA'))
  self.redraw()
 def redraw(self):
  if not getattr(self,'images',None):return
  width=max(100,min(c.winfo_width() for c in self.canvases));height=max(100,min(c.winfo_height() for c in self.canvases))
  scale=min((width-16)/max(im.width for im in self.images),(height-16)/max(im.height for im in self.images),8)
  self.photos=[]
  for canvas,image in zip(self.canvases,self.images):
   w=max(100,canvas.winfo_width());h=max(100,canvas.winfo_height());canvas.delete('all')
   for y in range(0,h,20):
    for x in range(0,w,20):canvas.create_rectangle(x,y,x+20,y+20,fill=PANEL if (x//20+y//20)%2 else HOVER,outline='')
   resized=image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.NEAREST)
   photo=ImageTk.PhotoImage(resized,master=canvas);self.photos.append(photo);canvas.create_image(w/2,h/2,image=photo)
 def submit_review(self):
  if self.parent.approve_records([self.record_key],self.folder):self.destroy()
 def submit_return(self):
  if self.parent.return_records([self.record_key],self.folder):self.destroy()


class ModDetailsDialog(tk.Toplevel):
 def __init__(self,app):
  super().__init__(app);self.app=app;self.title('Mod details');self.geometry('680x480');self.minsize(580,430);self.configure(bg=BG);self.transient(app);self.grab_set();self.columnconfigure(1,weight=1);self.rowconfigure(4,weight=1)
  self.project=str(Path(app.project.get()).resolve());self.characters=sorted({r['character'] for r in app.plan['patches']})
  saved=getattr(app,'mod_drafts',{}).get(self.project,{})
  self.drafts={name:mod_details(name,saved.get(name)) for name in self.characters};self.current=self.characters[0]
  tk.Label(self,text='Edit the details included in each character’s mod.json.',bg=BG,fg=TEXT).grid(row=0,column=0,columnspan=2,sticky='w',padx=16,pady=14)
  tk.Label(self,text='Character',bg=BG,fg=MUTED).grid(row=1,column=0,sticky='w',padx=16)
  self.character=tk.StringVar(value=NAMES[self.current]);self.character_box=ttk.Combobox(self,textvariable=self.character,values=[NAMES[n] for n in self.characters],state='readonly');self.character_box.grid(row=1,column=1,sticky='ew',padx=16,pady=6);self.character_box.bind('<<ComboboxSelected>>',self.switch_character)
  self.name=tk.StringVar();self.version=tk.StringVar()
  for row,label,var in [(2,'Name',self.name),(3,'Version',self.version)]:
   tk.Label(self,text=label,bg=BG,fg=MUTED).grid(row=row,column=0,sticky='w',padx=16)
   entry=ttk.Entry(self,textvariable=var);entry.grid(row=row,column=1,sticky='ew',padx=16,pady=6)
   if row==2:self.name_entry=entry
  tk.Label(self,text='Description',bg=BG,fg=MUTED).grid(row=4,column=0,sticky='nw',padx=16,pady=6)
  frame=tk.Frame(self,bg=BG);frame.grid(row=4,column=1,sticky='nsew',padx=16,pady=6);frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
  self.description=tk.Text(frame,height=6,wrap='word',bg=PANEL,fg=TEXT,insertbackground=TEXT,relief='flat',padx=8,pady=8,undo=True);self.description.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(frame,command=self.description.yview);scroll.grid(row=0,column=1,sticky='ns');self.description.configure(yscrollcommand=scroll.set)
  self.error=tk.StringVar();tk.Label(self,textvariable=self.error,bg=BG,fg=ACCENT,wraplength=630,justify='left').grid(row=5,column=0,columnspan=2,sticky='w',padx=16,pady=6)
  actions=tk.Frame(self,bg=BG);actions.grid(row=6,column=0,columnspan=2,sticky='ew',padx=16,pady=14)
  ttk.Button(actions,text='Cancel',command=self.destroy).pack(side='left');self.export_button=ttk.Button(actions,text='Choose folder and export…',style='Accent.TButton',command=self.submit);self.export_button.pack(side='right')
  self.show_character();self.bind('<Escape>',lambda e:self.destroy());self.name_entry.focus_set()
 def store_character(self):
  self.drafts[self.current]=dict(name=self.name.get(),version=self.version.get(),desc=self.description.get('1.0','end-1c'))
 def show_character(self):
  values=self.drafts[self.current];self.name.set(values['name']);self.version.set(values['version']);self.description.delete('1.0',tk.END);self.description.insert('1.0',values['desc'])
 def switch_character(self,event=None):
  self.store_character();self.current=self.characters[self.character_box.current()];self.show_character();self.error.set('')
 def submit(self):
  self.store_character()
  try:metadata={name:mod_details(name,values) for name,values in self.drafts.items()}
  except ValueError as exc:self.error.set(str(exc));return
  if not hasattr(self.app,'mod_drafts'):self.app.mod_drafts={}
  self.app.mod_drafts[self.project]=metadata
  self.grab_release()
  try:started=self.app.export_mods(metadata)
  finally:
   if self.winfo_exists():self.grab_set()
  if started:self.destroy()


class SequenceDialog(tk.Toplevel):
 def __init__(self,app,project,files,groups):
  super().__init__(app);self.app=app;self.project=project;self.files=sorted(files,key=lambda f:natural_key(Path(f).name));self.groups=groups;self.title('Import animation sequence');self.geometry('950x540');self.configure(bg=BG);self.transient(app);self.grab_set();self.columnconfigure(1,weight=1);self.rowconfigure(4,weight=1)
  tk.Label(self,text=f'{len(files)} PNG(s), sorted by filename number. Sources stay unchanged.',bg=BG,fg=TEXT).grid(row=0,column=0,columnspan=2,sticky='w',padx=14,pady=12)
  tk.Label(self,text='Destination animation / layer',bg=BG,fg=TEXT).grid(row=1,column=0,padx=14,sticky='w')
  self.animation=tk.StringVar();self.animation_box=ttk.Combobox(self,textvariable=self.animation,values=list(groups),state='readonly',width=80);self.animation_box.grid(row=1,column=1,sticky='ew',padx=14,pady=5)
  tk.Label(self,text='First destination frame',bg=BG,fg=TEXT).grid(row=2,column=0,padx=14,sticky='w')
  self.start_box=ttk.Combobox(self,state='readonly');self.start_box.grid(row=2,column=1,sticky='ew',padx=14,pady=5)
  self.overwrite=tk.BooleanVar(value=False);ttk.Checkbutton(self,text='Replace existing Input frames (back up first)',variable=self.overwrite).grid(row=3,column=0,columnspan=2,sticky='w',padx=14,pady=8)
  self.table=ttk.Treeview(self,columns=('source','target'),show='headings');self.table.heading('source',text='Selected PNG');self.table.heading('target',text='Destination frame');self.table.column('source',width=260);self.table.column('target',width=600);self.table.grid(row=4,column=0,columnspan=2,sticky='nsew',padx=14)
  self.note=tk.StringVar();tk.Label(self,textvariable=self.note,bg=BG,fg=MUTED,wraplength=900,justify='left').grid(row=5,column=0,columnspan=2,sticky='w',padx=14,pady=8)
  self.copy_button=ttk.Button(self,text='Copy sequence to Input',command=self.submit);self.copy_button.grid(row=6,column=1,sticky='e',padx=14,pady=12)
  self.animation_box.bind('<<ComboboxSelected>>',self.select_animation);self.start_box.bind('<<ComboboxSelected>>',self.preview);self.overwrite.trace_add('write',self.preview)
  selected=next((key for key in groups if (project/'Input'/key).resolve()==Path(files[0]).parent.resolve()),next((key for key in groups if Path(files[0]).name in [Path(r).name for r,e in groups[key]]),next(iter(groups))))
  self.animation.set(selected);self.select_animation()
 def select_animation(self,event=None):
  entries=self.groups[self.animation.get()];names=[Path(r).name for r,e in entries];self.start_box['values']=names
  self.start_box.current(names.index(Path(self.files[0]).name) if Path(self.files[0]).name in names else 0);self.preview()
 def preview(self,*args):
  self.table.delete(*self.table.get_children());entries=self.groups[self.animation.get()];start=self.start_box.current()
  for source,(route,entry) in zip(self.files,entries[max(0,start):]):self.table.insert('',tk.END,values=(Path(source).name,Path(route).name))
  try:
   mapping=plan_sequence(self.project,self.files,self.animation.get(),start,self.overwrite.get());self.note.set(f'{len(mapping)} frames mapped consecutively. Check the starting frame and mapping before copying. Existing Input backups go into Sequence Imports.');self.copy_button.state(['!disabled'])
  except Exception as exc:self.note.set(str(exc));self.copy_button.state(['disabled'])
 def submit(self):
  try:plan_sequence(self.project,self.files,self.animation.get(),self.start_box.current(),self.overwrite.get())
  except Exception as exc:messagebox.showerror('Cannot stage animation',str(exc),parent=self);return
  self.app.import_sequence(self.project,self.files,self.animation.get(),self.start_box.current(),self.overwrite.get());self.destroy()

def main():
 if '--smoke-test' in sys.argv:
  app=App();app.withdraw();app.update_idletasks();assert len(app.vars)==19 and len(app.tabs.tabs())==3;app.destroy();Path(sys.argv[sys.argv.index('--smoke-test')+1]).write_text(json.dumps(dict(ui='passed',characters=19,tabs=['Export project','Import replacements','Sort between projects'])))
 elif '--self-test' in sys.argv:
  import test_workshop
  test_workshop.run(Path(sys.argv[sys.argv.index('--self-test')+1]))
 elif '--verify' in sys.argv:
  import verify
  verify.run(Path(sys.argv[sys.argv.index('--verify')+1]))
 else:App().mainloop()
