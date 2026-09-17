from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400\analysis\build_final_report.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("text+='\\n每变体", "text+='\\n每变体")
s=s.replace("已发生UE不因业务失败被剔除。\\n\\n## 4.", "已发生UE不因业务失败被剔除。无撤销C分支的实际端点也必须读取：若同为零，不能把撤销R的零归因于撤销带来的收益。\\n\\n## 4.")
s=s.replace("print(json.dumps({'stage':stage", """md('audit/ROOT_README_APPEND_PROPOSED.md',f'''## P3R 机制补全（本地审查，{stage}）

独立输出：[p3r-20260917-103400](论文材料/P3_机制测量/p3r-20260917-103400/P3R_FINAL_REPORT.md)。原P3及用户修改字节保全。DS M2全部30条原始失败已定位；静态声明域、严格ALR三值、RIR新旧队列、T18、CI敏感性和独立核对已完成。

用户明确授权的Luna补实验实际{ledger['requests']['attempts']}次尝试、未知{ledger['requests']['response_unknown']}；新GLM/DS/Judge/防御/攻击生成0。执行完成不等于全部科学缺口关闭；严格结果与分母见主表。人审0，旧暂停队列不恢复，P4/P5和画像路由不实施。未commit/push。
''')
print(json.dumps({'stage':stage""")
p.write_text(s,encoding='utf-8')
