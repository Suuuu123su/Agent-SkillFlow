from common import *
from collections import Counter

guard();units=read(OUT/'control/UNIT_MAP.json');checks=[];counts=Counter();errors=[]
for uid,u in units.items():
 if u['study']!='P3R' or u['source_protocol']!='reference_harness':continue
 p=ROOT/u['source_ref'];s=read(p);events=s['events'];unit=u['native_unit_ref'];byid={e['id']:e for e in events}
 for i,e in enumerate(events):
  ok=e['seq']==i+1 and e['previous']==(digest(events[i-1]) if i else None);counts['event_links']+=1
  if not ok:errors.append([u['source_ref'],e['id'],'chain'])
  if e['kind']=='effect' and e['unit']==unit:
   receipt=e['receipt'];raw=(p.parent/receipt['file']).read_bytes();r={k:v for k,v in receipt.items() if k!='receipt_id'};ok=receipt['receipt_id']=='receipt:'+digest(r) and hashlib.sha256(raw).hexdigest()==receipt['sha256'] and len(raw)==receipt['byte_count'];counts['owned_receipts']+=1
   if not ok:errors.append([u['source_ref'],e['id'],'receipt'])
 for a in s['artifacts'].values():
  counts['artifact_hashes']+=1
  if digest(a['value'])!=a['sha256']:errors.append([u['source_ref'],a['id'],'artifact_hash'])
 counts['units']+=1
baseline=read(OUT/'audit/USER_MODIFICATIONS_BASELINE.json');modified=[rel for rel,h in baseline.items() if sha(ROOT/rel)!=h];assert not modified
src=read(OUT/'SOURCE_MAP.json')['sources'];changed=[s['path'] for s in src if sha(ROOT/s['path'])!=s['sha256']];assert not changed
assert not errors
dump('checks/INPUT_AND_CHAIN_VERIFICATION.json',{'checks':dict(counts),'errors':errors,'input_file_hashes_checked':len(src),'changed_input_files':changed,'user_modified_files_checked':len(baseline),'user_modifications_changed':modified,'original_archive_verified_before_projection':'audit/P3R_INPUT_BINDING.json','additional_chain_audit':'after full sweep; prior P3R chain audit reused through exact archive binding'})
print(canonical({'counts':dict(counts),'source_hashes':len(src),'errors':errors,'user_files_preserved':len(baseline)}))
