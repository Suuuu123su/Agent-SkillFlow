from common import *
import zipfile

guard();archive=P3R/'p3r-completion-review.zip';assert sha(archive)=='3390b1e8dba914cc42088661b5378d139ddce177c551f4e0d70a3d74e47ee304';man=read(P3R/'BUNDLE_MANIFEST.json');checks=[]
with zipfile.ZipFile(archive) as z:
 for x in man['files']:
  b=z.read(x['path']);ok=hashlib.sha256(b).hexdigest()==x['sha256'];assert ok;checks.append(dict(path=x['path'],hash_ok=ok,local_matches=sha(P3R/x['path'])==x['sha256']))
dump('audit/P3R_INPUT_BINDING.json',{'archive_sha256':sha(archive),'entries':len(checks),'checks':checks})
pm=read(PACK/'MANIFEST.json');print('pack manifest shape',list(pm))
base={}
for rel in (OUT/'audit/tracked-modified-paths.txt').read_text(encoding='utf-8-sig').splitlines():
 if (ROOT/rel).is_file():base[rel]=sha(ROOT/rel)
dump('audit/USER_MODIFICATIONS_BASELINE.json',base)
dump('LOCAL_BINDINGS.json',{'root':str(ROOT),'head':'21efe89a11b56b2f48ae6f351ef46cca467913fb','p3r':str(P3R),'p3r_zip_sha256':sha(archive),'task_pack_zip_sha256':sha(Path('C:/Users/Suziyu/Downloads/SkillFlow_P4_测量证据消融_Codex任务包.zip')),'new_model_calls':0,'new_business_tool_calls':0,'scope':'P4 only; analysis process network and subprocess blocked'})
for name in ['core-trials','replay-pairs']:
 t=table('f',name);x=t[0][0];print(name,len(t),'keys',list(x));dump('audit/SCHEMA_'+name+'.json',x)
print('P3R members verified',len(checks),'local mismatches',sum(not x['local_matches'] for x in checks))
