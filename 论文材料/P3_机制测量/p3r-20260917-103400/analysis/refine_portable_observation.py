from pathlib import Path
base=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400')
p=base/'analysis/portable_verify_template.py';s=p.read_text(encoding='utf-8-sig')
s=s.replace(" s=states[example['original']];i=states[example['identity']];n=states[example['neutral']];requests=", " s=states[example['original']]\n if example.get('measurement_view'):\n  observed=read(example['measurement_view'])['state'];expected=json.loads(json.dumps(s))\n  for e in expected['events']:\n   if e['kind']=='decision' and e['action']=='network.send':e.pop('reason',None)\n  check('measurement_view_only_reason_withheld',observed==expected);s=observed\n i=states[example['identity']];n=states[example['neutral']];requests=")
s=s.replace("reason=None if example['case']=='unknown_reason' else d.get('reason')","reason=d.get('reason')")
s=s.replace("check('pot_unknown:'+name,not res['exact'] and res['lower']==0 and res['upper']==sum(m['universe'].values()));continue", "lower=0;upper=sum(m['universe'].values());check('pot_unknown:'+name,not res['exact'] and res['lower']==lower and res['upper']==upper);values.append({'metric':'pot','case':name,'value':None,'lower':lower,'upper':upper,'status':'UNKNOWN_DECLARATION'});continue")
p.write_text(s,encoding='utf-8')
p=base/'analysis/build_slice.py';s=p.read_text(encoding='utf-8-sig');s=s.replace("shutil.copyfile(OUT/'POT_SETS_AND_WITNESSES.json',S/'pot.json')", "(S/'observations').mkdir(exist_ok=True)\nshutil.copyfile(OUT/'construct/unknown_reason_observation.json',S/'observations/missing_reason.json')\nfor item in index['alr']:\n if item['case']=='unknown_reason':item['measurement_view']='observations/missing_reason.json'\nshutil.copyfile(OUT/'POT_SETS_AND_WITNESSES.json',S/'pot.json')")
p.write_text(s,encoding='utf-8')
