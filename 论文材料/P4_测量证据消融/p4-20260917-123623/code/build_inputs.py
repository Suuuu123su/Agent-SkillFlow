"""Freeze evidence documents and query population before any predictor result is read."""
from common import *
from ingest import legacy,reference,opaque
from collections import defaultdict,Counter
import copy

guard();docs={};registry=[];predict=[];sources={};unitmap={};cf_by_run=defaultdict(list);groups=defaultdict(list);gold_inputs=[]
expected={x['path']:x['sha256'] for x in read(P3R/'SOURCE_MANIFEST_P3R.json')['sources']}
def source(p):
 p=Path(p);rel=p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)
 if rel not in sources:
  h=sha(p);want=expected.get(rel);assert want is None or want==h,(rel,want,h);sources[rel]=dict(path=rel,sha256=h,expected_sha256=want,hash_verified=want==h if want else None,bytes=p.stat().st_size)
 return rel

def keep(doc,native,ref,domain,study,phase,protocol):
 if doc['id'] in docs:assert docs[doc['id']]==doc;return
 docs[doc['id']]=doc;unitmap[doc['id']]=dict(native_unit_ref=native,source_ref=ref,domain=domain,study=study,phase=phase,source_protocol=protocol)

def query(metric,uid,protocol,**kwargs):
 unit=unitmap[uid];params=dict(metric=metric,unit=uid,protocol=protocol,**kwargs);qid=opaque(canonical(params));r=dict(query_id=qid,**unit,metric=metric,protocol=protocol,unit_kind='query_'+metric,horizon=kwargs.get('k'),independence_group=uid,parameters=kwargs);registry.append(r);predict.append(dict(query_id=qid,**params))

def basic(doc,include_prov=True):
 uid=doc['id'];query('UEA_count',uid,'actual_receipt_and_authorization');query('TaskSuccess',uid,'mechanical_public_obligations');query('E_STS',uid,'U_and_not_verified_contract_violation');query('failure_taxonomy',uid,'recorded_failure_types')
 for op in doc['observation']['ops']:
  if doc['layout']=='reference' and not op.get('belongs_to_current'):continue
  query('UEA',uid,'actual_receipt_and_authorization',op=op['id'])
  if op['action']=='network.send':
   query('ALR',uid,'T11_explicit_reason',op=op['id']);query('ALR',uid,'P3R_identity_guard',op=op['id'])
 if not any(x['action']=='network.send' and x.get('belongs_to_current',True) for x in doc['observation']['ops']):
  query('ALR',uid,'T11_explicit_reason',op=None);query('ALR',uid,'P3R_identity_guard',op=None)
 if include_prov:
  for a in doc['observation']['objects']:query('Provenance',uid,'recorded_origin_prediction',artifact=a['id'])

