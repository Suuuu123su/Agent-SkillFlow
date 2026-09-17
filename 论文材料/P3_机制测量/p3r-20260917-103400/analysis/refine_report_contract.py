from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400\analysis\build_final_report.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("r.update(extra or {});long.append(r)","""r.update(extra or {});
 code='analysis/analyze_live.py' if domain=='LUNA_LIVE_REFERENCE' else 'analysis/capability_model.py' if metric=='hiaa_pot_declared' else 'analysis/reference_harness.py' if domain=='SCRIPTED_NEW' else 'analysis/recover_mechanisms.py'
 r.update(calculation_code=code,calculation_code_hash=sha(OUT/code),statistical_unit='declared effect-type weighted set' if metric=='hiaa_pot_declared' else 'unique authorization request' if metric.startswith('alr') else 'parent chain at session k' if metric.startswith('rir') else 'valid replay pair' if metric.startswith('ci') else 'contract-defined construct unit',interval_kind='finite_missing_evidence_identification_range_not_sampling_CI',independent_check_status='see independent event/graph/statistics audit and portable slice; scope varies by metric');long.append(r)""")
s=s.replace("每变体2实例×2重复；主分母仅撤销original分支", "表中范围是有限缺证识别区间，不是总体风险的置信区间；0/4不支持低总体风险结论。每变体2实例×2重复；主分母仅撤销original分支")
s=s.replace("精确区间、selector、run列表见", "scheduled簇bootstrap区间：F Context/ToolReturn均[1,1]；G Context[0.4,0.8]、ToolReturn[0.2,2/3]。精确区间、selector、run列表见")
s=s.replace("'historical_status':'hash verification at packaging'", "'historical_status':read(OUT/'audit/HISTORICAL_PRESERVATION.json') if (OUT/'audit/HISTORICAL_PRESERVATION.json').exists() else 'pending hash verification'")
p.write_text(s,encoding='utf-8')
