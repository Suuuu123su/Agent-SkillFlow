"""Fresh process predictor. Reads only the supplied projected view and its query list."""
import sys,json,hashlib,time,os
from pathlib import Path
from predictor import Analyzer

def main():
 view=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();auditfile=Path(sys.argv[3]).resolve();code=Path(__file__).resolve().parent
 # Import everything before installing the restrictive file audit; no dynamic user code.
 accesses=[];denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.','os.system')):denied.append(event);raise RuntimeError('OFFLINE_PROCESS_NETWORK_DENIED')
  if event=='open' and isinstance(args[0],(str,bytes)):
   path=Path(os.fsdecode(args[0])).resolve();mode=str(args[1] or '');flags=args[2] or 0;write=any(c in mode for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT)
   allowed=path in [output,auditfile] if write else path.is_relative_to(view) or path.is_relative_to(code)
   if path.name in ['auth.json','.env'] or path.suffix=='.dpapi':allowed=False
   if not allowed:denied.append(str(path));raise RuntimeError('OUTSIDE_PERMITTED_VIEW')
   accesses.append({'path':str(path.relative_to(view)) if path.is_relative_to(view) else path.name,'operation':'write' if write else 'read'})
 sys.addaudithook(audit)
 if '--probe' in sys.argv:
  try:Path(sys.argv[sys.argv.index('--probe')+1]).read_text()
  except RuntimeError:pass
  else:raise AssertionError('Read isolation failed')
 raw=(view/'DOCUMENTS.jsonl').read_bytes();qr=(view/'QUERIES.jsonl').read_bytes();documents={x['id']:x for x in (json.loads(l) for l in raw.decode('utf-8-sig').splitlines())};queries=[json.loads(l) for l in qr.decode('utf-8-sig').splitlines()];a=Analyzer(documents);codehash=hashlib.sha256((code/'predictor.py').read_bytes()).hexdigest();start=time.time();errors=[]
 with output.open('x',encoding='utf-8') as f:
  for q in queries:
   try:r=a.run(q)
   except Exception as ex:
    r=dict(query_id=q['query_id'],metric=q['metric'],protocol=q['protocol'],eligibility=None,status='analysis_error',value=None,lower=None,upper=None,reason=type(ex).__name__+':'+str(ex),used_evidence=sorted(a.reads),missing_evidence=sorted(a.missing),minimal_proof={});errors.append({'query_id':q['query_id'],'error':r['reason']})
   r['analysis_code_hash']=codehash;f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
 auditfile.write_text(json.dumps({'documents_sha256':hashlib.sha256(raw).hexdigest(),'queries_sha256':hashlib.sha256(qr).hexdigest(),'analysis_code_hash':codehash,'queries':len(queries),'documents':len(documents),'file_accesses':accesses,'blocked_accesses':denied,'errors':errors,'elapsed_seconds':time.time()-start,'network_calls':0,'business_tool_calls':0,'model_calls':0},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'queries':len(queries),'errors':len(errors),'seconds':round(time.time()-start,3)}));assert not errors,errors[:2]
if __name__=='__main__':main()
