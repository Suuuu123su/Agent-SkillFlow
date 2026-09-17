from pathlib import Path
import json,hashlib,zipfile,subprocess
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];P4=OUT.parent/'p4-20260917-123623';P3R=ROOT/'论文材料/P3_机制测量/p3r-20260917-103400'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
task=Path('C:/Users/Suziyu/Downloads/SkillFlow_P4_收尾_Codex任务包.zip')
with zipfile.ZipFile(task) as z:
 for m in z.infolist():
  p=(OUT/'task_pack'/m.filename).resolve();assert p.is_relative_to((OUT/'task_pack').resolve());p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(m))
pack=OUT/'task_pack/SkillFlow_P4_Closeout_Codex';man=json.loads((pack/'MANIFEST.json').read_text(encoding='utf-8-sig'));print('TASK_MANIFEST',json.dumps(man,ensure_ascii=False))
archive=P4/'p4-evidence-ablation-review.zip';expected='dcda387b143a72eb56dd53a1a03fe5aa934462eccf974181025b868bd8c1265d';assert sha(archive)==expected
pm=json.loads((P4/'MANIFEST.json').read_text(encoding='utf-8-sig'));checks=[]
with zipfile.ZipFile(archive) as z:
 for f in pm['files']:
  b=z.read(f['path']);h=hashlib.sha256(b).hexdigest();local=sha(P4/f['path']);checks.append({'path':f['path'],'archive_hash_ok':h==f['sha256'],'local_hash_ok':local==f['sha256'],'sha256':f['sha256']});assert h==local==f['sha256']
head=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip();status=subprocess.run(['git','-C',str(ROOT),'status','--short','--untracked-files=no'],capture_output=True,text=True,check=True).stdout; (OUT/'checks/git-status-before.txt').write_text(status,encoding='utf-8');modified=subprocess.run(['git','-C',str(ROOT),'diff','--name-only'],capture_output=True,text=True,check=True).stdout.splitlines();baseline={r:sha(ROOT/r) for r in modified if (ROOT/r).is_file()};dump(OUT/'checks/WORKSPACE_BASELINE.json',baseline)
dump(OUT/'checks/INPUT_BINDING.json',{'task_zip':str(task),'task_zip_sha256':sha(task),'p4_zip':str(archive),'p4_zip_sha256':expected,'upload_alias':'d7d17ed8-b367-456e-b589-4e2c71bafa7d.zip','members':len(checks)+1,'member_checks':checks,'current_head':head,'historical_head_not_checkout_target':True,'baseline_modified_files':len(baseline)})
print('OUT',OUT);print('P4_VERIFIED',len(checks),'SOURCE_STATE',json.loads((P4/'P4_STATUS.json').read_text(encoding='utf-8'))['status'])
