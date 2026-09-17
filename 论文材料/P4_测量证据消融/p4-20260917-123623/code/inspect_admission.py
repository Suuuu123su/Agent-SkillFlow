from common import *
xs=rows(OUT/'control/REFERENCE_INPUTS.jsonl')
for k in ['reference','finite_model']:
 x=next(x for x in xs if x['kind']==k);print(k,canonical(x)[:23000])
x=next(x for x in xs if x['kind']=='legacy');print('oracle',canonical(x['data']['oracle'])[:4000]);print('certificate',next((d['task_success_evidence'] for d in rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl') if d.get('task_success_evidence')),None))
reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')}
for x in rows(OUT/'checks/admission-V00-r0.jsonl'):
 r=reg[x['query_id']]
 if r['domain'] in ['FINITE_CONSTRUCT','CONTROLLED_CONSTRUCT'] and r['metric'] in ['RIR','ALR','HIAA_pot_declared'] and ('original' in r['native_unit_ref'] or r['metric']=='HIAA_pot_declared'):print('prediction',canonical({'r':r,'p':x})[:2500])
