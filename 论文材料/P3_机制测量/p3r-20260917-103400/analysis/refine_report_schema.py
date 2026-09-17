from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400\analysis\build_final_report.py')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("value=json.dumps(result,ensure_ascii=False)","value=result['lower']")
s=s.replace("extra={'case':name})","extra={'case':name,'upper':result['upper'],'exact':result['exact'],'difference_lower':result['difference_lower'],'difference_upper':result['difference_upper']})")
s=s.replace("csvout('METRICS_LONG.csv',long);jl('METRICS_LONG.jsonl',long)","""for case in read(OUT/'construct/CONSTRUCT_RESULTS.json'):
 for x in case['outcomes']:
  if case['module']=='RIR':
   eligible=x['eligible'];num=int(x['status']=='confirmed');add('rir_construct_k'+str(x['k']),'SCRIPTED_NEW','RIR_chain_v1',num,int(eligible),unknown=int(x['status']=='uncertain_attribution'),source='construct/CONSTRUCT_RESULTS.json',limits='Deterministic state-machine execution, not natural model attack',extra={'case':case['case'],'status':x['status']})
  else:add('alr_construct','SCRIPTED_NEW','frozen_replica_guard_strict',int(x['strict'] is True),int(x['exposed']),unknown=int(x['strict'] is None),source='construct/CONSTRUCT_RESULTS.json',limits='Explicit unknown-reason observation ablation where named',extra={'case':case['case'],'seven_conditions':x['conditions']})
csvout('METRICS_LONG.csv',long);jl('METRICS_LONG.jsonl',long)""")
p.write_text(s,encoding='utf-8')
