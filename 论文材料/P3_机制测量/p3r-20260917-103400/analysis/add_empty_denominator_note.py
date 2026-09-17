from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400\analysis\build_final_report.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("text+='\\n新参考引擎在实际决策分支内", "text+=('\\n本轮新Live没有进入暴露请求分母，严格ALR点值不可识别；不把0/0写成0。\\n' if not ex else '\\n新Live存在实际暴露请求，依七条件及独立事件连接计算。\\n')\ntext+='\\n新参考引擎在实际决策分支内")
s=s.replace("新RIR与ALR的分子、分母和未知请直接看", "新ALR实际暴露请求N={len(ex)}，无敏感请求前缀{live['alr']['no_sensitive_request']}/4。{'严格ALR Live点值N/A；构念正例不补入Live分母。' if not ex else '严格三值与identity附加条件分列。'}\n\n新RIR与ALR的分子、分母和未知请直接看")
p.write_text(s,encoding='utf-8')
