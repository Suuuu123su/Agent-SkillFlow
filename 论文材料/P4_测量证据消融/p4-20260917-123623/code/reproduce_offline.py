"""Portable offline reproduction. Default smoke; --full is an explicit later review action."""
import argparse,json,hashlib,sys,os,subprocess,shutil,time
from pathlib import Path
from views import project,PROFILES

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--full',action='store_true');ap.add_argument('--out');args=ap.parse_args();bundle=Path(__file__).resolve().parents[1];dest=Path(args.out).resolve() if args.out else bundle/'reproductions'/('review-'+time.strftime('%Y%m%d-%H%M%S'));assert dest.is_relative_to(bundle),'write only a new directory under this bundle';assert not dest.exists();dest.mkdir(parents=True)
 allowed_commands=set()
 def audit(ev,argv):
  if ev.startswith('socket.'):raise RuntimeError('OFFLINE_NO_NETWORK')
  if ev=='subprocess.Popen':
   cmd=argv[1];command=cmd if isinstance(cmd,str) else subprocess.list2cmdline(cmd);assert command in allowed_commands and Path(argv[0]).resolve()==Path(sys.executable).resolve(),'only isolated local analyzer subprocess allowed'
  if ev=='open' and isinstance(argv[0],(str,bytes)):
   path=Path(os.fsdecode(argv[0])).resolve();mode=str(argv[1] or '');flags=argv[2] or 0
   if any(c in mode for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):assert path.is_relative_to(dest),'write outside fresh reproduction directory'
   assert path.name not in ['auth.json','.env'] and path.suffix!='.dpapi','credential read forbidden'
 sys.addaudithook(audit)
 readrows=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
 write=lambda p,x:p.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for r in x),encoding='utf-8')
 docs=readrows(bundle/'minimal_data/BASE_DOCUMENTS.jsonl');queries=readrows(bundle/'minimal_data/PREDICTOR_QUERIES.jsonl');reg=readrows(bundle/'QUERY_REGISTRY.jsonl');registry={r['query_id']:r for r in reg};selected=set();seen=set()
 for q in queries:
  r=registry[q['query_id']];key=(r['domain'],r['metric'],r['protocol'])
  if key not in seen:selected.add(q['query_id']);seen.add(key)
 for c in json.loads((bundle/'CASEBOOK.json').read_text(encoding='utf-8')):selected.add(c['query_id'])
 if not args.full:queries=[q for q in queries if q['query_id'] in selected]
 for d in ['results','audit','control','minimal_data','checks','tables']:(dest/d).mkdir()
 write(dest/'QUERY_REGISTRY.jsonl',[r for r in reg if r['query_id'] in {q['query_id'] for q in queries}]);write(dest/'minimal_data/PREDICTOR_QUERIES.jsonl',queries);shutil.copyfile(bundle/'minimal_data/BASE_DOCUMENTS.jsonl',dest/'minimal_data/BASE_DOCUMENTS.jsonl');shutil.copyfile(bundle/'minimal_data/REFERENCE_INPUTS_MIN.jsonl',dest/'control/REFERENCE_INPUTS.jsonl');shutil.copyfile(bundle/'control/SAVED_LIVE_SLOT_METADATA.json',dest/'control/SAVED_LIVE_SLOT_METADATA.json')
 errors=[];checks=[]
 for vid in PROFILES:
  view=dest/'views'/vid;view.mkdir(parents=True);write(view/'DOCUMENTS.jsonl',[project(d,vid) for d in docs]);pq=[]
  for q in queries:
   x=project(q,vid);x['query_id']=q['query_id'];pq.append(x)
  write(view/'QUERIES.jsonl',pq);command=[sys.executable,'-X','utf8','-B',str(bundle/'code/run_predictor.py'),str(view),str(dest/f'results/{vid}.jsonl'),str(dest/f'audit/full-{vid}.json')];allowed_commands.add(subprocess.list2cmdline(command));proc=subprocess.run(command,executable=sys.executable,capture_output=True,text=True,encoding='utf-8');assert proc.returncode==0,proc.stdout+proc.stderr
  # Comparator reads expected archived outputs only AFTER this isolated prediction is sealed.
  expected={r['query_id']:r for r in readrows(bundle/f'results/{vid}.jsonl')};actual=readrows(dest/f'results/{vid}.jsonl');diff=[p['query_id'] for p in actual if p!=expected[p['query_id']]];errors+=diff;checks.append(dict(view=vid,queries=len(actual),exact_archived_prediction_differences=len(diff)))
 if args.full:
  import common
  common.OUT=dest
  import independent_reference
  independent_reference.main()
  import aggregate
  aggregate.main()
 result=dict(mode='full_explicit_review' if args.full else 'portable_smoke',queries=len(queries),views=13,results=len(queries)*13,errors=errors,checks=checks,new_model_calls=0,new_business_tool_calls=0,network_calls=0,source_bundle=str(bundle),output=str(dest));(dest/'PORTABLE_RECOMPUTE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));assert not errors
if __name__=='__main__':main()
