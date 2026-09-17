from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P4_测量证据消融\p4-20260917-123623\code\ingest.py');s=p.read_text(encoding='utf-8-sig');s=s.replace("oblig.append(dict(kind='effect_contract',spec=x))", "oblig.append(dict(kind='effect_contract',spec={'selector':{k:v for k,v in x['selector'].items() if k!='alias'},'required_session':opaque(x['session_id'])}))")
s=s.replace("'task_contract_present':True,'risk_selectors'", "'task_contract_present':state['scenario']['module']=='RIR','risk_selectors'")
s=s.replace("[opaque(v) for v in a['observed_label']['parent_artifact_ids']]", "list(dict.fromkeys([opaque(v) for v in a['observed_label']['parent_artifact_ids']]+[opaque(v) for v in ev[a['created_by_event_id']]['input_artifact_ids']]))")
p.write_text(s,encoding='utf-8')
p=p.parent/'predictor.py';s=p.read_text(encoding='utf-8-sig');s=s.replace("return len(set(p['state_hashes']))==1", "return None if p.get('source_object') is None else len(set(p['state_hashes']))==1")
p.write_text(s,encoding='utf-8')
