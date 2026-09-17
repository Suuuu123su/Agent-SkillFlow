from common import *
x=rows(OUT/'control/REFERENCE_INPUTS.jsonl')[0];print('oracle',canonical(x['data']['oracle'])[:4500])
reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')}
for x in rows(OUT/'checks/admission-V00-r0.jsonl'):
 r=reg[x['query_id']]
 if r['domain']=='CONTROLLED_CONSTRUCT' and r['metric']=='RIR':print(r['native_unit_ref'],r['protocol'],r['horizon'],x['eligibility'],x['status'],x['value'],x['details'])
print('finite_models',canonical([x for x in rows(OUT/'control/REFERENCE_INPUTS.jsonl') if x['kind']=='finite_model'])[:7000])
print('cert_count',sum(bool(d.get('task_success_evidence')) for d in rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl')))
