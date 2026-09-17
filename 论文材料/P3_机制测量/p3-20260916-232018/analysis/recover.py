"""P3 phase A: saved facts -> fresh projections and metrics; never reads old scores.
Run with existing .venv-skillflow Python, -B; all output is confined to this run.
"""
import sys, os, json, hashlib, csv, datetime, socket
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
READS = set()
def audit(event, args):
    if event.startswith(('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system')):
        raise RuntimeError('P3 forbids network/process execution: ' + event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        p = Path(os.fsdecode(args[0])).resolve()
        mode = args[1] or ''
        flags = args[2] or 0
        if any(c in str(mode) for c in 'wax+') or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            if not p.is_relative_to(OUT): raise RuntimeError('P3 write outside output: ' + str(p))
        else:
            if p.suffix.lower() in {'.dpapi', '.env'} or any(s in p.name.lower() for s in ('key_keeper', 'key-keeper')) or (p.suffix.lower() not in {'.py','.pyc'} and any(s in p.name.lower() for s in ('credential', 'secret'))):
                raise RuntimeError('P3 prohibited secret-related read: ' + str(p))
            READS.add(str(p))
sys.addaudithook(audit)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')
def lines(name, rows):
    with (OUT/name).open('w', encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False, default=str)+'\n')
def csvout(name, rows):
    rows=list(rows)
    if not rows: return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else v for k,v in r.items()})

from skillflow.experiment.t17.v2.dataset_rows import CoreRow, ReplayRow
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.metrics import metric_vector
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof
from skillflow.experiment.t17.v2.canonical import model_digest

COLLECTION=ROOT/'datasets/t17-v2'
collection=json.loads((COLLECTION/'dataset-manifest.json').read_text('utf-8'))
inventory=[];coverage=[];groups={};raw_by_phase={};all_metrics=[];fresh_vectors={}
projections=[];replay_facts=[];hash_errors=[]
for phase, ref in collection['stages'].items():
    directory=COLLECTION/ref['directory']
    mf=directory/'dataset-manifest.json'
    manifest=json.loads(mf.read_text('utf-8'))
    inventory.append({'path':mf.relative_to(ROOT).as_posix(),'sha256':sha(mf),'expected_sha256':ref['manifest']['sha256'],'phase':phase,'layer':'frozen_design_and_contract'})
    if sha(mf)!=ref['manifest']['sha256']: hash_errors.append(str(mf))
    for name, entry in manifest['files'].items():
        p=directory/name
        actual=sha(p) if p.exists() else None
        is_score=name.startswith(('reports','metrics-', 'condition-summary','skill-comparison','model-comparison','defense-comparison','README'))
        inventory.append({'path':p.relative_to(ROOT).as_posix(),'phase':phase,'sha256':actual,'expected_sha256':entry['content']['sha256'],'size_bytes':p.stat().st_size if p.exists() else None,'records':entry['record_count'],'layer':'historical_scores_hash_only' if is_score else 'raw_or_exported_facts','hash_match':actual==entry['content']['sha256']})
        if actual!=entry['content']['sha256']:hash_errors.append(str(p))
    def read_table(name):
        result=[]
        for part in manifest['tables'][name]:
            with (directory/part).open(encoding='utf-8') as f:
                for number,line in enumerate(f,1):
                    result.append((json.loads(line),f'{(directory/part).relative_to(ROOT).as_posix()}#L{number}'))
        return result
    raws=read_table('core-trials.jsonl');rraws=read_table('replay-pairs.jsonl')
    raw_by_phase[phase]=(raws,rraws)
    cores=[];replays=[]
    for raw,loc in raws:
        c=CoreRow.model_validate(raw).restore();cores.append(c)
        d=c.data
        projections.append({'phase':phase,'source_ref':loc,'identity':raw['identity'],'run_id':c.run_id,'status':c.status,'issues':raw['issues'],'behaviors':[x.behavior for x in c.decisions],'metadata':None if d is None else raw['data']['metadata'],'proof':None if d is None else d.proof.model_dump(mode='json')})
    by_trial={c.identity.trial_id:c for c in cores}
    for raw,loc in rraws:
        r=ReplayRow.model_validate(raw).restore(by_trial[raw['identity']['trial_id']])
        recomputed=None
        if r.proof:
            q=r.proof;recomputed=build_replay_proof(q.source,q.original,q.neutral,q.selector,q.manifest)
            if recomputed!=q:raise ValueError('Replay fact proof drift: '+loc)
        replays.append(r)
        replay_facts.append({'phase':phase,'source_ref':loc,'identity':raw['identity'],'source_core_run_id':r.source_core_run_id,'target_alias':r.target_alias,'status':r.status,'reason':r.reason,'proof_recomputed':recomputed is not None,'proof':None if recomputed is None else recomputed.model_dump(mode='json',exclude={'source','original','neutral'})})
    config=V2Configuration.model_validate(manifest['stages'][0]['configuration'])
    group=AnalysisGroup(config,tuple(cores),tuple(replays),(manifest['stages'][0]['raw_manifest']['sha256'],))
    groups[phase]=group
    coverage.append({'phase':phase,'domain':cores[0].identity.domain,'scheduled_core':manifest['scheduled_core'],'observed_core':len(cores),'unique_core_ids':len({c.identity.unit_id for c in cores}),'scheduled_replay':manifest['scheduled_replay'],'observed_replay':len(replays),'unique_replay_ids':len({r.identity.unit_id for r in replays}),'core_parts':manifest['tables']['core-trials.jsonl'],'replay_parts':manifest['tables']['replay-pairs.jsonl'],'complete':group.complete,'replay_complete':group.replay_complete})
    print(f'FACTS {phase}: cores={len(cores)} replays={len(replays)} validated',flush=True)