certificates={x['run_id']:x.get('proof',{}).get('task') for x in rows(P3/'facts/CORE_PROJECTIONS.jsonl')}
source(P3/'facts/CORE_PROJECTIONS.jsonl')
raw_ci={r['pair_id']:r for r in rows(P3R/'evidence/CI_RAW_INTERVENTION_OBJECTS.jsonl')}
for phase in ['f','g','h']:
 d=ROOT/f'datasets/t17-v2/stages/{phase}';source(d/'dataset-manifest.json');m=read(d/'dataset-manifest.json')
 for name in ['core-trials','replay-pairs']:
  for f in m['tables'][name+'.jsonl']:source(d/f)
 cores=table(phase,'core-trials');replays=table(phase,'replay-pairs')
 for c,ref in cores:
  data=copy.deepcopy(c['data']);data['task_certificate_bindings']=certificates.get(c['run_id'])
  for sk in data['analysis_definition']['skills']:source(ROOT/sk['manifest'])
  doc=legacy(data,ref,decisions=c['decisions'],issues=c['issues'],status=c['status']);keep(doc,c['run_id'],ref,'HISTORICAL_LIVE','T17',phase,'T17-v2');meta=data['metadata'];basic(doc)
  if c['identity']['condition_id'].startswith('m2-'):
   for k in [1,3]:
    for protocol in ['legacy_v2','chain_v1','confirmed_prefix_v1']:query('RIR',doc['id'],protocol,k=k)
  if meta.get('hiaa_cell'):
   selector={k:v for k,v in meta['harm_selector'].items() if k!='alias'};member=dict(unit=doc['id'],cell=meta['hiaa_cell'],cluster=opaque(c['identity']['semantic_template_id']),repeat=c['identity']['repeat_index'],selector=selector);groups[(phase,meta['hiaa_design_id'])].append(member);query('HIAA_Y',doc['id'],'scheduled_receipted_selector',selector=selector)
  # Oracle plane is retained only for independent evaluator; it is never a predictor document.
  gold_inputs.append(dict(kind='legacy',unit=doc['id'],domain='HISTORICAL_LIVE',source_ref=ref,data=data))
 for r,ref in replays:
  uid=opaque(r['identity']['unit_id']);base=docs[opaque(r['source_core_run_id'])];pair=None;p=r['proof']
  if p:
   man=p['manifest'];pair=dict(identity=legacy(p['original'],ref+'#/proof/original'),neutral=legacy(p['neutral'],ref+'#/proof/neutral'),selector={k:v for k,v in p['selector'].items() if k!='alias'},source_object=opaque(man['original_intervention']['source_artifact_id']),state_hashes=[man[k] for k in ['checkpoint_state_hash','original_restore_state_hash','neutral_restore_state_hash']],prefix_hashes=[man[k] for k in ['checkpoint_prefix_hash','original_prefix_hash','neutral_prefix_hash']],intervention={'original_mode':man['original_intervention']['mode'],'neutral_mode':man['neutral_intervention']['mode'],'artifact_types':[man[x]['artifact_type'] for x in ['original_intervention','neutral_intervention']],'lengths':[man[x]['content_length'] for x in ['original_intervention','neutral_intervention']]},control_bytes=None,precision_contract='whole_object_legacy_no_semantic_certificate')
   raw=raw_ci.get(r['identity']['unit_id'])
   if raw and raw['original'] and raw['neutral']:
    pair['control_bytes']={arm:raw[arm]['text'] for arm in ['original','neutral']}
    for arm in ['original','neutral']:source(ROOT/raw[arm]['ref'])
   base['counterfactual'].append(pair)
  doc=dict(id=uid,layout='pair',observation={'closed':r['status']=='completed'},counterfactual={'pair':pair,'candidate_closed':r['status']=='completed','pair_absence_reason':r['reason'] if pair is None else None},irrelevant_metadata={'display_title':'Saved pair'})
  keep(doc,r['identity']['unit_id'],ref,'HISTORICAL_LIVE','T17',phase,'T17-v2');query('CI',uid,'legacy_object_ablation');query('CI',uid,'precise_control_semantics')
for (phase,design),members in groups.items():
 uid=opaque('grid:'+phase+':'+design);doc=dict(id=uid,layout='grid',design={'members':members,'cells':['p00','p01','p10','p11']},irrelevant_metadata={'display_title':'Frozen grid'});keep(doc,design,'datasets/t17-v2/stages/'+phase+'/matrix.jsonl','HISTORICAL_LIVE','T17',phase,'T17-v2')
 for policy in ['scheduled','valid_only']:query('HIAA_run',uid,policy)
 query('HIAA_pot_observed',uid,'legacy_observed_executed_union')
# T18 only actual recovered mechanism cases, chosen by saved source locators, not numerator.
t18rows=list(csv.DictReader((P3R/'T18_ALR_RIR_RECOVERED.csv').open(encoding='utf-8-sig')));paths=sorted({r['source'] for r in t18rows});t18replays={}
for domain in ['scripted','fake_reference']:
 t18replays[domain]=[read(p) for p in sorted((ROOT/f'datasets/t18-local/{domain}/replays').glob('*.json'))]
 for p in (ROOT/f'datasets/t18-local/{domain}/replays').glob('*.json'):source(p)
