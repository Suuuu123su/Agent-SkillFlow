from common import *
from collections import Counter
offline_guard()
loc=list(csv.DictReader((PACK/'locators/LEGACY_M2_90.csv').open(encoding='utf-8-sig')))
G=ROOT/'runs/t17-v2-deepseek-20260904-01/model2/attempt-02/segment';usage=rows(G/'api-usage.jsonl')
attempts={x['unit_id']:x for x in usage if x['event_type']=='attempt' and (x.get('call') or {}).get('step_id')=='m2-a-read'}
cores={r['identity']['unit_id']:(r,ref) for r,ref in table('g','core-trials')};out=[];safe=[]
for item in loc:
 if item['phase']!='g':continue
 r,ref=cores[item['unit_id']];a=attempts[item['unit_id']];p=G/'api-private'/f"{a['attempt_index']:06}.json";v=read(p);req,res=v['request'],v['response'];vis=[x for x in res.get('output',[]) if x.get('type')!='reasoning'];reason=(res.get('incomplete_details') or {}).get('reason');u=res.get('usage',{});input_prompt=json.loads(req['input'][-1]['content'][0]['text'])
 cause='output_cap_before_visible_decision' if res['status']=='incomplete' and reason=='max_output_tokens' and not vis else 'valid_no_call_task_scope_mismatch' if res['status']=='completed' and vis else 'needs_individual_inspection'
 out.append(dict(phase='g',unit_id=item['unit_id'],run_id=r['run_id'],request_id=a['call']['call_id'],response_id=res['id'],attempt_index=a['attempt_index'],first_failure_step='m2-a-read',cause=cause,status=res['status'],incomplete_reason=reason,visible_output_items=len(vis),required_fields=req['text']['format']['schema']['required'],actual_visible_fields=['selected_action_ids','output_text'] if vis else [],host_source_expected_from='Actor chooses read-memory-source; host executes file.read and binds its output alias',allowed_action_ids=input_prompt['allowed_action_ids'],input_artifacts_count=len(input_prompt['input_artifacts']),request_max_output_tokens=req.get('max_output_tokens'),total_output_tokens=u.get('output_tokens'),reasoning_tokens=u.get('output_tokens_details',{}).get('reasoning_tokens'),source_file=p.relative_to(ROOT).as_posix(),source_sha256=sha(p),core_ref=ref,m2_source_present='m2-source' in r['data']['artifact_ids_by_alias'],memory_writes=sum(e['effect']['action']=='memory.write' and e['executed'] for e in r['data']['facts']['effects']),mechanical_adapter_can_recover_saved_output=False))
 safe.append(dict(unit_id=item['unit_id'],request=req,response={k:res.get(k) for k in ['id','status','incomplete_details','max_output_tokens','model','usage','text']},visible_output=vis,omitted_reasoning=True,source_sha256=sha(p)))
csvout('M2_FIRST_FAILURES.csv',out);jl('evidence/M2_SAFE_REQUEST_RESPONSE.jsonl',safe)
summary=dict(total=len(out),causes=dict(Counter(x['cause'] for x in out)),memory_writes=sum(x['memory_writes'] for x in out),sources_present=sum(x['m2_source_present'] for x in out));dump('audit/M2_DIAGNOSIS_COUNTS.json',summary);print(summary)
# Locate actual F successful prefix and retain public visible request/response without reasoning.
fcore=next(r for r,ref in table('f','core-trials') if r['identity']['unit_id']==loc[0]['unit_id'])
m=read(ROOT/'datasets/t17-v2/stages/f/dataset-manifest.json');raw=ROOT/m['stages'][0]['raw_relative_path'];print('F raw',raw)
print('F actions',fcore['decisions'][:2]);print('F raw exists',raw.exists())
dump('evidence/F_M2_SUCCESS_CORE.json',fcore)
(OUT/'M2_DIAGNOSIS.md').write_text('# DS M2 原始失败诊断\n\n全部30条的首次阻断均发生在 m2-a-read。原请求的结构化输出合同要求 selected_action_ids 和 output_text；tools 数组为空，因为旧协议是动作ID选择器而非原生工具参数调用。29条原响应明确保存 incomplete_details.reason=max_output_tokens，且没有可见决策输出。另1条 s04-r1 目标样本返回合法空选择，明确说明当前动作列表不含整个任务的撤销与后续会话读取；这是局部步骤与全局任务的解释不一致，不是截断。不是根据缺Memory猜测截断。\n\n源文件存在于宿主workspace；m2-source应由模型选择read-memory-source后，真实file.read工具产出并绑定。空决策导致该工具未执行，随后m2-a-write因missing_input被跳过。不能把下游missing_input误记为最早根因。29条没有可机械修复的JSON；另1条合法空选择也不能强改为调用，故不能离线补写历史Memory。F正例的真实读/写动作单独封存。\n\n新入口改用真实工具调用循环、明确读写参数与可见工具结果，继承最近成功Luna传输，不套用旧DS 2048输出设置。旧G的30/30 Memory未形成与RIR空分母继续保留；没有重发任何旧请求。\n',encoding='utf-8')

