from common import *
from collections import Counter
r=rows(OUT/'live/raw/results.jsonl');print('actual_response_models',dict(Counter((x.get('response') or {}).get('model') for x in r)));print('response_statuses',dict(Counter((x.get('response') or {}).get('status') for x in r)))
l=read(OUT/'live/ledger.json');print('requests',l['requests']);print('active',[(k,v['status']) for k,v in l['units'].items() if v['status']=='running'])