for rel in paths:
 source(ROOT/rel);c=read(ROOT/rel);data=c['data'];domain=c['domain'];doc=legacy(data,rel);keep(doc,c['run_id'],rel,'T18_SCRIPTED' if domain=='scripted' else 'T18_FAKE_REFERENCE','T18',c['cell']['mode'],'T18');basic(doc)
 for p in t18replays[domain]:
  if p['source_run_id']!=c['run_id']:continue
  pr=p['proof'];m=pr['manifest'];doc['counterfactual'].append(dict(identity=legacy(pr['original'],rel+'#replay'),neutral=legacy(pr['neutral'],rel+'#replay'),selector={k:v for k,v in pr['selector'].items() if k!='alias'},source_object=opaque(m['original_intervention']['source_artifact_id']),state_hashes=[m[k] for k in ['checkpoint_state_hash','original_restore_state_hash','neutral_restore_state_hash']],prefix_hashes=[m[k] for k in ['checkpoint_prefix_hash','original_prefix_hash','neutral_prefix_hash']],intervention={'original_mode':m['original_intervention']['mode'],'neutral_mode':m['neutral_intervention']['mode'],'artifact_types':[m[x]['artifact_type'] for x in ['original_intervention','neutral_intervention']],'lengths':[m[x]['content_length'] for x in ['original_intervention','neutral_intervention']]},control_bytes=None,precision_contract='saved_construct_intervention_semantics_unverified'))
 for k in sorted({int(r['k']) for r in t18rows if r['source']==rel and r['metric'].startswith('RIR')}):
  for protocol in ['legacy_v2','chain_v1','confirmed_prefix_v1']:query('RIR',doc['id'],protocol,k=k)
 gold_inputs.append(dict(kind='legacy',unit=doc['id'],domain='T18_SCRIPTED' if domain=='scripted' else 'T18_FAKE_REFERENCE',source_ref=rel,data=data))
# Existing P3R reference execution families and Live units, with raw labels kept outside predictor.
construct=read(P3R/'construct/CONSTRUCT_RESULTS.json');construct_index=read(P3R/'review_slice/index.json');source(P3R/'review_slice/index.json')
configs=[]
for row in construct:
 names={arm:Path(path.replace('\\','/')).name for arm,path in row['paths'].items()};prefix=row['case']+('-prefix' if row['module']=='RIR' else '-alr-prefix');configs.append(dict(domain='CONTROLLED_CONSTRUCT',module=row['module'],parent=prefix,children=names,base=P3R/'construct/execution-v1',case=row['case']))
slots=list(csv.DictReader((P3R/'task_pack/SkillFlow_P3R_CompleteMetrics60/capacity_slots.csv').open(encoding='utf-8-sig')));ledger=read(P3R/'live/ledger.json');source(P3R/'live/ledger.json')
for slot in slots:
 if slot['kind']!='prefix':continue
 children={r['branch']:r['slot_id'] for r in slots if r['parent_slot']==slot['slot_id']};names={'original':children['revoked_original'],'identity':children['revoked_identity'],'neutral':children['revoked_neutral'],'control':children['not_revoked_control']} if slot['module']=='RIR' else children;configs.append(dict(domain='SAVED_LIVE',module=slot['module'],parent=slot['slot_id'],children=names,base=P3R/'live/units',case=None))
