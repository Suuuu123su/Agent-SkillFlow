from common import *
from capability_model import *
import copy
offline_guard()
base={'closed':True,'atoms':['source_A','source_B','consumed_A','purpose_send','grant_send','enabled'],'initial':['source_A','purpose_send','enabled'],'universe':{'local.mock.send:A:archive':2},'rules':[{'id':'bridge_read_A','requires':['source_A'],'execution_requires':['enabled'],'adds':['consumed_A'],'bridge':True},{'id':'send_A','requires':['consumed_A','purpose_send'],'execution_requires':['enabled'],'adds':[],'effect':'local.mock.send:A:archive','manifest_declared':True,'grant_atom':'grant_send'}],'effect_key':'action:source:purpose/sink','weights':'nonnegative declared sensitivity','observed_executed_effects':[]}
cases={}
cases['unexecuted_but_reachable']=copy.deepcopy(base)
z=copy.deepcopy(base);z['initial'].append('consumed_A');cases['same_sets_true_zero']=z
z=copy.deepcopy(base);z['initial'].remove('purpose_send');cases['and_missing']=z
z=copy.deepcopy(base);z['initial'].remove('source_A');z['initial'].append('source_B');cases['same_tool_wrong_source']=z
z=copy.deepcopy(base);z['irrelevant_metadata']='changed';cases['metadata_invariant']=z
z=copy.deepcopy(base);z['unknown_semantics']=['policy semantics absent'];cases['unknown_not_zero']=z
z=copy.deepcopy(base);z['initial'].append('grant_send');cases['authorized_excluded_from_U']=z
out={};checks=[]
for name,m in cases.items():
 result=potential(m);out[name]={'model':m,'result':result}
 for b in [False,True]:
  independent=independent_bit_enumeration(m,b);actual=result['h1' if b else 'h0'];checks.append({'case':name,'bridge':b,'match':independent is None or independent==actual['lower'],'independent':independent,'solver':actual['lower']})
assert out['unexecuted_but_reachable']['result']['lower']==2
assert out['same_sets_true_zero']['result']['lower']==out['and_missing']['result']['lower']==out['same_tool_wrong_source']['result']['lower']==out['authorized_excluded_from_U']['result']['lower']==0
assert out['metadata_invariant']['result']==out['unexecuted_but_reachable']['result']
assert not out['unknown_not_zero']['result']['exact']
assert all(x['match'] for x in checks)
dump('POT_SETS_AND_WITNESSES.json',out);dump('audit/POT_INDEPENDENT_ENUMERATION.json',checks)
(OUT/'CAPABILITY_MODEL_CONTRACT.md').write_text('''# HIAA_pot_declared_v1

U_h 是声明有限状态机内 **未获 manifest+Grant 双重授权但原生执行规则允许产生** 的Effect类型集合，按非负敏感权重去重。注册工具本身不是U；合法已授权Effect不进入U。输入不使用运行后Effect或模型结果。

状态由有限布尔原子构成；每条规则必须同时满足数据、用途、原生执行前提；缺任一AND条件不能执行。规则闭包枚举全部可达状态直到不动点，无任意Python、自然语言或隐含参数域。工具注册一致不意味着来源/用途可达相同。只有指定bridge规则启停，其他初态、规则和权重逐字一致。

每个U成员有规则ID见证路径；独立核对器对全部2^6状态显式构图并传播可达性。精确性仅限此闭合声明模型。未知语义输出 L为空、U为声明类型全集；使用 W(L1\\U0) 与 W(U1\\L0) 的合法上下界，不拿两个上界相减。

本次实际7构念：未执行却可达的静态增量2；同集合真零0；AND不足0；同工具错误来源0；无关元数据不变2；缺政策语义[0,2]未知；真实Grant合法效果排除后0。14个bridge状态与独立枚举一致。

历史T17公开配置保存动作候选、原生工具和观测Effect，但没有对任意Actor输出参数/语言策略作穷尽声明。因此旧观测pot=0保持；新增历史静态值仍未识别。上述2与0不得填入F/G/H历史主表。可运行源码与冻结构念模型均包含在包内。
''',encoding='utf-8')
print('POT 7 cases, 14 independent checks passed')
