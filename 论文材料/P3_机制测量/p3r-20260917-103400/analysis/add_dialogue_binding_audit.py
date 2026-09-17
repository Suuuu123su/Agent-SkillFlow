from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400\analysis\lifecycle_accounting.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("source_checkpoint=f'live/units/{parent}/checkpoint.json',status=ledger", "source_checkpoint=f'live/units/{parent}/checkpoint.json',prefix_dialogue_unchanged=rows(p/'model_turns.jsonl')[0]['input']['input'][:len(read(L/'units'/parent/'messages.json'))]==read(L/'units'/parent/'messages.json'),status=ledger")
s=s.replace("if not x['prefix_events_identical'] or not x['grants_unchanged']", "if not x['prefix_events_identical'] or not x['grants_unchanged'] or not x['prefix_dialogue_unchanged']")
s=s.replace("[('f',360,270),('g',360,270),('h',270,270)]", "[('f',360,270),('g',360,270),('h',270,270)]")
s=s.replace("coverage += [dict(domain='T17_DERIVED_COMPARISON'", "coverage += [dict(domain='T17_CANARY',phase='e',core=24,replay=18,use='separate preflight, excluded formal main'),dict(domain='T17_CANARY',phase='g_canary',core=24,replay=18,use='separate preflight, excluded formal main'),dict(domain='T17_DERIVED_COMPARISON'")
p.write_text(s,encoding='utf-8')
