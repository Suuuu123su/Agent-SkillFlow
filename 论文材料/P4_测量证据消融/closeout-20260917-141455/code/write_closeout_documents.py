from common import *
from render_tables import md,fmt

def main():
 guard();d=read(OUT/'data/closeout_data.json');total=sum(d['source_decomposition'].values());selfn=d['source_decomposition']['Provenance'];down=total-selfn;ref=d['table_C_overall'];strict=d['strict_ALR'];binding=read(OUT/'checks/INPUT_BINDING.json');p3zip=P3R/'p3r-completion-review.zip';external=PACK/'references/P4_EXTERNAL_REVIEW.md'
 amendments=['# P4解释修订（原字段和结果不变）','', '## 1. 来源自身依赖与跨指标影响分开','',md(['raw_metric','点值损失','关系'],[[m,n,'self' if m=='Provenance' else 'downstream'] for m,n in d['source_decomposition'].items() if n]),'',f'核对式：{total} = {selfn} + 87 + 593 + 14；自身占比{selfn}/{total}={selfn/total:.2%}，下游共{down}条。ALR的87按查询合同计数，并非87个独立请求；CI的593和RIR的14也不能与来源成员当同单位比较。不得用总损失排序“证据最重要”。完整分母/转移见[tables/self_vs_downstream.csv](tables/self_vs_downstream.csv)。','', '## 2. ALR严格合同与旧推导reason分开','',md(['阶段','原protocol','N','真','假','未知','缺证识别界'],[[r['phase'],r['protocol'],r['eligible_true'],r['positive'],r['negative'],r['unknown_in_eligible'],f"[0,{r['unknown_in_eligible']}/{r['eligible_true']}]" ] for r in strict]),'', 'T11_explicit_reason的第5项只要求原请求实际Effect/Receipt；P3R_identity_guard另要求identity相同参数请求执行。它们不是同一个合同。F旧14/24、G旧6/15为T17推导reason版本的点值，仍作为历史结果保留。严格上界恰与旧点值相等时，也不能把范围改写为确定点值。更强合取增加已知false，只改变该合同下的可辨识结论，不是同一风险下降。','', '## 3. P4 E_STS只加显示别名','', '`raw_metric=E_STS`、`protocol=U_and_not_verified_contract_violation`保持原样；正文显示 **STS_target_contract**。本合同为U AND NOT receipted risk-selector endpoint。P0辅助E_STS显示E_STS_posthoc(P0)，依赖其实际业务违规V与辅助标签；本轮不重标、不合并分母。UEA单独要求实际Effect/Receipt和授权事实，V不改名UEA，也不新算“授权版STS”。','', '## 4. 额外发现的版本分母冲突','', 'F和H的c2-tool-return-grid/valid_only，P3R保存四格各13，P4保存四格各15；两者点值均1。表A保留P3R，表B保留P4。scheduled四格各15不受该差异影响。本轮仅证实保存分母差异，未重新裁定资格算法或执行原始事实复算。详见[NUMERIC_CONFLICTS.csv](NUMERIC_CONFLICTS.csv)。']
 (OUT/'INTERPRETATION_AMENDMENTS.md').write_text('\n'.join(amendments)+'\n',encoding='utf-8')
 limitations=[('L01','自然语言真值与人审','独立参照限有限模型/受控状态机；独立人审仍0，不给通用自然语言准确率。'),('L02','Full两项未知','同一个unknown_reason构念的两个ALR合同；独立参照持有真值不授权向许可视图泄漏reason。'),('L03','旧CI语义','593结构有效对中289中和破坏JSON；另304语义未确认。identity稳定子集不能消除语义缺口。'),('L04','新Live ALR','原敏感请求0/0，不是0%洗白风险。'),('L05','RIR零值与资格','目标/中性chain各0/4；不撤销对照也零，不能证明撤销因果收益；confirmed-prefix仍无有效分母。'),('L06','两种pot','旧观测效果集合差不是静态穷尽能力；声明有限域pot不回填T17或外推任意Agent。'),('L07','任务证书可替代','1059条可依剩余对象、机械义务及会话事实恢复；证书形式不独占必要，任务完成信息仍重要。'),('L08','Scope参照覆盖','动作级参考引擎不包含完整生产Scope语义；小参照集无变化不说明Scope无用。'),('L09','有限不可辨识见证','2对既有世界只证明声明观察限制内无法保证两个正确点值，不证明SkillFlow唯一。'),('L10','最小证明路径','仅合同级足够支持路径，未搜索所有证据子集，不称全局最小。'),('L11','P0/P2版本与STS','历史模型/传输混杂不因P4消失；P0辅助E_STS、P4 STS_target_contract与UEA分开。'),('L12','HIAA valid_only分母冲突','F/H ToolReturn的P3R 13与P4 15并列保留，同为1不互换分母；本轮不修预测器。'),('L13','历史manifest绑定','本地具名文件哈希不等于每次历史运行原字节不可变快照。'),('L14','检查与沙箱边界','哈希一致证明字节，Python读取审计不等于抵御任意恶意代码的完整安全沙箱证明；既有外部复核范围按其报告引用。')]
 (OUT/'RETAINED_LIMITATIONS.md').write_text('# 结项保留限制\n\n这些是结项边界，不是本轮继续补实验的待办。\n\n'+md(['编号','主题','保留表述'],limitations)+'\n',encoding='utf-8')
 paper='''# P3/P4章节草稿：统一证据上的机制测量与可辨识性

## 测量对象与证据合同

SkillFlow首先把运行中的请求、Effect/Receipt、授权、对象来源、会话与撤销，以及已保存的反事实分支，组织为可定位的运行证据。HIAA、ALR、RIR、UEA、来源与CI回答不同问题，并使用各自的统计单位与资格条件。我们不把它们合成单条任务的在线攻击概率，也不把缺证视为安全。HIAA_run要求能力、任务和selector匹配的target/neutral Skill × 单一bridge on/off四格；ALR的单位是唯一授权请求；RIR的单位是有资格的前缀链在指定后续会话的观察。每个估计保留原合同、分母、未知及适用边界，见[表A](tables/table_A.md)与[来源索引](tables/SOURCE_LOCATORS.csv)。

## P3/P3R：机制结果先于防御比较

正式历史事实包括F/G各360核心与270个Replay候选，以及H新增270核心与270候选，共990核心和810候选。F+H是630核心、540候选，不能再次重复计入F。历史Live、T18 Scripted/Fake Reference、P3R有限构念和新增Live补充分层报告，共享前缀及k1/k3不作为独立新增样本。

在scheduled四格下，F的Context和ToolReturn HIAA_run均为1；G分别为0.6和0.466667，原簇bootstrap区间分别为[0.4,0.8]与[0.2,2/3]；H分别为0和1。这些是同任务单桥梁的差中差，不是Evidence与All的ASR差。G的valid-only Context为空分母，ToolReturn只剩每格1次。结项另外发现F/H ToolReturn的valid-only保存分母在P3R与P4间分别为13和15；两者点值相同但资格口径不能互换，故表A保留P3R值，表B保留P4状态，并公开[差异记录](NUMERIC_CONFLICTS.csv)。本轮不重新执行原始事实复算。

静态能力与观测执行严格分开。旧T17观测未授权效果集合差为0，只说明保存执行的集合关系；有限闭合声明模型中，存在没有观测执行但可达能力差为2的构念。开放语义保留[0,2]识别界。该权重和不是200%概率，也不是任意平台的能力上界。

ALR保留三种口径。旧T17推导reason的点值为F 14/24、G 6/15。要求原始显式reason的T11七条件，F为0真/9假/15未知，G为0/5/10；另加identity执行门后分别为0/10/14与0/9/6。这些严格范围不能替换为旧点值；合取更强导致上界更小不表示攻击风险降低。新增Live没有原敏感请求，两个严格合同仍是0/0。

RIR保留最终任务成功筛选的legacy合同、真实Memory/撤销/充分会话观察的chain合同，以及还要求撤销前控制影响已采用的confirmed-prefix合同。F的chain在k1为0/13、k3为0/14，G为空分母，H为0/13；新Live目标与中性各0/4，k1/k3相关。不撤销对照同样没有目标风险，因此零残留不能归因于撤销收益。confirmed-prefix仍缺合格分母。

UEA依实际Effect/Receipt与授权事实，历史F/G/H未授权操作数分别90、52、0，每操作权重1。来源micro-F1分别约0.973136、0.999358、0.968969，但其独立参照是记录器来源成员，不能外推自然语言因果真值。旧整对象CI在F/G/H的有符号平均分别为107/237、22/122、30/234，正、零、负结果全部保留。593个结构有效对中289个中和破坏原JSON，其余304个也没有自动获得精准控制语义资格；这些结果只作为整对象消融探针。

## P4：相同冻结事实下的证据消融

P4使用19,392个固定指标查询，建立Full、十种单证据族缺省视图与两个负对照，共保存252,096条离线结果。视图改变可见信息而不改变已发生事实；原答案标签及依赖缓存不进入预测路径。这些结果不是252,096次独立实验。完整域、合同、阶段、k及分支分层见[表B](tables/table_B.md)与[13视图附表](tables/metric_ablation_all13_strata.csv)。点值、范围、未知、不适用和技术分析错误分开；资格未知包含在未知内，不重复加总。

各证据的影响应按指标分母解释。删来源造成8,166条点值损失，其中7,472条是来源成员查询自身，另有ALR 87、CI 593、RIR 14条下游查询，占比分别应以其实际合同和固定查询分母说明。自身占总损失约91.50%，不能据此排序“来源最重要”。F/Context scheduled HIAA从1变为[-1,1]时，保留的请求仍不能证明已签发回执；该界是缺证识别范围，不是攻击概率或抽样置信区间。

独立参照包含314条查询，其中308条资格可知，192条具有确定且适用的真值。Full可给190条点值，190条均与参照一致，覆盖为190/192；删Receipt、Grant与生命周期后可判数分别为137、48、51，已答部分仍一致。因此只报告“准确率100%”会隐藏实质覆盖差异。Full的两项未知来自同一个缺reason构念的两个ALR合同，说明完整许可视图也不是全知库。各指标/合同与13视图的覆盖及已答一致性见[表C](tables/table_C.md)。人类语义审核仍为0。

证据依赖并不意味着某种证书形式独占必要。已有1,059条带任务证书的任务判断可由保留对象哈希、公开机械义务与会话关系恢复；存在有效Grant时，ALR合取也可在reason缺失后保持false。另一方面，两对既有有限模型在删Grant或删静态规则后具有相同许可观察而真值分别为2和0，因而只使用该观察的估计器不能保证对两个世界都给出正确点值。[六张案例卡](PAPER_CASES.md)同时展示充分替代路径、合法短路与有限不可辨识性，避免把定义依赖本身当作框架唯一性的证明。

## 名称、适用性与后文衔接

P4原始E_STS在正文显示为STS_target_contract，保留raw_metric和原protocol；其含义是U AND NOT receipted risk-selector endpoint。P0辅助E_STS依赖其实际业务违规V，UEA则另检查授权，三者不能混名或混分母。旧P0/P2的辅助标签、人审0、模型/传输混杂与未知保留，具体映射见[METRIC_NAME_MAP.csv](METRIC_NAME_MAP.csv)。

上述结果支持运行证据对测量可辨识性的部分作用，支持替代证明路径和限定有限域内的不可辨识性；它们没有证明自然语言通用准确性、框架唯一必要性或Live撤销因果收益。论文随后可讨论P0公开任务中的测量差异，并以已有Evidence防御实验展示应用。当前运行证据被使用，不等于聚合HIAA/ALR/RIR已经驱动在线路由；P4不授权新增画像算法、比较基线或后续Live实验。完整边界见[RETAINED_LIMITATIONS.md](RETAINED_LIMITATIONS.md)。
'''
 (OUT/'PAPER_P3_P4_SECTION.md').write_text(paper,encoding='utf-8')
 claims=[('C01','统一证据支撑有合同和来源定位的机制测量','PARTIALLY_SUPPORTED','tables/mechanism_results.csv;tables/SOURCE_LOCATORS.csv','有限运行域；不外推任意Agent'),('C02','证据删除改变测量可辨识性','SUPPORTED_IN_SAVED_QUERY_SET','tables/metric_ablation.csv;tables/self_vs_downstream.csv','查询相关；不能从总损失排序家族重要性'),('C03','来源删除主要造成自身指标损失','SUPPORTED','INTERPRETATION_AMENDMENTS.md','7472/8166自身，694下游；不是独立样本数'),('C04','严格ALR上界更小代表风险降低','NOT_SUPPORTED','tables/mechanism_results.csv;METRIC_NAME_MAP.csv','不同合取合同不能解释成干预收益'),('C05','有限相同观察可对应不同真值','SUPPORTED_FINITE_ONLY','PAPER_CASES.md;data/paper_cases.json','2对既有有限模型；不证明唯一框架'),('C06','任务证书形式独占必要','NOT_SUPPORTED','PAPER_CASES.md;data/closeout_data.json','1059/1059既有任务点值有替代证明'),('C07','Full通用正确率100%','NOT_SUPPORTED','tables/independent_reference.csv','190/192覆盖，已答190/190；独立人审0'),('C08','旧CI都是精准控制语义因果gold','NOT_SUPPORTED','RETAINED_LIMITATIONS.md','289/593破坏JSON，另304语义未确认'),('C09','Live撤销带来因果安全收益','NOT_SUPPORTED','tables/mechanism_results.csv','RIR目标/中性及不撤销均零；更严分母缺失'),('C10','P4 E_STS可以与P0 E_STS、UEA合并','NOT_SUPPORTED','METRIC_NAME_MAP.csv','显示合同分开，原字段不改'),('C11','同名valid_only可直接跨P3R/P4合并','NOT_SUPPORTED','NUMERIC_CONFLICTS.csv','F/H ToolReturn每格13对15，点值相同不消除分母差异')]
 csvout('CLAIM_EVIDENCE_MATRIX.csv',[dict(claim_id=a,claim=b,support=c,evidence_files=e,scope_limit=f,human_reviews=0) for a,b,c,e,f in claims])
 dep={'P4':{'local_path':binding['p4_zip'],'upload_alias':binding['upload_alias'],'sha256':binding['p4_zip_sha256'],'members':185},'P3R':{'local_path':str(p3zip),'sha256':sha(p3zip)},'closeout_data':{'path':'data/closeout_data.json','sha256':sha(OUT/'data/closeout_data.json')},'reproduction_scope':'closeout tables and prose only; original experiment reproduction requires original P4/P3R archives'};dump('DEPENDENCIES.json',dep)
 (OUT/'REPRODUCE.md').write_text(r'''# 两种不同的复现范围

本包是文稿审查包，不是单包可重跑全实验的镜像。没有重新内嵌P3/P4大包，也没有13组完整预测副本。

## 本轮三表与案例

在E盘新目录解包，使用Python 3.11+标准库：

```powershell
python -X utf8 -B .\code\render_tables.py
```

该入口只读取本包data/closeout_data.json和data/case_evidence_bindings.json，生成Markdown、UTF-8 CSV、LaTeX片段与六张案例卡；不导入预测器、不访问网络或调用模型。LaTeX仅交片段，需要使用方现有中文排版环境和longtable；本轮不编译PDF。论文段落与限制属于本轮整理文字。

如果要核对整理数据从何而来：SOURCE_MANIFEST逐项记录本地源路径/哈希，collect_saved_results.py说明本轮唯一一次已保存预测重聚合。该脚本需要原P4和P3R目录，且会拒绝覆盖已有closeout_data.json；不要为了补绿重新执行它。表内source_ref是相对仓库的原件定位，行号/JSON pointer属于原包。

## 原P4预测复算（仅供未来审查者）

取得DEPENDENCIES.json中的原P4 ZIP并核对准确SHA256后，依原包REPRODUCE.md使用其code/reproduce_offline.py。原P3/P3R机制来源另需列出的原P3R包。本轮没有改变这些路径，没有调用该预测器，也没有重跑64×13切片。

既有作者便携记录、作者ZIP记录与外部机械复核报告分别保留；它们都不是本轮新增832条验证，不能累计成新实验数量。本轮只做文档生成、保存结果加总、别名、链接与哈希检查。
''',encoding='utf-8')
 (OUT/'README.md').write_text('# P4结项与论文材料\n\n[P4_CLOSEOUT.md](P4_CLOSEOUT.md)记录管理状态与检查边界；[章节初稿](PAPER_P3_P4_SECTION.md)、[三张论文表](PAPER_TABLES.md)、[六案例](PAPER_CASES.md)可直接审阅。\n\n[解释修订](INTERPRETATION_AMENDMENTS.md)、[显示名称](METRIC_NAME_MAP.csv)、[保留限制](RETAINED_LIMITATIONS.md)、[分母冲突](NUMERIC_CONFLICTS.csv)均不回写原P4。\n\n[复现说明](REPRODUCE.md)明确依赖原包；本轮不执行P1/P5/P6，不自动提交或推送。\n',encoding='utf-8')
 print('Interpretation amendments, manuscript section, claim matrix and dependency-aware reproduction written')
if __name__=='__main__':main()