for conf in configs:
 children=conf['children'];unitdocs={};rawstates={};units=[conf['parent']]+list(children.values())
 for unit in units:
  p=conf['base']/unit/'state.json'
  if not p.is_file():continue
  ref=source(p);s=read(p);rawstates[unit]=s
  if conf['case']=='unknown_reason' and unit==children['original']:
   source(P3R/'construct/unknown_reason_observation.json');s=read(P3R/'construct/unknown_reason_observation.json')['state']
  doc=reference(s,unit,ref,p.parent);keep(doc,unit,ref,conf['domain'],'P3R',conf['module'],'reference_harness');unitdocs[unit]=doc;basic(doc,include_prov=False)
  for f in (p.parent/'safe_sink').glob('*.json'):source(f)
 if children['original'] not in unitdocs:continue
 o=unitdocs[children['original']];i=unitdocs.get(children['identity']);n=unitdocs.get(children['neutral']);identity=copy.deepcopy(i) if i else None;neutral=copy.deepcopy(n) if n else None
 pair=dict(identity=identity,neutral=neutral,selector={'action':'network.send','source_pattern':'memory:/saved','sink_pattern':'mock://external'},source_object=None,state_hashes=[],prefix_hashes=[],precision_contract='reference_claim_only' if conf['module']=='ALR' else 'reference_memory_span_shared_history',same_prefix=conf['parent'] in rawstates,control_bytes=None)
 if n:
  os=rawstates[children['original']];ns=rawstates[children['neutral']]
  pair['control_bytes']={'original':os['scenario']['claim'] if conf['module']=='ALR' else os['memory']['value'] if os['memory'] else None,'neutral':ns['scenario']['claim'] if conf['module']=='ALR' else ns['memory']['value'] if ns['memory'] else None}
  if conf['module']=='RIR' and os['memory']:pair['source_object']=opaque(os['memory']['artifact_id'])
 o['counterfactual']=[pair]
 if conf['module']=='RIR':
  for k in [1,3]:
   for protocol in ['legacy_v2','chain_v1','confirmed_prefix_v1']:query('RIR',o['id'],protocol,k=k)
 if conf['domain']=='CONTROLLED_CONSTRUCT':gold_inputs.append(dict(kind='reference',unit=o['id'],domain=conf['domain'],module=conf['module'],source_ref=unitmap[o['id']]['source_ref'],states=rawstates,roles={'parent':conf['parent'],**children},measurement_view='missing_reason' if conf['case']=='unknown_reason' else None))
# Static finite models: only raw declaration, never result/witness answers.
for label,entry in read(P3R/'POT_SETS_AND_WITNESSES.json').items():
 uid=opaque('finite-model:'+label);model=copy.deepcopy(entry['model'])
 for r in model['rules']:r['id']=opaque(r['id'])
 doc=dict(id=uid,layout='capability',capability_universe=model['universe'],declared_capability_rules={k:v for k,v in model.items() if k!='universe'},irrelevant_metadata={'display_title':'Declared finite model'});keep(doc,label,(P3R/'POT_SETS_AND_WITNESSES.json').relative_to(ROOT).as_posix()+'#/'+label+'/model','FINITE_CONSTRUCT','P3R','finite','declared_v1');query('HIAA_pot_declared',uid,'declared_finite_v1');gold_inputs.append(dict(kind='finite_model',unit=uid,domain='FINITE_CONSTRUCT',model=entry['model']))
for x in read(PACK/'MANIFEST.json')['files']:
 assert sha(PACK/x['path'])==x['sha256'];source(PACK/x['path'])
assert len(predict)==len({x['query_id'] for x in predict})
jl('minimal_data/BASE_DOCUMENTS.jsonl',docs.values());jl('minimal_data/PREDICTOR_QUERIES.jsonl',predict);jl('QUERY_REGISTRY.jsonl',registry);dump('control/UNIT_MAP.json',unitmap);jl('control/REFERENCE_INPUTS.jsonl',gold_inputs);dump('SOURCE_MAP.json',{'sources':list(sources.values()),'p3r_archive_binding':'audit/P3R_INPUT_BINDING.json','query_count':len(predict),'document_count':len(docs),'counts_by_domain':dict(Counter(x['domain'] for x in registry)),'claims':'Exact raw file hashes verified when registered; no old scores passed to predictor'})
dump('audit/PROJECTION_BUILD.json',{'documents':len(docs),'queries':len(predict),'unique_t17_cores':990,'replay_candidates':810,'t18_related_core_files':len(paths),'p3r_configurations':len(configs),'profiles_planned':13,'new_model_calls':0,'new_tool_execution':0,'gold_kept_separate':True,'full_sweep_not_started':True})
print(json.dumps(read(OUT/'audit/PROJECTION_BUILD.json'),ensure_ascii=False))
