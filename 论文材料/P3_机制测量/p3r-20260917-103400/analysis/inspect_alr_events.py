from common import *
from collections import Counter
for p in (OUT/'live/units').glob('ALR*/state.json'):
 s=read(p);u=p.parent.name;own=[e for e in s['events'] if e['unit']==u];print(u,dict(Counter(e['action'] for e in own if e['kind']=='effect')),[(e['action'],e['reason']) for e in own if e['kind']=='decision'])
