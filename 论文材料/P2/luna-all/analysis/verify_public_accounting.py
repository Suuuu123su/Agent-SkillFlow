"""Standalone standard-library verifier for the exported accounting directory."""
import sys,json,collections
from pathlib import Path
def main(path):
 p=Path(path);rows=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
 assert [x['id'] for x in rows]==list(range(1,len(rows)+1))
 assert len(rows)<=4096
 assert all(x['model']=='gpt-5.6-luna' for x in rows)
 assert all(x['endpoint']=='https://chatgpt.com/backend-api/codex/responses' for x in rows)
 r2=[x for x in rows if x['protocol_revision']=='r2_host_tools_removed']
 assert all(x['top_level_tool_count']==0 and x['nested_tool_count']==0 and x['tool_choice']=='none' for x in r2)
 assert all(x['role'] in {'actor','semantic','content','derived','judge'} for x in rows)
 counts=collections.Counter((x['unit'],x['role']) for x in rows)
 assert all(sum(v for (u,role),v in counts.items() if u==unit and role in {'semantic','content','derived'})<=108 for unit in {x['unit'] for x in rows})
 assert sum(x['role']=='judge' for x in rows)<=47
 assert all(v<=20 for (u,role),v in counts.items() if role=='actor')
 assert all(sum(v for (u,role),v in counts.items() if u==unit and role!='judge')<=128 for unit in {x['unit'] for x in rows})
 print(json.dumps({'budget_counted_attempts':len(rows),'known_local_pre_forward_failures':sum(x.get('known_not_forwarded',False) for x in rows),'external_dispatch_attempts':sum(not x.get('known_not_forwarded',False) for x in rows),'unknown':sum(x['unknown_delivery'] is True for x in rows),'missing_usage':sum(not x['usage'] for x in rows),'tokens_observed':sum((x['usage'] or {}).get('total_tokens',0) for x in rows),'by_role':dict(collections.Counter(x['role'] for x in rows)),'scope':'Accounting only; does not prove semantic safety, completion, or raw projection fidelity.'},indent=2))
if __name__=='__main__':main(sys.argv[1])
