from common import *
import re,zipfile,datetime

def main():
 # Explicitly authorized append-only entry paths, all on E. No subprocess/network.
 entries=[ROOT/'README.md',ROOT/'docs/progress.md',ROOT/'论文材料/README.md']
 def audit(ev,args):
  if ev.startswith(('socket.','subprocess.','os.system')):raise RuntimeError('OFFLINE_CLOSEOUT_ONLY')
  if ev=='open' and isinstance(args[0],(str,bytes)):
   p=Path(os.fsdecode(args[0])).resolve();mode=str(args[1] or '');flags=args[2] or 0
   if p.name in ['auth.json','.env'] or p.suffix=='.dpapi':raise RuntimeError('NO_KEY_ACCESS')
   if any(x in mode for x in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):assert p.is_relative_to(OUT) or p in entries
 sys.addaudithook(audit)
 assert not (OUT/'p4-closeout-review.zip').exists(),'refuse overwrite archive'
 checks=read(OUT/'checks/CLOSEOUT_CHECKS.json');assert checks['status']=='PASS'
 binding=read(OUT/'checks/INPUT_BINDING.json');baseline=read(OUT/'checks/WORKSPACE_BASELINE.json');d=read(OUT/'data/closeout_data.json')
 for rel,h in baseline.items():assert sha(ROOT/rel)==h,('concurrent workspace change',rel)
 for r in binding['member_checks']:assert sha(P4/r['path'])==r['sha256'],r['path']
 assert sha(Path(binding['p4_zip']))==binding['p4_zip_sha256']
 dump('checks/PRESERVATION.json',{'original_P4_members_unchanged':len(binding['member_checks']),'original_P4_zip_unchanged':True,'all_nine_preexisting_modified_files_unchanged_before_append':True,'original_status_unchanged':True})
 status={'stage':'P4-CLOSEOUT','management_status':'CLOSED_WITH_DOCUMENTED_GAPS','original_P4_status':'COMPLETED_WITH_DOCUMENTED_GAPS','data_processing':{'saved_prediction_read_passes':1,'saved_rows':252096,'published_strata_checked':4758,'new_predictions':0,'P3_raw_recomputation':0},'existing_verification_records':{'author_portable':832,'author_zip_roundtrip':832,'external_report_portable':832,'counting_rule':'separate historical records, not added, not current checks','external_source':'task_pack/SkillFlow_P4_Closeout_Codex/references/P4_EXTERNAL_REVIEW.md'},'current_checks':{'document_checks':16,'source_hashes':61,'P4_manifest_members':184,'new_portable_64x13_checks':0,'scope':'saved-result aggregates, formats, names, links, hashes and ZIP members; no predictors'},'reference_scope':{'queries':314,'eligibility_known':308,'determinate_applicable':192,'Full_answered':190,'Full_agrees':190,'human_reviews':0},'research_support':{'measurement_identifiability':'PARTIALLY_SUPPORTED','unique_framework_necessity':'NOT_ESTABLISHED','live_revocation_benefit':'NOT_SUPPORTED','general_natural_language_accuracy':'NOT_ESTABLISHED'},'retained_numeric_conflicts':2,'tables':{'A':138,'B':273,'C':130,'B_full_strata':4758,'C_overall':13},'case_cards':6,'new_activity':{k:0 for k in ['API','Actor','Router','Checker','Judge','local_model','attack_generation','business_tool','counterfactual_replay']},'next_stages':{'P1':'DEFERRED','P5':'NOT_STARTED','P6':'NOT_STARTED'},'git_commit':False,'git_push':False,'review_zip':'p4-closeout-review.zip','packaging_evidence':'ZIP_RECEIPT.json (sidecar; final verification after ZIP creation)'}
 dump('P4_CLOSEOUT_STATUS.json',status)
 (OUT/'P4_CLOSEOUT.md').write_text('''# P4结项

管理状态：**CLOSED_WITH_DOCUMENTED_GAPS**。原P4仍为COMPLETED_WITH_DOCUMENTED_GAPS，原输入、预测、标签和状态未改动。

## 交付与研究结论

[三表](PAPER_TABLES.md)由同一份整理数据输出MD、UTF-8 CSV和LaTeX：表A 138行、表B 273行（完整4758层附表）、表C 130行并附13视图总体。[六张案例](PAPER_CASES.md)、[章节草稿](PAPER_P3_P4_SECTION.md)、[主张矩阵](CLAIM_EVIDENCE_MATRIX.csv)已完成。支持证据影响测量可辨识性的部分结论，未证明框架唯一必要性、通用自然语言准确性或Live撤销因果收益。独立人审仍0。

来源点值损失8166分为7472自身和694下游（ALR87、CI593、RIR14），不用于证据重要性排名。两种严格ALR合同分别保留；P4 E_STS仅显示为STS_target_contract。Full可判190/192，已答190/190与有限参照一致。

## 四层记录分开

- 原数据处理：固定19392查询×13视图，252096保存结果；原工程记录和研究限制均保留。
- 既有验证：作者便携832、作者ZIP832、外部报告832分别引用；不相加，不是本轮新增验证。外部报告为任务包提供的既有报告，不冒称本轮独立人审。
- 本轮检查：唯一一次读取保存预测并重聚合，4758层及参考计数一致；16项文档/数值/别名检查、61份使用来源哈希、原P4的184清单成员及原ZIP保全检查。没有新预测、原事实复算或64×13便携运行。链接与本包成员校验见[CLOSEOUT_CHECKS.json](CLOSEOUT_CHECKS.json)；最终ZIP字节回执单独在同目录ZIP_RECEIPT.json。
- 研究支持：有限参照314查询中308资格可知、192有确定适用真值；查询和会话相关，不是192独立任务。范围与抽样置信区间分开。

## 保留缺口

F/H ToolReturn valid_only四格在P3R各13、P4各15；点值均1不能合并分母。本轮记录[两个版本冲突](NUMERIC_CONFLICTS.csv)，不修原预测。旧CI有289/593中和破坏JSON、其余304语义未确认；新增Live ALR空分母、RIR零值无撤销收益证明、confirmed-prefix缺资格分母仍保留。完整限制见[RETAINED_LIMITATIONS.md](RETAINED_LIMITATIONS.md)。

## 归档边界

所有新增模型/业务/重放调用0。只追加本地论文入口和进度原文，保全记录在checks/ENTRY_UPDATES.json。未commit/push，[待提交清单](COMMIT_REVIEW_LIST.md)要求只选本次新增块。小型ZIP不内嵌旧大包，依赖准确路径与SHA256见[DEPENDENCIES.json](DEPENDENCIES.json)；[复现说明](REPRODUCE.md)明确文稿重建与原实验依赖。P1继续延期，P5/P6未开始。完成此结项即停止。
''',encoding='utf-8')
 rel=OUT.relative_to(ROOT).as_posix();marker='<!-- P4_CLOSEOUT_20260917_141455 -->';updates=[];patch=[]
 for p in entries:
  before=p.read_bytes() if p.exists() else b'';assert marker.encode() not in before
  target=os.path.relpath(OUT/'P4_CLOSEOUT.md',p.parent).replace('\\','/')
  text=f'\n\n{marker}\n## P4结项（2026-09-17）\n\n状态：CLOSED_WITH_DOCUMENTED_GAPS；原P4状态与事实不变。[结项及论文三表]({target})已交付，附章节草稿、六案例与审查ZIP。仅一次读取保存预测重聚合，另做文档、加总、别名、链接和哈希检查；新增模型/业务/重放调用0，未运行新预测器或便携832切片。Full覆盖190/192、已答一致190/190，人审0。保留F/H valid-only每格13对15、旧CI语义、ALR空分母和RIR因果限制。未提交/推送；P1延期，P5/P6不启动。\n'
  with p.open('ab') as f:f.write(text.encode('utf-8'))
  after=p.read_bytes();assert after.startswith(before) and after[len(before):]==text.encode('utf-8')
  updates.append({'path':p.relative_to(ROOT).as_posix(),'previous_bytes':len(before),'previous_sha256':hashlib.sha256(before).hexdigest(),'new_sha256':sha(p),'original_prefix_preserved':True,'mode':'append' if before else 'new'})
  patch.extend(['--- a/'+p.relative_to(ROOT).as_posix(),'+++ b/'+p.relative_to(ROOT).as_posix(),f'@@ -{len(before.splitlines())},0 +{len(before.splitlines())+1},{len(text.splitlines())} @@']+['+'+x for x in text.splitlines()])
 dump('checks/ENTRY_UPDATES.json',updates);(OUT/'LOCAL_ENTRY_APPEND.patch').write_text('\n'.join(patch)+'\n',encoding='utf-8')
 for rel0,h in baseline.items():
  if rel0 not in ['README.md','docs/progress.md']:assert sha(ROOT/rel0)==h
 (OUT/'COMMIT_REVIEW_LIST.md').write_text('''# 待提交清单（未暂存、未提交、未推送）

1. 本closeout目录：结项状态、三表各格式及完整附表、六案例、章节文字、主张/别名/限制/差异、整理数据、来源哈希、轻量生成及检查代码、任务包参考与归档凭证。
2. 新增论文材料/README.md入口；根README.md与docs/progress.md仅提交标记P4_CLOSEOUT_20260917_141455后的本轮追加块。精确内容见LOCAL_ENTRY_APPEND.patch，前缀保全哈希见checks/ENTRY_UPDATES.json。
3. 审查ZIP可按仓库资产策略作为本地附件，不必与展开内容重复提交。

原README和progress已有用户修改，不能整文件盲目暂存。其余既有修改（.gitignore、五个instrumentation/models源文件及test_t14_security_isolation.py）不属本轮。P3/P3R与原P4目录只读，未更改或重新打包其大包。不使用git add -A，不自动commit/push。任务包的NEXT_PLAN仅归档，未执行P5。
''',encoding='utf-8')
 dump('CLOSEOUT_CHECKS.json',checks)
 required=['README.md','P4_CLOSEOUT.md','P4_CLOSEOUT_STATUS.json','INTERPRETATION_AMENDMENTS.md','METRIC_NAME_MAP.csv','PAPER_TABLES.md','tables/mechanism_results.csv','tables/metric_ablation.csv','tables/self_vs_downstream.csv','tables/independent_reference.csv','tables/paper_tables.tex','PAPER_P3_P4_SECTION.md','PAPER_CASES.md','CLAIM_EVIDENCE_MATRIX.csv','RETAINED_LIMITATIONS.md','SOURCE_MANIFEST.json','REPRODUCE.md','COMMIT_REVIEW_LIST.md']
 assert all((OUT/x).is_file() for x in required)
 # Only current authored document links; archived external references keep their original context.
 links=[]
 for p in list(OUT.glob('*.md'))+list((OUT/'tables').glob('*.md')):
  for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
   if '://' in target or target.startswith('#'):continue
   dest=(p.parent/target.split('#')[0]).resolve();assert dest.exists(),(p.name,target);links.append({'document':p.relative_to(OUT).as_posix(),'target':target,'exists':True})
 checks['delivery_checks']={'required_files':len(required),'resolved_authored_links':len(links),'entry_prefixes_preserved':len(updates),'unrelated_modified_files_preserved':7,'original_manifest_members_unchanged':184,'zip_validation':'see ZIP_RECEIPT.json sidecar'}
 checks['acceptance_items']=[{'item':i,'status':'PASS_WITH_DOCUMENTED_SCOPE','evidence':e} for i,e in enumerate(['checks/INPUT_BINDING.json','checks/CLOSEOUT_CHECKS.json','INTERPRETATION_AMENDMENTS.md','METRIC_NAME_MAP.csv','CLAIM_EVIDENCE_MATRIX.csv','PAPER_CASES.md','checks/PRESERVATION.json;checks/ENTRY_UPDATES.json','DEPENDENCIES.json;ZIP_RECEIPT.json'],1)]
 dump('checks/LINK_CHECKS.json',links);dump('CLOSEOUT_CHECKS.json',checks)
 # Small document bundle, no nested old ZIPs and no raw 13-view result files.
 files=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ['MANIFEST.json','ZIP_RECEIPT.json'] and p.suffix!='.zip' and '__pycache__' not in p.parts]
 manifest=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]
 dump('MANIFEST.json',{'scope':'paper closeout review, not standalone experiment reproduction','files':manifest})
 zpath=OUT/'p4-closeout-review.zip'
 with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in files+[OUT/'MANIFEST.json']:z.write(p,p.relative_to(OUT).as_posix())
 with zipfile.ZipFile(zpath) as z:
  assert len(z.namelist())==len(manifest)+1
  for r in manifest:
   content=z.read(r['path']);assert len(content)==r['bytes'] and hashlib.sha256(content).hexdigest()==r['sha256']
  assert json.loads(z.read('P4_CLOSEOUT_STATUS.json'))['management_status']=='CLOSED_WITH_DOCUMENTED_GAPS'
  assert not any(n.endswith('.zip') for n in z.namelist())
 dump('ZIP_RECEIPT.json',{'archive':zpath.name,'sha256':sha(zpath),'bytes':zpath.stat().st_size,'members':len(manifest)+1,'manifest_members_verified':len(manifest),'status':'PASS','nested_archives':0,'predictors_executed':0,'external_dependency':'original P4 and P3R archives listed in DEPENDENCIES.json','timestamp':datetime.datetime.now().astimezone().isoformat()})
 print(can(read(OUT/'ZIP_RECEIPT.json')))
if __name__=='__main__':main()
