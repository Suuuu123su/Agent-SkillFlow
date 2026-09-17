"""Targeted correction only: UEA unit weights, retain first-check evidence."""
import json,pathlib,hashlib,csv,datetime
p=pathlib.Path(__file__).resolve().parents[1]
def dump(n,x):(p/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
check=json.loads((p/'RECOMPUTE_CHECK.json').read_text('utf-8'));dump('audit/RECOMPUTE_CHECK_FIRST_PASS.json',check)
s=p/'analysis/independent.py'; original=s.read_bytes();(p/'audit/independent-first-pass.py.txt').write_bytes(original)
text=original.decode('utf-8-sig').replace("sum(e['weight'] for e in es if e['uea'])","sum(1 for e in es if e['uea'])")
s.write_text(text,encoding='utf-8')
effects=[json.loads(x) for x in (p/'facts/EFFECTS.jsonl').open(encoding='utf-8')];ind=json.loads((p/'facts/INDEPENDENT_METRICS.json').read_text('utf-8'))
fixes=[]
for row in check['checks']:
 if row.get('metric_id')!='uea_weight':continue
 phase=row['phase'];ss=[e for e in effects if (e['phase'] in ['f','h'] and e['mode']==phase[3:]) if phase.startswith('fh_')] if phase.startswith('fh_') else [e for e in effects if e['phase']==phase]
 n=sum(e['uea'] for e in ss);before=row['calculated'];row.update(calculated=float(n),numerator=n,match=n==row['fresh_original_algorithm']);ind[phase]['uea_weight']={'numerator':n,'denominator':1,'value':float(n)}
 fixes.append({'phase':phase,'first_independent_value':before,'corrected_unit_weight':n,'sensitivity_sum_separate_diagnostic':sum(e['weight'] for e in ss if e['uea']),'reason':'original calculate_uea uses weight=1 per operation; sensitivity belongs to HIAA_pot not UEA'})
check.update(passed=sum(c['match'] for c in check['checks']),failed=sum(not c['match'] for c in check['checks']),targeted_revision=fixes)
dump('RECOMPUTE_CHECK.json',check);dump('facts/INDEPENDENT_METRICS.json',ind);dump('audit/TARGETED_WEIGHT_CORRECTION.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'changes':fixes,'scope':'only seven UEA-weight aggregate cells; all other checks unchanged','source_contract':'src/skillflow/analysis/effective_authority.py:89'})
print(check['passed'],check['failed'])
