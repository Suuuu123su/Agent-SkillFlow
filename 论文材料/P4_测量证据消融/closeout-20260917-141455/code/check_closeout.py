from common import *
import csv,re
from collections import defaultdict

def main():
 guard();d=read(OUT/'data/closeout_data.json');checks=[]
 def ok(name,condition,detail):
  assert condition,(name,detail)
  checks.append(dict(check=name,status='PASS',detail=detail))
 def rc(p):
  with (OUT/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
 for label,key,file in [('A','table_A','mechanism_results'),('B','table_B','metric_ablation'),('C','table_C','independent_reference')]:
  actual=rc('tables/'+file+'.csv');expected=d[key];ok('CSV_'+label,len(actual)==len(expected),len(actual))
  for i,(a,e) in enumerate(zip(actual,expected),1):
   assert a['row_id']==f'{label}{i:03}'
   for k,v in e.items():
    if v is None:assert a[k]==''
    elif isinstance(v,(dict,list)):assert json.loads(a[k])==v
    else:assert a[k]==str(v),(label,i,k,a[k],v)
  md=(OUT/f'tables/table_{label}.md').read_text(encoding='utf-8');tex=(OUT/f'tables/table_{label}.tex').read_text(encoding='utf-8')
  mr=[x for x in md.splitlines() if re.match(r'\| '+label+r'\d{3} \|',x)];tr=[x for x in tex.splitlines() if re.match(label+r'\d{3} &',x)]
  assert len(mr)==len(tr)==len(expected)
  # Independent format parsing; compare all printed cells after minimal LaTeX unescaping.
  for m,t in zip(mr,tr):
   mc=[x.strip() for x in m.strip('|').split('|')];tc=[x.strip() for x in t[:-3].split(' & ')]
   tc=[re.sub(r'\\([_&#%${}])',r'\1',x) for x in tc]
   assert mc==tc,(label,mc,tc)
  ok('MD_LATEX_'+label,True,{'rows':len(mr),'numeric_and_text_cells_equal':True})
 groups=defaultdict(list)
 for r in d['table_B']:
  assert r['fixed_queries']==sum(r[x] for x in ['point','bounded','unknown','not_applicable','conflict','analysis_error'])
  assert r['eligible_unknown']<=r['unknown']
  groups[(r['raw_metric'],r['protocol'],r['horizon'])].append(r)
 assert all(len(rs)==13 and len({r['fixed_queries'] for r in rs})==1 for rs in groups.values())
 assert all(sum(r['fixed_queries'] for r in d['table_B'] if r['view_id']==v)==19392 for v in FAMILIES)
 ok('fixed_denominators_and_status_partition',True,{'groups':len(groups),'views':13,'queries_per_view':19392,'eligibility_unknown_subset':True})
 for v in FAMILIES:
  rr=[r for r in d['table_C'] if r['view_id']==v];ov=next(r for r in d['table_C_overall'] if r['view_id']==v)
  for k in ['reference_queries','eligibility_known','determinate_applicable_truths','answered','agrees','wrong_determinate']:assert sum(r[k] for r in rr)==ov[k]
  assert (ov['reference_queries'],ov['eligibility_known'],ov['determinate_applicable_truths'])==(314,308,192)
  assert ov['judgment_coverage']==ov['answered']/192
  assert ov['answered_agreement']==(ov['agrees']/ov['answered'] if ov['answered'] else None)
 full=next(r for r in d['table_C_overall'] if r['view_id']=='V00');ok('reference_coverage',full['answered']==full['agrees']==190,full)
 sd=d['source_decomposition'];ok('source_decomposition',sum(sd.values())==8166 and [sd[x] for x in ['Provenance','ALR','CI','RIR']]==[7472,87,593,14],sd)
 for phase,vals in [('f',[(0,9,15),(0,10,14)]),('g',[(0,5,10),(0,9,6)])]:
  for protocol,expected in zip(['T11_explicit_reason','P3R_identity_guard'],vals):
   r=next(r for r in d['strict_ALR'] if r['phase']==phase and r['protocol']==protocol);assert tuple(r[x] for x in ['positive','negative','unknown_in_eligible'])==expected
 ok('ALR_contract_separation',True,'F 0/9/15 vs 0/10/14; G 0/5/10 vs 0/9/6')
 aliases=rc('METRIC_NAME_MAP.csv');es=[r for r in aliases if r['study']=='P4' and r['raw_metric']=='E_STS'];assert len(es)==1 and es[0]['display_metric']=='STS_target_contract' and es[0]['protocol']=='U_and_not_verified_contract_violation'
 ok('display_alias_only',True,'native P4 fields retained; P0 native protocol explicitly not imported')
 cards=read(OUT/'data/paper_cases.json');assert [c['card'] for c in cards]==['W1','W2','R1','S1','I1','U1']
 for c in cards:
  assert c['queries'] and c['objects'] and c['independent_reference']
  for p in c['before']+c['after']:assert p['source_ref'] and len(p['source_sha256'])==64
 i=cards[4];assert i['before'][0]['prediction']['value']==1 and (i['after'][0]['prediction']['lower'],i['after'][0]['prediction']['upper'])==(-1,1)
 assert all(x['prediction']['status']=='unknown' for x in cards[5]['before'])
 ok('six_existing_cards',True,'6 cards, actual query IDs, source/hash, reference coverage boundaries')
 assert len(d['conflicts'])==2 and all(set(x['P3R_denominators'].values())=={13} and set(x['P4_denominators'].values())=={15} for x in d['conflicts'])
 ok('version_conflicts_retained',True,'F/H valid-only 13 vs 15, not repaired')
 sm=read(OUT/'SOURCE_MANIFEST.json')['sources']
 for s in sm:assert sha(Path(s['absolute_path']))==s['sha256'],s['path']
 ok('used_source_hashes',True,len(sm))
 old=read(OUT/'checks/SAVED_REAGGREGATION.json');assert old['passes']==1 and old['new_predictions']==0 and old['parsed_saved_predictions']==252096
 ok('saved_reaggregation_scope',True,'exactly one prior saved-result pass; this checker does not read prediction JSONL')
 assert b'\r' not in (OUT/'REPRODUCE.md').read_bytes().replace(b'\r\n',b'\n')
 ok('reproduction_command',True,'literal PowerShell path without escaped carriage return')
 dump('checks/CLOSEOUT_CHECKS.json',{'status':'PASS','checks':checks,'new_prediction_calls':0,'new_portable_64x13_checks':0,'new_model_calls':0,'latex_compiled':False,'scope':'document/count/alias/source-byte checks; no semantic human review'})
 print(can({'status':'PASS','checks':len(checks),'source_hashes':len(sm)}))
if __name__=='__main__':main()


