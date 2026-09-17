from common import *
import zipfile,sys

def main():
 guard();candidate='--candidate' in sys.argv;name='checks/p4-candidate.zip' if candidate else 'p4-evidence-ablation-review.zip';paths=[]
 for p in OUT.iterdir():
  if p.is_file() and p.suffix in ['.md','.csv','.json','.jsonl'] and p.name not in ['MANIFEST.json','ZIP_RECEIPT.json','PACKAGE_VERIFICATION.json']:paths.append(p)
 for folder in ['code','minimal_data','results','tables','task_pack']:
  for p in (OUT/folder).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:paths.append(p)
 for p in (OUT/'checks').iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.csv']:paths.append(p)
 for p in (OUT/'audit').iterdir():
  if p.is_file() and not p.name.startswith('SCHEMA_'):paths.append(p)
 for p in ['control/UNIT_MAP.json','control/PROVENANCE_REFERENCE.jsonl','control/SAVED_LIVE_SLOT_METADATA.json','checks/minimal_reference_roundtrip/MINIMAL_REFERENCE_CHECK.json']:
  paths.append(OUT/p)
 paths=sorted(set(paths));assert all(p.is_relative_to(OUT) for p in paths);manifest={'schema':'P4_review_bundle/1','files':[dict(path=p.relative_to(OUT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in paths],'excluded':'reconstructible views; raw controller reference payloads; reproduction scratch; candidate zip; no credentials/provider logs','entrypoint':'code/reproduce_offline.py','full_results':252096};dump('MANIFEST.json',manifest)
 target=OUT/name;assert not target.exists()
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in paths+[OUT/'MANIFEST.json']:z.write(p,p.relative_to(OUT).as_posix())
 bad=[]
 with zipfile.ZipFile(target) as z:
  for f in manifest['files']:
   if hashlib.sha256(z.read(f['path'])).hexdigest()!=f['sha256']:bad.append(f['path'])
 assert not bad;record=dict(path=name,sha256=sha(target),bytes=target.stat().st_size,members=len(paths)+1,verified_member_hashes=len(paths),errors=bad)
 dump('checks/CANDIDATE_ZIP_CHECK.json' if candidate else 'ZIP_RECEIPT.json',record)
 if candidate:
  dest=OUT/'zip_validation';dest.mkdir()
  with zipfile.ZipFile(target) as z:
   for member in z.infolist():
    p=(dest/member.filename).resolve();assert p.is_relative_to(dest.resolve());p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(member))
  print('Extracted candidate into '+str(dest))
 print(canonical(record))
if __name__=='__main__':main()
