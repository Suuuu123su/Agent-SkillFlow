"""One read/aggregation pass over saved predictions. Never imports or calls a predictor."""
from common import *
from collections import Counter,defaultdict

def main():
 guard();assert not (OUT/'data/closeout_data.json').exists(),'one saved-prediction aggregation already exists'
 sources={}
 def src(p,role):
  p=Path(p);key=p.relative_to(ROOT).as_posix();sources[key]=dict(path=key,absolute_path=str(p),sha256=sha(p),bytes=p.stat().st_size,role=role);return key
 for f in read(PACK/'MANIFEST.json')['files']:assert sha(PACK/f['path'])==f['sha256'];src(PACK/f['path'],'task specification or existing external review; not current experiment')
 meta=read(P4/'P4_STATUS.json');src(P4/'P4_STATUS.json','original execution status')
 for f in ['P4_FINAL_REPORT.md','P4_METRIC_MAIN.md','LIMITATIONS_AND_GAPS.md','SOURCE_MAP.json','LOCAL_BINDINGS.json','METRIC_CONTRACTS.csv','METRIC_CONTRACTS.json','METRIC_CONTRACTS.md','MASK_DEPENDENCY_MAP.json','CASEBOOK.md','REPRODUCE.md','checks/PORTABLE_RECOMPUTE.json','checks/ZIP_ROUNDTRIP_RECOMPUTE.json','checks/FULL_EVALUATION.json']:
  src(P4/f,'existing P4 source, not new verification')
 registry=rows(P4/'QUERY_REGISTRY.jsonl');reg={r['query_id']:r for r in registry};src(P4/'QUERY_REGISTRY.jsonl','fixed query registry');contracts={r['metric']:r for r in csvread(P4/'METRIC_CONTRACTS.csv')};units={r['metric']:r['unit_kind'] for r in registry};slots=read(P4/'control/SAVED_LIVE_SLOT_METADATA.json');src(P4/'control/SAVED_LIVE_SLOT_METADATA.json','grouping ledger')
 gold={r['query_id']:r for r in rows(P4/'GOLD_PROVENANCE.jsonl')};goldsrc=src(P4/'GOLD_PROVENANCE.jsonl','existing independent reference; not new labels');savedscore=csvread(P4/'INDEPENDENT_REFERENCE_SCORES.csv');scoresrc=src(P4/'INDEPENDENT_REFERENCE_SCORES.csv','existing stratified reference scores');prior=rows(P4/'P4_METRIC_MAIN.jsonl');priorsrc=src(P4/'P4_METRIC_MAIN.jsonl','saved 4758 strata');src(P4/'P4_METRIC_MAIN.csv','saved published strata')
 witnesses=read(P4/'IDENTIFIABILITY_WITNESSES.json');wsrc=src(P4/'IDENTIFIABILITY_WITNESSES.json','two existing finite pairs');oldcases=read(P4/'CASEBOOK.json');csrc=src(P4/'CASEBOOK.json','existing cases');rebuild=csvread(P4/'TASK_EVIDENCE_RECONSTRUCTION.csv');src(P4/'TASK_EVIDENCE_RECONSTRUCTION.csv','existing alternative proof counts')
 taskcase=next(c for c in oldcases if c['metric']=='TaskSuccess');falsecase=next(c for c in oldcases if '真实Grant' in c['title']);hiaaq=next(r['query_id'] for r in registry if r['metric']=='HIAA_run' and r['phase']=='f' and r['native_unit_ref']=='c1-context-grid' and r['protocol']=='scheduled');unknownqs=[r['query_id'] for r in registry if r['metric']=='ALR' and r['native_unit_ref']=='unknown_reason-alr-original'];selected={taskcase['query_id'],falsecase['query_id'],hiaaq,*unknownqs,*[w[k] for w in witnesses for k in ['query_a','query_b']]};casepred={};base={};summary=[];impact=[];reference=[];errors=[];countchecks=[];fullbrief={}
 keyfields=['domain','study','phase','metric','protocol','horizon','source_variant','branch'];priorindex={tuple(r[k] for k in ['view_id']+keyfields):r for r in prior}
 for vid in FAMILIES:
  path=P4/f'results/{vid}.jsonl';psrc=src(path,'saved predictions read once for aggregation; not recomputed');agg=defaultdict(Counter);by_metric=defaultdict(Counter);trans=defaultdict(Counter);refs=defaultdict(Counter);seen=set()
  with path.open(encoding='utf-8-sig') as f:
   for line,text in enumerate(f,1):
    p=json.loads(text);qid=p['query_id'];r=reg[qid];assert qid not in seen;seen.add(qid);slot=slots.get(r['native_unit_ref'],{});key=(r['domain'],r['study'],r['phase'],r['metric'],r['protocol'],r['horizon'],slot.get('source_variant',''),slot.get('branch',''));bkey=(r['metric'],r['protocol'],r['horizon']);z=agg[key];z['fixed_queries']+=1;z[p['status']]+=1;z['eligible_'+('unknown' if p['eligibility'] is None else str(p['eligibility']).lower())]+=1;by_metric[bkey].update({k:v for k,v in [('fixed_queries',1),(p['status'],1),('eligible_'+('unknown' if p['eligibility'] is None else str(p['eligibility']).lower()),1)]})
    if vid=='V00':base[qid]=dict(status=p['status'],eligibility=p['eligibility'],value=p['value']);fullbrief[qid]=p if r['metric'] in ['HIAA_run','HIAA_pot_declared'] else None
    t=trans[bkey];t['full_point_n']+=base[qid]['status']=='point';t['view_point_n']+=p['status']=='point'
    if base[qid]['status']=='point':t['point_to_'+p['status']]+=1
    t['eligibility:'+str(base[qid]['eligibility'])+'->'+str(p['eligibility'])]+=1
    if qid in selected:casepred.setdefault(qid,{})[vid]=dict(prediction=p,source_ref=psrc+f'#L{line}',source_sha256=sources[psrc]['sha256'],registry=r,gold=gold.get(qid))
    if qid in gold:
     g=gold[qid];zz=refs[(g['domain'],r['metric'],r['protocol'])];zz['reference_queries']+=1;zz['truth_available']+=bool(g['truth_available']);zz['eligibility_known']+=bool(g['eligibility_known'])
     if g['truth_available'] and p['status']=='point':zz['determinate']+=1;zz['correct']+=p['value']==g['value'] and p['eligibility'] is True
  assert seen==set(reg)
  for key,z in agg.items():
   old=priorindex[(vid,*key)];bad={k:(z[k],old[k]) for k in ['fixed_queries','eligible_true','eligible_false','eligible_unknown']+STATES if z[k]!=old[k]}
   if bad:errors.append(dict(kind='saved_stratum_count_conflict',view=vid,key=key,counts=bad))
  for key,z in by_metric.items():
   metric,protocol,k=key;summary.append(dict(view_id=vid,masked_family=FAMILIES[vid],domain='ALL_DOMAINS_DESCRIPTIVE_QUERY_COUNTS',study='P4',raw_metric=metric,display_metric=display(metric),protocol=protocol,horizon=k,unit=units[metric],**{c:z[c] for c in ['fixed_queries','eligible_true','eligible_false','eligible_unknown']+STATES},boundary='Fixed heterogeneous query count; not risk rate or independent samples; eligible_unknown is already inside unknown',source_ref=psrc,source_sha256=sources[psrc]['sha256']))
   t=trans[key];relation='self' if metric in SELF.get(vid,set()) else 'control' if vid in ['V00','V11','V12'] else 'downstream';impact.append(dict(view_id=vid,masked_family=FAMILIES[vid],raw_metric=metric,display_metric=display(metric),protocol=protocol,horizon=k,relation=relation,full_point_n=t['full_point_n'],view_point_n=t['view_point_n'],point_loss=t['full_point_n']-t['view_point_n'],point_to_bounded=t['point_to_bounded'],point_to_unknown=t['point_to_unknown'],point_to_na=t['point_to_not_applicable'],eligibility_transition={k.split(':',1)[1]:v for k,v in t.items() if k.startswith('eligibility:')},query_denominator=z['fixed_queries'],mapping_basis='fixed named-family estimand map in code/common.py SELF; no standalone Receipt/Grant/reason estimator, those are downstream dependencies',source_ref=psrc))
  for key,z in refs.items():
   d,m,p=key;den=z['truth_available'];answered=z['determinate'];reference.append(dict(view_id=vid,domain=d,study='P4',raw_metric=m,display_metric=display(m),protocol=p,unit=units[m],reference_queries=z['reference_queries'],eligibility_known=z['eligibility_known'],determinate_applicable_truths=den,answered=answered,agrees=z['correct'],wrong_determinate=answered-z['correct'],judgment_coverage=answered/den if den else None,answered_agreement=z['correct']/answered if answered else None,source_ref=psrc+';'+goldsrc,source_sha256=sources[psrc]['sha256'],boundary='Finite controlled reference, correlated queries; no natural-language accuracy claim'))
  countchecks.append(dict(view=vid,unique_queries=len(seen),strata=len(agg),new_predictor_calls=0))
 # Existing reference score agreement, independent from its presentation rates.
 oldref={(r['view_id'],r['domain'],r['metric'],r['protocol']):r for r in savedscore}
 for r in reference:
  old=oldref[(r['view_id'],r['domain'],r['raw_metric'],r['protocol'])]
  for n,o in [('reference_queries','reference_queries'),('eligibility_known','eligibility_known'),('determinate_applicable_truths','truth_available'),('answered','determinate'),('agrees','correct')]:
   if r[n]!=int(old.get(o) or 0):errors.append(dict(kind='reference_count_conflict',view=r['view_id'],metric=r['raw_metric'],field=n,old=old.get(o),new=r[n]))
 # P3R table A is assembled from saved RESULTS only, never original events or a metric implementation.
 ml=rows(P3R/'METRICS_LONG.jsonl');mlsrc=src(P3R/'METRICS_LONG.jsonl','saved P3/P3R metric results');cells=csvread(P3R/'legacy/HIAA_CELLS.csv');cellsrc=src(P3R/'legacy/HIAA_CELLS.csv','saved P3 HIAA cells');contrast=csvread(P3R/'legacy/HIAA_CONTRASTS.csv');consrc=src(P3R/'legacy/HIAA_CONTRASTS.csv','saved bootstrap intervals');src(P3R/'P3R_METRIC_MAIN.md','existing narrative cross-check');src(P3R/'METRIC_CONTRACTS_P3R.md','historical contract definitions');mechanism=[];conflicts=[]
 def family(mid):
  if mid.startswith('hiaa'):return 'HIAA_pot_declared' if 'declared' in mid else 'HIAA_pot_observed' if 'potential' in mid else 'HIAA_run'
  if mid.lower().startswith('alr'):return 'ALR'
  if mid.lower().startswith('rir'):return 'RIR'
  if mid.startswith('uea'):return 'UEA'
  if mid.startswith('provenance'):return 'Provenance'
  if mid.startswith('ci'):return 'CI'
  return None
 for line,r in enumerate(ml,1):
  mid=r['metric_id'];fam=family(mid);layer=r.get('analysis_layer');ph=r.get('phase');domain=r.get('domain');pick=False
  if layer=='LEGACY_RECOMPUTED' and ph in ['f','g','h']:
   pick=mid in ['alr','rir_1','rir_3','uea_count','uea_type_count','provenance.f1','ci.mean','ci.positive','ci.zero','ci.negative'] or (mid.startswith('hiaa.') and len(mid.split('.'))==3)
  elif layer=='CORRECTED_OR_SENSITIVITY_ANALYSIS':pick=mid.startswith('rir_chain_') or mid=='ci_identity_stable_mean'
  elif layer in ['NEW_CONSTRUCT_VALIDATION','NEW_LIVE_SUPPLEMENT']:pick=fam is not None and domain!='SCRIPTED_T18'
  if not pick:continue
  contract=r.get('contract_version');unit=r.get('statistical_unit') or r.get('unit') or ('unique_request' if fam=='ALR' else 'prefix_session_cohort' if fam=='RIR' else 'saved metric unit');val=number(r.get('value'));n=number(r.get('numerator'));den=number(r.get('denominator'));lo=number(r.get('lower'));hi=number(r.get('upper'));status=r.get('status') or ('bounded' if val is None and lo is not None and hi is not None else 'not_applicable' if den==0 else 'unknown' if val is None else 'point');cc=None;design=r.get('case') or r.get('population_id') or mid;boot=r.get('confidence_interval');limit=r.get('limitations') or 'Preserve original contract and denominator; no new raw computation'
  if fam=='HIAA_run':
   design=mid.split('.')[1];policy=mid.split('.')[2];cc={c['cell']:{'numerator':number(c['numerator']),'denominator':number(c['denominator'])} for c in cells if c['phase']==ph and c['design']==design and c['policy']==policy};n=den=None;unit='matched four-cell run grid';boot=next(c['intervals'] for c in contrast if c['phase']==ph and c['design']==design and c['policy']==policy);design+=' / '+policy;limit+='; cells from '+cellsrc
  if fam=='HIAA_pot_observed':limit+='; observed unauthorized effect union only, not static capability';unit='declared sensitivity-weighted observed effect-type set'
  if fam=='ALR' and layer=='LEGACY_RECOMPUTED':limit+='; legacy derived reason point, not either explicit-reason strict contract'
  if fam=='RIR' and 'NEW_LIVE' in layer:limit+='; no-revoke control also zero; not revocation benefit; k1/k3 correlated'
  mechanism.append(dict(execution_domain=domain,analysis_layer=layer,study=r['study'],phase=ph,model_or_engine=r.get('model_config') or ('saved reference action-registry engine' if domain!='SCRIPTED_FINITE_DOMAIN' else 'declared finite model'),metric=fam,raw_metric=mid,display_metric=fam,contract=contract,design=design,unit=unit,numerator=n,denominator=den,value=val,lower=lo,upper=hi,unknown=number(r.get('unknown')),status=status,cells=cc,bootstrap_interval=boot,interval_kind=r.get('interval_kind'),source_ref=mlsrc+f'#L{line}',source_sha256=sources[mlsrc]['sha256'],original_evidence_refs=r.get('source_refs'),boundary=limit))
 # T18 grouped from the saved recovered-mechanism records, keeping mode and domain.
 t18=csvread(P3R/'T18_ALR_RIR_RECOVERED.csv');t18src=src(P3R/'T18_ALR_RIR_RECOVERED.csv','saved 95 recovered construct rows');tgroups=defaultdict(list)
 for i,r in enumerate(t18,2):tgroups[(r['domain'],r['mode'],r['metric'],r['k'])].append((i,r))
 for (dom,mode,mid,k),rr in tgroups.items():
  elig=[r for i,r in rr if r['eligible']=='True'];n=sum(r['numerator']=='True' for r in elig);u=sum(r['numerator'] not in ['True','False'] for r in elig);den=len(elig);mechanism.append(dict(execution_domain='T18_'+dom,analysis_layer='EXISTING_T18_CONSTRUCT',study='T18',phase=mode,model_or_engine=dom,metric=family(mid),raw_metric=mid,display_metric=family(mid),contract='T18_original_contract',design=mode+'/k'+k,unit='unique authorization request' if 'ALR' in mid else 'saved eligible chain at k',numerator=n,denominator=den,value=n/den if den and not u else None,lower=n/den if den else None,upper=(n+u)/den if den else None,unknown=u,status='not_applicable' if not den else 'unknown' if u else 'point',cells=None,bootstrap_interval=None,interval_kind='identification range not sampling CI',source_ref=t18src+'#rows='+','.join(str(i) for i,r in rr),source_sha256=sources[t18src]['sha256'],boundary='Separate scripted/fake reference and mode; not live attack evidence'))
 # Strict ALR and confirmed-prefix clauses retain saved P4 Full results as a distinct recovered layer.
 for i,r in enumerate(prior,1):
  if r['view_id']!='V00':continue
  if not ((r['domain']=='HISTORICAL_LIVE' and r['metric']=='ALR') or (r['metric']=='RIR' and r['protocol']=='confirmed_prefix_v1' and r['domain'] in ['HISTORICAL_LIVE','SAVED_LIVE'])):continue
  fam=r['metric'];den=r['eligible_true'];lo=r['rate_lower'];hi=r['rate_upper'];mechanism.append(dict(execution_domain=r['domain'],analysis_layer='P4_SAVED_CONTRACT_RECOVERY',study=r['study'],phase=r['phase'],model_or_engine='historical Luna F/H; DeepSeek G' if r['domain']=='HISTORICAL_LIVE' else 'saved Luna reference',metric=fam,raw_metric=fam,display_metric=fam,contract=r['protocol'],design=r['source_variant']+'/k'+str(r['horizon']) if fam=='RIR' else r['phase'],unit=units[fam],numerator=r['positive'],denominator=den,value=lo if lo is not None and lo==hi else None,lower=lo,upper=hi,unknown=r['unknown_in_eligible'],eligible_unknown=r['eligible_unknown'],status='eligibility_unknown' if r['eligible_unknown'] else 'not_applicable' if den==0 else 'bounded' if lo!=hi else 'point',cells=None,bootstrap_interval=None,interval_kind='identification range not sampling CI',source_ref=priorsrc+f'#L{i}',source_sha256=sources[priorsrc]['sha256'],boundary='No reinterpretation of stronger conjunction as lower risk; no qualified confirmed-prefix denominator'))
 # Detect saved HIAA denominator mismatch without resolving/recomputing it.
 for qid,p in fullbrief.items():
  if p is None or p['metric']!='HIAA_run':continue
  r=reg[qid];old={c['cell']:number(c['denominator']) for c in cells if c['phase']==r['phase'] and c['design']==r['native_unit_ref'] and c['policy']==r['protocol']};new={k:v['denominator'] for k,v in p['details']['cells'].items()}
  if old!=new:conflicts.append(dict(kind='HIAA_VALID_ONLY_DENOMINATOR',phase=r['phase'],design=r['native_unit_ref'],protocol=r['protocol'],P3R_denominators=old,P4_denominators=new,P3R_source=cellsrc,P4_source='论文材料/P4_测量证据消融/p4-20260917-123623/HIAA_CELLS.csv',query_id=qid,impact='same point value does not make denominators interchangeable; Table A retains P3R and Table B retains P4',resolution='documented, no predictor or source change; exact qualification difference not repaired in closeout'))
 src(P4/'HIAA_CELLS.csv','P4 saved cells for version discrepancy')
 summary.sort(key=lambda r:(ORDER[r['raw_metric']],r['protocol'],str(r['horizon']),r['view_id']));mechanism.sort(key=lambda r:(ORDER.get(r['metric'],99),r['analysis_layer'],r['execution_domain'],str(r['phase']),r['design']));reference.sort(key=lambda r:(ORDER[r['raw_metric']],r['protocol'],r['domain'],r['view_id']))
 source_decomp=Counter()
 for r in impact:
  if r['view_id']=='V03':source_decomp[r['raw_metric']]+=r['point_loss']
 strict=[r for r in prior if r['view_id']=='V00' and r['domain']=='HISTORICAL_LIVE' and r['metric']=='ALR'];totref=[]
 for vid in FAMILIES:
  rr=[r for r in reference if r['view_id']==vid];z={k:sum(r[k] for r in rr) for k in ['reference_queries','eligibility_known','determinate_applicable_truths','answered','agrees','wrong_determinate']};z.update(view_id=vid,judgment_coverage=z['answered']/z['determinate_applicable_truths'],answered_agreement=z['agrees']/z['answered'] if z['answered'] else None);totref.append(z)
 data=dict(schema='P4_closeout_editorial_data_v1',table_A=mechanism,table_B=summary,table_B_full_strata=[dict(r,raw_metric=r['metric'],display_metric=display(r['metric']),source_ref=priorsrc+f'#L{i}') for i,r in enumerate(prior,1)],self_vs_downstream=impact,table_C=reference,table_C_overall=totref,source_decomposition=dict(source_decomp),strict_ALR=strict,cases={'witnesses':witnesses,'witness_source':wsrc,'old_case_source':csrc,'task':taskcase,'short_circuit':falsecase,'hiaa_query':hiaaq,'unknown_reason_queries':unknownqs,'selected_predictions':casepred},existing_task_reconstruction=rebuild,existing_P4_status=meta,conflicts=conflicts,source_count=len(sources),mapping_SELF={k:sorted(v) for k,v in SELF.items()})
 dump('data/closeout_data.json',data);dump('SOURCE_MANIFEST.json',{'sources':list(sources.values()),'archive_binding':'checks/INPUT_BINDING.json','scope':'files actually used for closeout; no new original-fact metric recomputation'});dump('checks/SAVED_REAGGREGATION.json',{'passes':1,'parsed_saved_predictions':252096,'new_predictions':0,'new_gold_labels':0,'per_view':countchecks,'stratum_and_reference_conflicts':errors,'source_point_loss':dict(source_decomp),'source_total':sum(source_decomp.values()),'HIAA_version_conflicts':conflicts});assert not errors
 print(can({'table_A_rows':len(mechanism),'table_B_rows':len(summary),'full_strata':len(prior),'reference_rows':len(reference),'source_loss':dict(source_decomp),'denominator_conflicts':len(conflicts),'source_files':len(sources)}))
if __name__=='__main__':main()
