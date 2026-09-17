"""Seal local review outputs and ZIP; no git writes or publication."""
import json,hashlib,zipfile,datetime,ast,sys,os
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];READS=set()
for node in ast.parse((OUT/'analysis/independent.py').read_text('utf-8-sig')).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('guard','dump'):exec(compile(ast.Module(body=[node],type_ignores=[]),'<io>','exec'))
sys.addaudithook(guard)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
validation=json.loads((OUT/'audit/DELIVERY_VALIDATION.json').read_text('utf-8'));assert validation['failed']==0
preserve=json.loads((OUT/'audit/WORKSPACE_PRESERVATION.json').read_text('utf-8-sig'));assert preserve['root_readme_unchanged'] and preserve['head']=='21efe89a11b56b2f48ae6f351ef46cca467913fb'
# Validate internal Markdown destinations; source code and external references aren't links.
import re
broken=[]
for p in OUT.glob('*.md'):
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text('utf-8')):
  if '://' not in link and not link.startswith('#') and not (p.parent/link).exists():broken.append({'file':p.name,'link':link})
# UPLOAD_MANIFEST is intentionally created immediately below.
broken=[x for x in broken if x['link']!='UPLOAD_MANIFEST.json']
assert not broken,broken
(OUT/'HANDOFF.md').write_text('''# 下一次对话交接

P3已完成并停止，状态COMPLETED_WITH_DOCUMENTED_GAPS。先读README→P3_METRIC_MAIN→CONTRACT_DIFFERENCES→GAP_LIST，再按证据定位审查。

事实复算：T17 F/G各360核心270 Replay终态，H新增270/270；F+H完整630/540，不重复计F。预检独立；T18 264/44独立域。原算法980指标对象与历史一致，独立标准库核对1326项一致；T18 308×4端点核对一致。45项交付检查通过，后续机制分层聚合也一致。

F/G主结果：Context HIAA1/0.6，ToolReturn1/0.466667；ALR14/24、6/15；RIR1/3为0/13与N/A；UEA90/52；来源F1为6448/6626、3112/3114；CI为107/237、22/122。这些是结构化公开事实复算，不是旧README转录。

限制不可丢：HIAA_pot仅观测集合差；ALR显式原reason缺失，历史推导口径另列；RIR条件分母不证明污染前缀已确认；identity不稳定F5/G16；G格式失败171/360；独立核对仍共享授权Oracle与新图深度标签，未另写bootstrap。人工复核未做。

本轮新Actor/Router/Checker/Judge/本地模型/攻击生成/业务Replay全0。未读Key、未初始化SDK、未联网、未commit/push、未改Router/组件/执行器/恢复。旧T19队列及未知保持停止。P0辅助标签、人审0、unknown、PROCESSED_WITH_GAPS保留；P2不重跑；P1延期。

Metric→Decision只查六个已保存initial_consume边界及已绑定冻结源码，发现局部证据消费，未发现聚合HIAA/ALR/RIR数值输入。Evidence-Profile-v1只归档，不实施P4/P5/P5-RX/P6。任何后续工作需由用户明确启动。

根README的已有修改未覆盖；追加文本在audit/ROOT_README_APPEND_PROPOSED.md供之后审查合入。UPLOAD_MANIFEST是逐路径提交清单，不是已上传。审查ZIP需要已有公开集合与匹配源码来复算原事实，requires_existing_public_collection=true。
''',encoding='utf-8')
status=json.loads((OUT/'P3_STATUS.json').read_text('utf-8'));status['delivery_validation']={'passed':45,'failed':0,'source_files_verified_unchanged':1338,'mechanism_strata_checked':True};status['workspace_preservation']=preserve;status['stopped_at']='P3_LOCAL_REVIEW_DELIVERY';status['review_zip']='P3_REVIEW_'+OUT.name+'.zip';dump('P3_STATUS.json',status)
# Keep all original analysis files; no cleanup or deletion.
archive=OUT/status['review_zip'];assert not archive.exists(),'refuse to overwrite review archive'
excluded={'UPLOAD_MANIFEST.json','BUNDLE_MANIFEST.json','ZIP_RECEIPT.json',archive.name}
files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in excluded)
entries=[{'path':p.relative_to(ROOT).as_posix(),'bundle_path':p.relative_to(OUT).as_posix(),'size_bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
dump('UPLOAD_MANIFEST.json',{'status':'LOCAL_REVIEW_ONLY_NOT_COMMITTED_OR_PUSHED','repository':'Suuuu123su/Agent-SkillFlow','local_head':preserve['head'],'allowed_new_directory':OUT.relative_to(ROOT).as_posix(),'files':entries,'self_and_archive_hash_receipt_excluded':True,'proposed_future_existing_file_edit':{'path':'README.md','proposal':'audit/ROOT_README_APPEND_PROPOSED.md','applied':False},'do_not_stage_existing_changes':True,'requires_existing_public_collection':True})
files.append(OUT/'UPLOAD_MANIFEST.json')
dump('BUNDLE_MANIFEST.json',{'files':[{'path':p.relative_to(OUT).as_posix(),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in files],'self_excluded':'BUNDLE_MANIFEST.json','archive_excluded':archive.name,'requires_existing_public_collection':True})
files.append(OUT/'BUNDLE_MANIFEST.json')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in files:z.write(p,p.relative_to(OUT).as_posix())
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 byname={p.relative_to(OUT).as_posix():p for p in files};assert set(z.namelist())==set(byname)
 for name,p in byname.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha(p)
dump('ZIP_RECEIPT.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'entries':len(files),'all_entries_match_disk_sha256':True,'crc_test':'PASS','internal_markdown_links':'PASS','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requires_existing_public_collection':True,'publication_performed':False,'note':'ZIP_RECEIPT intentionally external; no self-hash cycle'})
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'entries':len(files),'sha256':sha(archive)},ensure_ascii=False))