if hash_errors:dump('audit/INPUT_HASH_ERRORS.json',hash_errors);raise RuntimeError('Input hash mismatch')
lines('facts/CORE_PROJECTIONS.jsonl',projections)
lines('facts/REPLAY_PROJECTIONS.jsonl',replay_facts)
dump('audit/INPUT_COVERAGE.json',coverage)
dump('SOURCE_MANIFEST.json',{'local_head':(OUT/'audit/head.txt').read_text('utf-8-sig').strip(),'sources':inventory,'historical_scores_read_for_calculation':False,'all_hashes_match':True})
combined=AnalysisGroup(groups['f'].configuration,groups['f'].cores+groups['h'].cores,groups['f'].replays+groups['h'].replays)
assert (len(combined.cores),len(combined.replays))==(630,540)
for mode in ('monitor','enforce'):
    groups['fh_'+mode]=combined.select(tuple(c for c in combined.cores if c.identity.enforcement_mode.value==mode))
for name,g in groups.items():
    values=metric_vector(g)
    fresh_vectors[name]={k:v.model_dump(mode='json') for k,v in values.items()}
    for metric,m in values.items():
        v=m.model_dump(mode='json');count=v['unit'] in ('effect_count','request_count','type_count','edge_count','step_count','origin_membership_count','unit_effect_weight')
        all_metrics.append({'study':'T17-v2','phase':name,'domain':g.cores[0].identity.domain,'model_config':g.cores[0].identity.requested_model,'method_version':'T17-v2:'+','.join(sorted({c.identity.enforcement_mode.value for c in g.cores})),'metric_id':metric,'contract_version':'t17-v2-local-head','population_id':name,'unit':v['unit'],'value':v['value'],'numerator':None if metric.startswith('hiaa.') and metric.endswith(('scheduled','valid_only')) else v['numerator'],'denominator':None if count or metric.startswith('hiaa.') and metric.endswith(('scheduled','valid_only','potential')) else v['denominator'],'original_representation_numerator':v['numerator'],'original_representation_denominator':v['denominator'],'scheduled':len(g.replays) if metric.startswith(('ci.','replay_')) else len(g.cores),'observed':sum(c.data is not None for c in g.cores),'unknown':sum(c.data is None for c in g.cores),'status':v['status'],'recovery_status':'RECOMPUTED_FROM_EXPORTED_FACTS','missing_reason':v.get('reason'),'confidence_interval':v.get('intervals',[]),'interval_kind':'original_frozen_contract','cluster_unit':'semantic_template_id','cells_or_pairs_file':'facts/CORE_PROJECTIONS.jsonl;facts/REPLAY_PROJECTIONS.jsonl','source_refs':v['evidence_ids'],'calculation_code_hash':sha(Path(__file__)),'computed_from_raw':True,'computation_level':'public_exported_structured_facts_original_algorithm','independent_check_status':'PENDING','historical_report_value':None,'comparison_status':'NOT_YET_READ','limitations':'public exporter/instrumentation trust; no private text or provider request verification'})
    print(f'METRICS {name}: {len(values)} saved',flush=True)
    dump('facts/FRESH_VECTORS.json',fresh_vectors)
lines('METRICS_LONG.jsonl',all_metrics);csvout('METRICS_LONG.csv',all_metrics)
dump('audit/FIRST_COMPUTATION_SEAL.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{n:sha(OUT/n) for n in ['METRICS_LONG.jsonl','facts/FRESH_VECTORS.json','facts/CORE_PROJECTIONS.jsonl','facts/REPLAY_PROJECTIONS.jsonl']},'old_report_contents_read':False,'note':'Task-package 02 contained historical reference numbers incidentally; no reference scores were computation inputs.','live_calls':0,'business_replays':0})
modules={str(Path(m.__file__).resolve()) for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and str(ROOT/'src') in str(Path(m.__file__).resolve()) and Path(m.__file__).suffix=='.py'}
dump('audit/ANALYSIS_CODE_MANIFEST.json',[{'path':Path(p).relative_to(ROOT).as_posix(),'sha256':sha(Path(p))} for p in sorted(modules)])
dump('audit/PROCESS_GUARD.json',{'network':'audit hook blocks connect/bind/DNS','subprocess':'blocked','writes':'output directory only','sdk_initialized':False,'business_replay_executed':False,'read_paths':sorted(READS)})
print('PHASE_A_COMPLETE: results sealed before historical report comparison',flush=True)


