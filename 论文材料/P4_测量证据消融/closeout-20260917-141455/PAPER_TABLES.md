# P3/P4论文表（统一整理数据生成）

三种格式共同来自[data/closeout_data.json](data/closeout_data.json)。完整源文件、合同、统计单位与适用边界按行ID见[tables/SOURCE_LOCATORS.csv](tables/SOURCE_LOCATORS.csv)。原预测及标签未修改。

## 表A：机制实证摘要
表A只整理已保存P3/P3R结果；严格合同的分层补充明确来自P4已保存Full表。历史Live、受控构念、T18和新Live不混池。bootstrap原字段完整保存在CSV中，缺证识别界另列。F/H ToolReturn valid_only的P3R分母13与P4分母15存在版本差异，见NUMERIC_CONFLICTS.csv；同为1不能互换分母。

| 行 | 执行域/阶段 | 指标 | 原合同 | 设计 | 单位 | 分子/分母 | 值/四格 | 状态 |
|---|---|---|---|---|---|---|---|---|
| A001 | live_reference/f | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:15/15; D=1 | measured |
| A002 | live_reference/f | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:15/15; D=1 | measured |
| A003 | live_reference/f | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:15/15; D=1 | measured |
| A004 | live_reference/f | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/13; p01:0/13; p10:0/13; p11:13/13; D=1 | measured |
| A005 | live_reference/g | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:9/15; D=0.6 | measured |
| A006 | live_reference/g | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/0; p01:0/0; p10:0/0; p11:0/0; D=N/A | not_applicable |
| A007 | live_reference/g | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:7/15; D=0.466667 | measured |
| A008 | live_reference/g | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/1; p01:0/1; p10:0/1; p11:1/1; D=1 | measured |
| A009 | live_reference/h | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:0/15; D=0 | measured |
| A010 | live_reference/h | HIAA_run | T17-v2-actual-code-1535005c0085 | c1-context-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:0/15; D=0 | measured |
| A011 | live_reference/h | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / scheduled | matched four-cell run grid | see cells/set | p00:0/15; p01:0/15; p10:0/15; p11:15/15; D=1 | measured |
| A012 | live_reference/h | HIAA_run | T17-v2-actual-code-1535005c0085 | c2-tool-return-grid / valid_only | matched four-cell run grid | see cells/set | p00:0/13; p01:0/13; p10:0/13; p11:13/13; D=1 | measured |
| A013 | live_reference/f | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | f | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A014 | live_reference/f | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | f | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A015 | live_reference/g | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | g | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A016 | live_reference/g | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | g | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A017 | live_reference/h | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | h | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A018 | live_reference/h | HIAA_pot_observed | T17-v2-actual-code-e492693c0b5a | h | declared sensitivity-weighted observed effect-type set | see cells/set | 0 | measured |
| A019 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | and_missing | declared effect-type weighted set | see cells/set | 0 | point |
| A020 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | authorized_excluded_from_U | declared effect-type weighted set | see cells/set | 0 | point |
| A021 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | metadata_invariant | declared effect-type weighted set | see cells/set | 2 | point |
| A022 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | same_sets_true_zero | declared effect-type weighted set | see cells/set | 0 | point |
| A023 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | same_tool_wrong_source | declared effect-type weighted set | see cells/set | 0 | point |
| A024 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | unexecuted_but_reachable | declared effect-type weighted set | see cells/set | 2 | point |
| A025 | SCRIPTED_FINITE_DOMAIN/ | HIAA_pot_declared | declared_finite_v1 | unknown_not_zero | declared effect-type weighted set | see cells/set | [0,2] | bounded |
| A026 | T18_fake_reference/all_defenses | ALR | T18_original_contract | all_defenses/k | unique authorization request | 0/1 | 0 | point |
| A027 | T18_fake_reference/evidence_router | ALR | T18_original_contract | evidence_router/k | unique authorization request | 0/1 | 0 | point |
| A028 | T18_fake_reference/monitor | ALR | T18_original_contract | monitor/k | unique authorization request | 1/1 | 1 | point |
| A029 | T18_fake_reference/oracle_router | ALR | T18_original_contract | oracle_router/k | unique authorization request | 0/1 | 0 | point |
| A030 | T18_scripted/all_defenses | ALR | T18_original_contract | all_defenses/k | unique authorization request | 0/3 | 0 | point |
| A031 | T18_scripted/causal_only | ALR | T18_original_contract | causal_only/k | unique authorization request | 0/2 | 0 | point |
| A032 | T18_scripted/drift_isolation_only | ALR | T18_original_contract | drift_isolation_only/k | unique authorization request | 0/2 | 0 | point |
| A033 | T18_scripted/evidence_router | ALR | T18_original_contract | evidence_router/k | unique authorization request | 0/3 | 0 | point |
| A034 | T18_scripted/monitor | ALR | T18_original_contract | monitor/k | unique authorization request | 2/3 | 0.666667 | point |
| A035 | T18_scripted/oracle_router | ALR | T18_original_contract | oracle_router/k | unique authorization request | 0/2 | 0 | point |
| A036 | T18_scripted/task_alignment_only | ALR | T18_original_contract | task_alignment_only/k | unique authorization request | 0/2 | 0 | point |
| A037 | T18_scripted/tdg_only | ALR | T18_original_contract | tdg_only/k | unique authorization request | 0/2 | 0 | point |
| A038 | T18_scripted/universal_enforce | ALR | T18_original_contract | universal_enforce/k | unique authorization request | 0/2 | 0 | point |
| A039 | live_reference/f | ALR | T17-v2-actual-code-fccd3b9a0fc6 | f | ratio | 14/24 | 0.583333 | measured |
| A040 | live_reference/g | ALR | T17-v2-actual-code-fccd3b9a0fc6 | g | ratio | 6/15 | 0.4 | measured |
| A041 | live_reference/h | ALR | T17-v2-actual-code-fccd3b9a0fc6 | h | ratio | 0/22 | 0 | measured |
| A042 | SCRIPTED_NEW/ | ALR | frozen_replica_guard_strict | neutral_still_executes | unique authorization request | 0/1 | 0 | point |
| A043 | SCRIPTED_NEW/ | ALR | frozen_replica_guard_strict | ordinary_bypass | unique authorization request | 0/0 | N/A (not_applicable) | not_applicable |
| A044 | SCRIPTED_NEW/ | ALR | frozen_replica_guard_strict | positive | unique authorization request | 1/1 | 1 | point |
| A045 | SCRIPTED_NEW/ | ALR | frozen_replica_guard_strict | real_grant | unique authorization request | 0/1 | 0 | point |
| A046 | SCRIPTED_NEW/ | ALR | frozen_replica_guard_strict | unknown_reason | unique authorization request | 0/1 | [0,1] | bounded |
| A047 | LUNA_LIVE_REFERENCE/ | ALR | frozen_replica_guard_strict | alr_frozen_replica_guard_strict | unique authorization request | 0/0 | N/A (not_applicable) | not_applicable |
| A048 | LUNA_LIVE_REFERENCE/ | ALR | t11_strict | alr_t11_strict | unique authorization request | 0/0 | N/A (not_applicable) | not_applicable |
| A049 | HISTORICAL_LIVE/f | ALR | T11_explicit_reason | f | unique_request_or_no_request_sentinel | 0/24 | [0,0.625] | bounded |
| A050 | HISTORICAL_LIVE/f | ALR | P3R_identity_guard | f | unique_request_or_no_request_sentinel | 0/24 | [0,0.583333] | bounded |
| A051 | HISTORICAL_LIVE/g | ALR | T11_explicit_reason | g | unique_request_or_no_request_sentinel | 0/15 | [0,0.666667] | bounded |
| A052 | HISTORICAL_LIVE/g | ALR | P3R_identity_guard | g | unique_request_or_no_request_sentinel | 0/15 | [0,0.4] | bounded |
| A053 | HISTORICAL_LIVE/h | ALR | T11_explicit_reason | h | unique_request_or_no_request_sentinel | 0/22 | 0 | point |
| A054 | HISTORICAL_LIVE/h | ALR | P3R_identity_guard | h | unique_request_or_no_request_sentinel | 0/22 | 0 | point |
| A055 | T17_LIVE/f | RIR | RIR_chain_v1 | rir_chain_1 | parent chain at session k | 0/13 | 0 | point |
| A056 | T17_LIVE/f | RIR | RIR_chain_v1 | rir_chain_3 | parent chain at session k | 0/14 | 0 | point |
| A057 | T17_LIVE/g | RIR | RIR_chain_v1 | rir_chain_1 | parent chain at session k | 0/0 | N/A (not_applicable) | not_applicable |
| A058 | T17_LIVE/g | RIR | RIR_chain_v1 | rir_chain_3 | parent chain at session k | 0/0 | N/A (not_applicable) | not_applicable |
| A059 | T17_LIVE/h | RIR | RIR_chain_v1 | rir_chain_1 | parent chain at session k | 0/13 | 0 | point |
| A060 | T17_LIVE/h | RIR | RIR_chain_v1 | rir_chain_3 | parent chain at session k | 0/13 | 0 | point |
| A061 | T18_fake_reference/all_defenses | RIR | T18_original_contract | all_defenses/k1 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A062 | T18_fake_reference/all_defenses | RIR | T18_original_contract | all_defenses/k3 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A063 | T18_fake_reference/evidence_router | RIR | T18_original_contract | evidence_router/k1 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A064 | T18_fake_reference/evidence_router | RIR | T18_original_contract | evidence_router/k3 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A065 | T18_fake_reference/monitor | RIR | T18_original_contract | monitor/k1 | saved eligible chain at k | 1/2 | 0.5 | point |
| A066 | T18_fake_reference/monitor | RIR | T18_original_contract | monitor/k3 | saved eligible chain at k | 1/2 | 0.5 | point |
| A067 | T18_fake_reference/oracle_router | RIR | T18_original_contract | oracle_router/k1 | saved eligible chain at k | 0/1 | 0 | point |
| A068 | T18_fake_reference/oracle_router | RIR | T18_original_contract | oracle_router/k3 | saved eligible chain at k | 0/1 | 0 | point |
| A069 | T18_scripted/all_defenses | RIR | T18_original_contract | all_defenses/k1 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A070 | T18_scripted/all_defenses | RIR | T18_original_contract | all_defenses/k3 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A071 | T18_scripted/causal_only | RIR | T18_original_contract | causal_only/k1 | saved eligible chain at k | 0/4 | 0 | point |
| A072 | T18_scripted/causal_only | RIR | T18_original_contract | causal_only/k3 | saved eligible chain at k | 0/2 | 0 | point |
| A073 | T18_scripted/drift_isolation_only | RIR | T18_original_contract | drift_isolation_only/k1 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A074 | T18_scripted/drift_isolation_only | RIR | T18_original_contract | drift_isolation_only/k3 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A075 | T18_scripted/evidence_router | RIR | T18_original_contract | evidence_router/k1 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A076 | T18_scripted/evidence_router | RIR | T18_original_contract | evidence_router/k3 | saved eligible chain at k | 0/0 | N/A (not_applicable) | not_applicable |
| A077 | T18_scripted/monitor | RIR | T18_original_contract | monitor/k1 | saved eligible chain at k | 2/4 | 0.5 | point |
| A078 | T18_scripted/monitor | RIR | T18_original_contract | monitor/k3 | saved eligible chain at k | 1/2 | 0.5 | point |
| A079 | T18_scripted/oracle_router | RIR | T18_original_contract | oracle_router/k1 | saved eligible chain at k | 0/2 | 0 | point |
| A080 | T18_scripted/oracle_router | RIR | T18_original_contract | oracle_router/k3 | saved eligible chain at k | 0/1 | 0 | point |
| A081 | T18_scripted/task_alignment_only | RIR | T18_original_contract | task_alignment_only/k1 | saved eligible chain at k | 0/4 | 0 | point |
| A082 | T18_scripted/task_alignment_only | RIR | T18_original_contract | task_alignment_only/k3 | saved eligible chain at k | 0/2 | 0 | point |
| A083 | T18_scripted/tdg_only | RIR | T18_original_contract | tdg_only/k1 | saved eligible chain at k | 0/4 | 0 | point |
| A084 | T18_scripted/tdg_only | RIR | T18_original_contract | tdg_only/k3 | saved eligible chain at k | 0/2 | 0 | point |
| A085 | T18_scripted/universal_enforce | RIR | T18_original_contract | universal_enforce/k1 | saved eligible chain at k | 0/4 | 0 | point |
| A086 | T18_scripted/universal_enforce | RIR | T18_original_contract | universal_enforce/k3 | saved eligible chain at k | 0/2 | 0 | point |
| A087 | live_reference/f | RIR | T17-v2-actual-code-073c22fd14cd | f | ratio | 0/13 | 0 | measured |
| A088 | live_reference/f | RIR | T17-v2-actual-code-073c22fd14cd | f | ratio | 0/13 | 0 | measured |
| A089 | live_reference/g | RIR | T17-v2-actual-code-073c22fd14cd | g | ratio | 0/0 | N/A (not_applicable) | not_applicable |
| A090 | live_reference/g | RIR | T17-v2-actual-code-073c22fd14cd | g | ratio | 0/0 | N/A (not_applicable) | not_applicable |
| A091 | live_reference/h | RIR | T17-v2-actual-code-073c22fd14cd | h | ratio | 0/13 | 0 | measured |
| A092 | live_reference/h | RIR | T17-v2-actual-code-073c22fd14cd | h | ratio | 0/13 | 0 | measured |
| A093 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | legal_retention | parent chain at session k | 0/0 | N/A (revocation_absent) | revocation_absent |
| A094 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | legal_retention | parent chain at session k | 0/0 | N/A (revocation_absent) | revocation_absent |
| A095 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | missing_memory | parent chain at session k | 0/0 | N/A (memory_unformed) | memory_unformed |
| A096 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | missing_memory | parent chain at session k | 0/0 | N/A (memory_unformed) | memory_unformed |
| A097 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | negative | parent chain at session k | 0/1 | 0 | confirmed_no_residual |
| A098 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | negative | parent chain at session k | 0/1 | 0 | confirmed_no_residual |
| A099 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | positive | parent chain at session k | 1/1 | 1 | confirmed |
| A100 | SCRIPTED_NEW/ | RIR | RIR_chain_v1 | positive | parent chain at session k | 1/1 | 1 | confirmed |
| A101 | LUNA_LIVE_REFERENCE/ | RIR | RIR_chain_v1 | rir_chain_neutral/k1 | parent chain at session k | 0/4 | 0 | point |
| A102 | LUNA_LIVE_REFERENCE/ | RIR | RIR_chain_v1 | rir_chain_neutral/k3 | parent chain at session k | 0/4 | 0 | point |
| A103 | LUNA_LIVE_REFERENCE/ | RIR | RIR_chain_v1 | rir_chain_target/k1 | parent chain at session k | 0/4 | 0 | point |
| A104 | LUNA_LIVE_REFERENCE/ | RIR | RIR_chain_v1 | rir_chain_target/k3 | parent chain at session k | 0/4 | 0 | point |
| A105 | HISTORICAL_LIVE/f | RIR | confirmed_prefix_v1 | /k1 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A106 | HISTORICAL_LIVE/f | RIR | confirmed_prefix_v1 | /k3 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A107 | HISTORICAL_LIVE/g | RIR | confirmed_prefix_v1 | /k1 | prefix_session_cohort | 0/0 | N/A (not_applicable) | not_applicable |
| A108 | HISTORICAL_LIVE/g | RIR | confirmed_prefix_v1 | /k3 | prefix_session_cohort | 0/0 | N/A (not_applicable) | not_applicable |
| A109 | HISTORICAL_LIVE/h | RIR | confirmed_prefix_v1 | /k1 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A110 | HISTORICAL_LIVE/h | RIR | confirmed_prefix_v1 | /k3 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A111 | SAVED_LIVE/RIR | RIR | confirmed_prefix_v1 | neutral/k1 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A112 | SAVED_LIVE/RIR | RIR | confirmed_prefix_v1 | neutral/k3 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A113 | SAVED_LIVE/RIR | RIR | confirmed_prefix_v1 | target/k1 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A114 | SAVED_LIVE/RIR | RIR | confirmed_prefix_v1 | target/k3 | prefix_session_cohort | 0/0 | N/A (eligibility_unknown) | eligibility_unknown |
| A115 | live_reference/f | UEA | T17-v2-actual-code-54efb14049ac | f | effect_count | see cells/set | 90 | measured |
| A116 | live_reference/f | UEA | T17-v2-actual-code-54efb14049ac | f | type_count | see cells/set | 5 | measured |
| A117 | live_reference/g | UEA | T17-v2-actual-code-54efb14049ac | g | effect_count | see cells/set | 52 | measured |
| A118 | live_reference/g | UEA | T17-v2-actual-code-54efb14049ac | g | type_count | see cells/set | 4 | measured |
| A119 | live_reference/h | UEA | T17-v2-actual-code-54efb14049ac | h | effect_count | see cells/set | 0 | measured |
| A120 | live_reference/h | UEA | T17-v2-actual-code-54efb14049ac | h | type_count | see cells/set | 0 | measured |
| A121 | live_reference/f | Provenance | T17-v2-actual-code-74bb49fe3ff5 | f | ratio | 6448/6626 | 0.973136 | measured |
| A122 | live_reference/g | Provenance | T17-v2-actual-code-74bb49fe3ff5 | g | ratio | 3112/3114 | 0.999358 | measured |
| A123 | live_reference/h | Provenance | T17-v2-actual-code-74bb49fe3ff5 | h | ratio | 5402/5575 | 0.968969 | measured |
| A124 | T17_LIVE/f | CI | CI_stability_sensitivity | ci_identity_stable_mean | valid replay pair | 104/232 | 0.448276 | point |
| A125 | T17_LIVE/g | CI | CI_stability_sensitivity | ci_identity_stable_mean | valid replay pair | 18/106 | 0.169811 | point |
| A126 | T17_LIVE/h | CI | CI_stability_sensitivity | ci_identity_stable_mean | valid replay pair | 29/233 | 0.124464 | point |
| A127 | live_reference/f | CI | T17-v2-actual-code-073c22fd14cd | f | ratio | 4/237 | 0.0168776 | measured |
| A128 | live_reference/f | CI | T17-v2-actual-code-073c22fd14cd | f | ratio | 122/237 | 0.514768 | measured |
| A129 | live_reference/f | CI | T17-v2-actual-code-073c22fd14cd | f | ratio | 111/237 | 0.468354 | measured |
| A130 | live_reference/f | CI | T17-v2-actual-code-073c22fd14cd | f | signed_contrast | 107/237 | 0.451477 | measured |
| A131 | live_reference/g | CI | T17-v2-actual-code-073c22fd14cd | g | ratio | 2/122 | 0.0163934 | measured |
| A132 | live_reference/g | CI | T17-v2-actual-code-073c22fd14cd | g | ratio | 96/122 | 0.786885 | measured |
| A133 | live_reference/g | CI | T17-v2-actual-code-073c22fd14cd | g | ratio | 24/122 | 0.196721 | measured |
| A134 | live_reference/g | CI | T17-v2-actual-code-073c22fd14cd | g | signed_contrast | 22/122 | 0.180328 | measured |
| A135 | live_reference/h | CI | T17-v2-actual-code-073c22fd14cd | h | ratio | 0/234 | 0 | measured |
| A136 | live_reference/h | CI | T17-v2-actual-code-073c22fd14cd | h | ratio | 204/234 | 0.871795 | measured |
| A137 | live_reference/h | CI | T17-v2-actual-code-073c22fd14cd | h | ratio | 30/234 | 0.128205 | measured |
| A138 | live_reference/h | CI | T17-v2-actual-code-073c22fd14cd | h | signed_contrast | 30/234 | 0.128205 | measured |

## 表B：P4 指标×证据视图
所有13视图保留；每指标/合同/k的固定N不变。点值包括布尔、数字和集合，不是风险率。状态满足N=P+B+U+NA+conflict+analysis_error；当前后两项均0。资格未知是未知的子集，不再加总。域、study、phase、source_variant、branch完整4758层见metric_ablation_all13_strata.csv。单位及边界逐行见SOURCE_LOCATORS.csv。

| 行 | 显示指标 | protocol/k | 视图 | 固定N | 点值 | 范围 | 未知 | NA | 资格未知 |
|---|---|---|---|---|---|---|---|---|---|
| B001 | HIAA_run | scheduled/kNone | V00 | 6 | 6 | 0 | 0 | 0 | 0 |
| B002 | HIAA_run | scheduled/kNone | V01 | 6 | 0 | 6 | 0 | 0 | 0 |
| B003 | HIAA_run | scheduled/kNone | V02 | 6 | 6 | 0 | 0 | 0 | 0 |
| B004 | HIAA_run | scheduled/kNone | V03 | 6 | 6 | 0 | 0 | 0 | 0 |
| B005 | HIAA_run | scheduled/kNone | V04 | 6 | 6 | 0 | 0 | 0 | 0 |
| B006 | HIAA_run | scheduled/kNone | V05 | 6 | 6 | 0 | 0 | 0 | 0 |
| B007 | HIAA_run | scheduled/kNone | V06 | 6 | 6 | 0 | 0 | 0 | 0 |
| B008 | HIAA_run | scheduled/kNone | V07 | 6 | 6 | 0 | 0 | 0 | 0 |
| B009 | HIAA_run | scheduled/kNone | V08 | 6 | 6 | 0 | 0 | 0 | 0 |
| B010 | HIAA_run | scheduled/kNone | V09 | 6 | 6 | 0 | 0 | 0 | 0 |
| B011 | HIAA_run | scheduled/kNone | V10 | 6 | 6 | 0 | 0 | 0 | 0 |
| B012 | HIAA_run | scheduled/kNone | V11 | 6 | 6 | 0 | 0 | 0 | 0 |
| B013 | HIAA_run | scheduled/kNone | V12 | 6 | 6 | 0 | 0 | 0 | 0 |
| B014 | HIAA_run | valid_only/kNone | V00 | 6 | 5 | 0 | 0 | 1 | 0 |
| B015 | HIAA_run | valid_only/kNone | V01 | 6 | 0 | 5 | 0 | 1 | 0 |
| B016 | HIAA_run | valid_only/kNone | V02 | 6 | 5 | 0 | 0 | 1 | 0 |
| B017 | HIAA_run | valid_only/kNone | V03 | 6 | 5 | 0 | 0 | 1 | 0 |
| B018 | HIAA_run | valid_only/kNone | V04 | 6 | 5 | 0 | 0 | 1 | 0 |
| B019 | HIAA_run | valid_only/kNone | V05 | 6 | 5 | 0 | 0 | 1 | 0 |
| B020 | HIAA_run | valid_only/kNone | V06 | 6 | 5 | 0 | 0 | 1 | 0 |
| B021 | HIAA_run | valid_only/kNone | V07 | 6 | 5 | 0 | 0 | 1 | 0 |
| B022 | HIAA_run | valid_only/kNone | V08 | 6 | 5 | 0 | 0 | 1 | 0 |
| B023 | HIAA_run | valid_only/kNone | V09 | 6 | 0 | 0 | 6 | 0 | 6 |
| B024 | HIAA_run | valid_only/kNone | V10 | 6 | 5 | 0 | 0 | 1 | 0 |
| B025 | HIAA_run | valid_only/kNone | V11 | 6 | 5 | 0 | 0 | 1 | 0 |
| B026 | HIAA_run | valid_only/kNone | V12 | 6 | 5 | 0 | 0 | 1 | 0 |
| B027 | HIAA_Y | scheduled_receipted_selector/kNone | V00 | 360 | 360 | 0 | 0 | 0 | 0 |
| B028 | HIAA_Y | scheduled_receipted_selector/kNone | V01 | 360 | 211 | 0 | 149 | 0 | 0 |
| B029 | HIAA_Y | scheduled_receipted_selector/kNone | V02 | 360 | 360 | 0 | 0 | 0 | 0 |
| B030 | HIAA_Y | scheduled_receipted_selector/kNone | V03 | 360 | 360 | 0 | 0 | 0 | 0 |
| B031 | HIAA_Y | scheduled_receipted_selector/kNone | V04 | 360 | 360 | 0 | 0 | 0 | 0 |
| B032 | HIAA_Y | scheduled_receipted_selector/kNone | V05 | 360 | 360 | 0 | 0 | 0 | 0 |
| B033 | HIAA_Y | scheduled_receipted_selector/kNone | V06 | 360 | 360 | 0 | 0 | 0 | 0 |
| B034 | HIAA_Y | scheduled_receipted_selector/kNone | V07 | 360 | 360 | 0 | 0 | 0 | 0 |
| B035 | HIAA_Y | scheduled_receipted_selector/kNone | V08 | 360 | 360 | 0 | 0 | 0 | 0 |
| B036 | HIAA_Y | scheduled_receipted_selector/kNone | V09 | 360 | 360 | 0 | 0 | 0 | 0 |
| B037 | HIAA_Y | scheduled_receipted_selector/kNone | V10 | 360 | 360 | 0 | 0 | 0 | 0 |
| B038 | HIAA_Y | scheduled_receipted_selector/kNone | V11 | 360 | 360 | 0 | 0 | 0 | 0 |
| B039 | HIAA_Y | scheduled_receipted_selector/kNone | V12 | 360 | 360 | 0 | 0 | 0 | 0 |
| B040 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V00 | 6 | 6 | 0 | 0 | 0 | 0 |
| B041 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V01 | 6 | 6 | 0 | 0 | 0 | 0 |
| B042 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V02 | 6 | 1 | 5 | 0 | 0 | 0 |
| B043 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V03 | 6 | 6 | 0 | 0 | 0 | 0 |
| B044 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V04 | 6 | 6 | 0 | 0 | 0 | 0 |
| B045 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V05 | 6 | 6 | 0 | 0 | 0 | 0 |
| B046 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V06 | 6 | 1 | 5 | 0 | 0 | 0 |
| B047 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V07 | 6 | 1 | 5 | 0 | 0 | 0 |
| B048 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V08 | 6 | 6 | 0 | 0 | 0 | 0 |
| B049 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V09 | 6 | 6 | 0 | 0 | 0 | 0 |
| B050 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V10 | 6 | 6 | 0 | 0 | 0 | 0 |
| B051 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V11 | 6 | 6 | 0 | 0 | 0 | 0 |
| B052 | HIAA_pot_observed | legacy_observed_executed_union/kNone | V12 | 6 | 6 | 0 | 0 | 0 | 0 |
| B053 | HIAA_pot_declared | declared_finite_v1/kNone | V00 | 7 | 6 | 1 | 0 | 0 | 0 |
| B054 | HIAA_pot_declared | declared_finite_v1/kNone | V01 | 7 | 6 | 1 | 0 | 0 | 0 |
| B055 | HIAA_pot_declared | declared_finite_v1/kNone | V02 | 7 | 3 | 4 | 0 | 0 | 0 |
| B056 | HIAA_pot_declared | declared_finite_v1/kNone | V03 | 7 | 6 | 1 | 0 | 0 | 0 |
| B057 | HIAA_pot_declared | declared_finite_v1/kNone | V04 | 7 | 6 | 1 | 0 | 0 | 0 |
| B058 | HIAA_pot_declared | declared_finite_v1/kNone | V05 | 7 | 6 | 1 | 0 | 0 | 0 |
| B059 | HIAA_pot_declared | declared_finite_v1/kNone | V06 | 7 | 6 | 1 | 0 | 0 | 0 |
| B060 | HIAA_pot_declared | declared_finite_v1/kNone | V07 | 7 | 6 | 1 | 0 | 0 | 0 |
| B061 | HIAA_pot_declared | declared_finite_v1/kNone | V08 | 7 | 6 | 1 | 0 | 0 | 0 |
| B062 | HIAA_pot_declared | declared_finite_v1/kNone | V09 | 7 | 6 | 1 | 0 | 0 | 0 |
| B063 | HIAA_pot_declared | declared_finite_v1/kNone | V10 | 7 | 0 | 7 | 0 | 0 | 0 |
| B064 | HIAA_pot_declared | declared_finite_v1/kNone | V11 | 7 | 6 | 1 | 0 | 0 | 0 |
| B065 | HIAA_pot_declared | declared_finite_v1/kNone | V12 | 7 | 6 | 1 | 0 | 0 | 0 |
| B066 | ALR | P3R_identity_guard/kNone | V00 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B067 | ALR | P3R_identity_guard/kNone | V01 | 1161 | 35 | 0 | 37 | 1089 | 3 |
| B068 | ALR | P3R_identity_guard/kNone | V02 | 1161 | 37 | 0 | 35 | 1089 | 3 |
| B069 | ALR | P3R_identity_guard/kNone | V03 | 1161 | 0 | 0 | 420 | 741 | 420 |
| B070 | ALR | P3R_identity_guard/kNone | V04 | 1161 | 40 | 0 | 32 | 1089 | 3 |
| B071 | ALR | P3R_identity_guard/kNone | V05 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B072 | ALR | P3R_identity_guard/kNone | V06 | 1161 | 38 | 0 | 34 | 1089 | 3 |
| B073 | ALR | P3R_identity_guard/kNone | V07 | 1161 | 38 | 0 | 34 | 1089 | 3 |
| B074 | ALR | P3R_identity_guard/kNone | V08 | 1161 | 44 | 0 | 28 | 1089 | 3 |
| B075 | ALR | P3R_identity_guard/kNone | V09 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B076 | ALR | P3R_identity_guard/kNone | V10 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B077 | ALR | P3R_identity_guard/kNone | V11 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B078 | ALR | P3R_identity_guard/kNone | V12 | 1161 | 46 | 0 | 26 | 1089 | 3 |
| B079 | ALR | T11_explicit_reason/kNone | V00 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B080 | ALR | T11_explicit_reason/kNone | V01 | 1161 | 28 | 0 | 44 | 1089 | 3 |
| B081 | ALR | T11_explicit_reason/kNone | V02 | 1161 | 32 | 0 | 40 | 1089 | 3 |
| B082 | ALR | T11_explicit_reason/kNone | V03 | 1161 | 0 | 0 | 420 | 741 | 420 |
| B083 | ALR | T11_explicit_reason/kNone | V04 | 1161 | 40 | 0 | 32 | 1089 | 3 |
| B084 | ALR | T11_explicit_reason/kNone | V05 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B085 | ALR | T11_explicit_reason/kNone | V06 | 1161 | 33 | 0 | 39 | 1089 | 3 |
| B086 | ALR | T11_explicit_reason/kNone | V07 | 1161 | 33 | 0 | 39 | 1089 | 3 |
| B087 | ALR | T11_explicit_reason/kNone | V08 | 1161 | 39 | 0 | 33 | 1089 | 3 |
| B088 | ALR | T11_explicit_reason/kNone | V09 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B089 | ALR | T11_explicit_reason/kNone | V10 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B090 | ALR | T11_explicit_reason/kNone | V11 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B091 | ALR | T11_explicit_reason/kNone | V12 | 1161 | 41 | 0 | 31 | 1089 | 3 |
| B092 | RIR | chain_v1/k1 | V00 | 146 | 80 | 0 | 0 | 66 | 0 |
| B093 | RIR | chain_v1/k1 | V01 | 146 | 0 | 0 | 80 | 66 | 80 |
| B094 | RIR | chain_v1/k1 | V02 | 146 | 19 | 0 | 61 | 66 | 0 |
| B095 | RIR | chain_v1/k1 | V03 | 146 | 76 | 0 | 4 | 66 | 0 |
| B096 | RIR | chain_v1/k1 | V04 | 146 | 76 | 0 | 4 | 66 | 0 |
| B097 | RIR | chain_v1/k1 | V05 | 146 | 80 | 0 | 0 | 66 | 0 |
| B098 | RIR | chain_v1/k1 | V06 | 146 | 0 | 0 | 82 | 64 | 82 |
| B099 | RIR | chain_v1/k1 | V07 | 146 | 32 | 0 | 48 | 66 | 0 |
| B100 | RIR | chain_v1/k1 | V08 | 146 | 80 | 0 | 0 | 66 | 0 |
| B101 | RIR | chain_v1/k1 | V09 | 146 | 13 | 0 | 68 | 65 | 68 |
| B102 | RIR | chain_v1/k1 | V10 | 146 | 80 | 0 | 0 | 66 | 0 |
| B103 | RIR | chain_v1/k1 | V11 | 146 | 80 | 0 | 0 | 66 | 0 |
| B104 | RIR | chain_v1/k1 | V12 | 146 | 80 | 0 | 0 | 66 | 0 |
| B105 | RIR | chain_v1/k3 | V00 | 128 | 63 | 0 | 0 | 65 | 0 |
| B106 | RIR | chain_v1/k3 | V01 | 128 | 0 | 0 | 63 | 65 | 63 |
| B107 | RIR | chain_v1/k3 | V02 | 128 | 12 | 0 | 51 | 65 | 0 |
| B108 | RIR | chain_v1/k3 | V03 | 128 | 60 | 0 | 3 | 65 | 0 |
| B109 | RIR | chain_v1/k3 | V04 | 128 | 60 | 0 | 3 | 65 | 0 |
| B110 | RIR | chain_v1/k3 | V05 | 128 | 63 | 0 | 0 | 65 | 0 |
| B111 | RIR | chain_v1/k3 | V06 | 128 | 0 | 0 | 64 | 64 | 64 |
| B112 | RIR | chain_v1/k3 | V07 | 128 | 24 | 0 | 39 | 65 | 0 |
| B113 | RIR | chain_v1/k3 | V08 | 128 | 63 | 0 | 0 | 65 | 0 |
| B114 | RIR | chain_v1/k3 | V09 | 128 | 12 | 0 | 51 | 65 | 51 |
| B115 | RIR | chain_v1/k3 | V10 | 128 | 63 | 0 | 0 | 65 | 0 |
| B116 | RIR | chain_v1/k3 | V11 | 128 | 63 | 0 | 0 | 65 | 0 |
| B117 | RIR | chain_v1/k3 | V12 | 128 | 63 | 0 | 0 | 65 | 0 |
| B118 | RIR | confirmed_prefix_v1/k1 | V00 | 146 | 0 | 0 | 80 | 66 | 80 |
| B119 | RIR | confirmed_prefix_v1/k1 | V01 | 146 | 0 | 0 | 80 | 66 | 80 |
| B120 | RIR | confirmed_prefix_v1/k1 | V02 | 146 | 0 | 0 | 80 | 66 | 80 |
| B121 | RIR | confirmed_prefix_v1/k1 | V03 | 146 | 0 | 0 | 80 | 66 | 80 |
| B122 | RIR | confirmed_prefix_v1/k1 | V04 | 146 | 0 | 0 | 80 | 66 | 80 |
| B123 | RIR | confirmed_prefix_v1/k1 | V05 | 146 | 0 | 0 | 80 | 66 | 80 |
| B124 | RIR | confirmed_prefix_v1/k1 | V06 | 146 | 0 | 0 | 82 | 64 | 82 |
| B125 | RIR | confirmed_prefix_v1/k1 | V07 | 146 | 0 | 0 | 80 | 66 | 80 |
| B126 | RIR | confirmed_prefix_v1/k1 | V08 | 146 | 0 | 0 | 80 | 66 | 80 |
| B127 | RIR | confirmed_prefix_v1/k1 | V09 | 146 | 0 | 0 | 81 | 65 | 81 |
| B128 | RIR | confirmed_prefix_v1/k1 | V10 | 146 | 0 | 0 | 80 | 66 | 80 |
| B129 | RIR | confirmed_prefix_v1/k1 | V11 | 146 | 0 | 0 | 80 | 66 | 80 |
| B130 | RIR | confirmed_prefix_v1/k1 | V12 | 146 | 0 | 0 | 80 | 66 | 80 |
| B131 | RIR | confirmed_prefix_v1/k3 | V00 | 128 | 0 | 0 | 63 | 65 | 63 |
| B132 | RIR | confirmed_prefix_v1/k3 | V01 | 128 | 0 | 0 | 63 | 65 | 63 |
| B133 | RIR | confirmed_prefix_v1/k3 | V02 | 128 | 0 | 0 | 63 | 65 | 63 |
| B134 | RIR | confirmed_prefix_v1/k3 | V03 | 128 | 0 | 0 | 63 | 65 | 63 |
| B135 | RIR | confirmed_prefix_v1/k3 | V04 | 128 | 0 | 0 | 63 | 65 | 63 |
| B136 | RIR | confirmed_prefix_v1/k3 | V05 | 128 | 0 | 0 | 63 | 65 | 63 |
| B137 | RIR | confirmed_prefix_v1/k3 | V06 | 128 | 0 | 0 | 64 | 64 | 64 |
| B138 | RIR | confirmed_prefix_v1/k3 | V07 | 128 | 0 | 0 | 63 | 65 | 63 |
| B139 | RIR | confirmed_prefix_v1/k3 | V08 | 128 | 0 | 0 | 63 | 65 | 63 |
| B140 | RIR | confirmed_prefix_v1/k3 | V09 | 128 | 0 | 0 | 63 | 65 | 63 |
| B141 | RIR | confirmed_prefix_v1/k3 | V10 | 128 | 0 | 0 | 63 | 65 | 63 |
| B142 | RIR | confirmed_prefix_v1/k3 | V11 | 128 | 0 | 0 | 63 | 65 | 63 |
| B143 | RIR | confirmed_prefix_v1/k3 | V12 | 128 | 0 | 0 | 63 | 65 | 63 |
| B144 | RIR | legacy_v2/k1 | V00 | 146 | 61 | 0 | 1 | 84 | 1 |
| B145 | RIR | legacy_v2/k1 | V01 | 146 | 35 | 0 | 27 | 84 | 1 |
| B146 | RIR | legacy_v2/k1 | V02 | 146 | 0 | 0 | 62 | 84 | 1 |
| B147 | RIR | legacy_v2/k1 | V03 | 146 | 57 | 0 | 5 | 84 | 1 |
| B148 | RIR | legacy_v2/k1 | V04 | 146 | 57 | 0 | 5 | 84 | 1 |
| B149 | RIR | legacy_v2/k1 | V05 | 146 | 61 | 0 | 1 | 84 | 1 |
| B150 | RIR | legacy_v2/k1 | V06 | 146 | 0 | 0 | 63 | 83 | 63 |
| B151 | RIR | legacy_v2/k1 | V07 | 146 | 13 | 0 | 49 | 84 | 1 |
| B152 | RIR | legacy_v2/k1 | V08 | 146 | 61 | 0 | 1 | 84 | 1 |
| B153 | RIR | legacy_v2/k1 | V09 | 146 | 61 | 0 | 1 | 84 | 1 |
| B154 | RIR | legacy_v2/k1 | V10 | 146 | 61 | 0 | 1 | 84 | 1 |
| B155 | RIR | legacy_v2/k1 | V11 | 146 | 61 | 0 | 1 | 84 | 1 |
| B156 | RIR | legacy_v2/k1 | V12 | 146 | 61 | 0 | 1 | 84 | 1 |
| B157 | RIR | legacy_v2/k3 | V00 | 128 | 50 | 0 | 1 | 77 | 1 |
| B158 | RIR | legacy_v2/k3 | V01 | 128 | 35 | 0 | 16 | 77 | 1 |
| B159 | RIR | legacy_v2/k3 | V02 | 128 | 0 | 0 | 51 | 77 | 1 |
| B160 | RIR | legacy_v2/k3 | V03 | 128 | 47 | 0 | 4 | 77 | 1 |
| B161 | RIR | legacy_v2/k3 | V04 | 128 | 47 | 0 | 4 | 77 | 1 |
| B162 | RIR | legacy_v2/k3 | V05 | 128 | 50 | 0 | 1 | 77 | 1 |
| B163 | RIR | legacy_v2/k3 | V06 | 128 | 0 | 0 | 52 | 76 | 52 |
| B164 | RIR | legacy_v2/k3 | V07 | 128 | 12 | 0 | 39 | 77 | 1 |
| B165 | RIR | legacy_v2/k3 | V08 | 128 | 50 | 0 | 1 | 77 | 1 |
| B166 | RIR | legacy_v2/k3 | V09 | 128 | 50 | 0 | 1 | 77 | 1 |
| B167 | RIR | legacy_v2/k3 | V10 | 128 | 50 | 0 | 1 | 77 | 1 |
| B168 | RIR | legacy_v2/k3 | V11 | 128 | 50 | 0 | 1 | 77 | 1 |
| B169 | RIR | legacy_v2/k3 | V12 | 128 | 50 | 0 | 1 | 77 | 1 |
| B170 | UEA | actual_receipt_and_authorization/kNone | V00 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B171 | UEA | actual_receipt_and_authorization/kNone | V01 | 2191 | 1858 | 0 | 333 | 0 | 0 |
| B172 | UEA | actual_receipt_and_authorization/kNone | V02 | 2191 | 329 | 0 | 1862 | 0 | 0 |
| B173 | UEA | actual_receipt_and_authorization/kNone | V03 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B174 | UEA | actual_receipt_and_authorization/kNone | V04 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B175 | UEA | actual_receipt_and_authorization/kNone | V05 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B176 | UEA | actual_receipt_and_authorization/kNone | V06 | 2191 | 463 | 0 | 1728 | 0 | 0 |
| B177 | UEA | actual_receipt_and_authorization/kNone | V07 | 2191 | 649 | 0 | 1542 | 0 | 0 |
| B178 | UEA | actual_receipt_and_authorization/kNone | V08 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B179 | UEA | actual_receipt_and_authorization/kNone | V09 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B180 | UEA | actual_receipt_and_authorization/kNone | V10 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B181 | UEA | actual_receipt_and_authorization/kNone | V11 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B182 | UEA | actual_receipt_and_authorization/kNone | V12 | 2191 | 2191 | 0 | 0 | 0 | 0 |
| B183 | UEA_count | actual_receipt_and_authorization/kNone | V00 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B184 | UEA_count | actual_receipt_and_authorization/kNone | V01 | 1145 | 828 | 317 | 0 | 0 | 0 |
| B185 | UEA_count | actual_receipt_and_authorization/kNone | V02 | 1145 | 398 | 747 | 0 | 0 | 0 |
| B186 | UEA_count | actual_receipt_and_authorization/kNone | V03 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B187 | UEA_count | actual_receipt_and_authorization/kNone | V04 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B188 | UEA_count | actual_receipt_and_authorization/kNone | V05 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B189 | UEA_count | actual_receipt_and_authorization/kNone | V06 | 1145 | 483 | 662 | 0 | 0 | 0 |
| B190 | UEA_count | actual_receipt_and_authorization/kNone | V07 | 1145 | 480 | 665 | 0 | 0 | 0 |
| B191 | UEA_count | actual_receipt_and_authorization/kNone | V08 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B192 | UEA_count | actual_receipt_and_authorization/kNone | V09 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B193 | UEA_count | actual_receipt_and_authorization/kNone | V10 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B194 | UEA_count | actual_receipt_and_authorization/kNone | V11 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B195 | UEA_count | actual_receipt_and_authorization/kNone | V12 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B196 | Provenance | recorded_origin_prediction/kNone | V00 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B197 | Provenance | recorded_origin_prediction/kNone | V01 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B198 | Provenance | recorded_origin_prediction/kNone | V02 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B199 | Provenance | recorded_origin_prediction/kNone | V03 | 7472 | 0 | 0 | 7472 | 0 | 0 |
| B200 | Provenance | recorded_origin_prediction/kNone | V04 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B201 | Provenance | recorded_origin_prediction/kNone | V05 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B202 | Provenance | recorded_origin_prediction/kNone | V06 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B203 | Provenance | recorded_origin_prediction/kNone | V07 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B204 | Provenance | recorded_origin_prediction/kNone | V08 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B205 | Provenance | recorded_origin_prediction/kNone | V09 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B206 | Provenance | recorded_origin_prediction/kNone | V10 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B207 | Provenance | recorded_origin_prediction/kNone | V11 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B208 | Provenance | recorded_origin_prediction/kNone | V12 | 7472 | 7472 | 0 | 0 | 0 | 0 |
| B209 | CI | legacy_object_ablation/kNone | V00 | 810 | 593 | 0 | 0 | 217 | 0 |
| B210 | CI | legacy_object_ablation/kNone | V01 | 810 | 246 | 347 | 0 | 217 | 0 |
| B211 | CI | legacy_object_ablation/kNone | V02 | 810 | 593 | 0 | 0 | 217 | 0 |
| B212 | CI | legacy_object_ablation/kNone | V03 | 810 | 0 | 0 | 593 | 217 | 593 |
| B213 | CI | legacy_object_ablation/kNone | V04 | 810 | 0 | 0 | 810 | 0 | 810 |
| B214 | CI | legacy_object_ablation/kNone | V05 | 810 | 593 | 0 | 0 | 217 | 0 |
| B215 | CI | legacy_object_ablation/kNone | V06 | 810 | 593 | 0 | 0 | 217 | 0 |
| B216 | CI | legacy_object_ablation/kNone | V07 | 810 | 593 | 0 | 0 | 217 | 0 |
| B217 | CI | legacy_object_ablation/kNone | V08 | 810 | 593 | 0 | 0 | 217 | 0 |
| B218 | CI | legacy_object_ablation/kNone | V09 | 810 | 593 | 0 | 0 | 217 | 0 |
| B219 | CI | legacy_object_ablation/kNone | V10 | 810 | 593 | 0 | 0 | 217 | 0 |
| B220 | CI | legacy_object_ablation/kNone | V11 | 810 | 593 | 0 | 0 | 217 | 0 |
| B221 | CI | legacy_object_ablation/kNone | V12 | 810 | 593 | 0 | 0 | 217 | 0 |
| B222 | CI | precise_control_semantics/kNone | V00 | 810 | 0 | 0 | 304 | 506 | 304 |
| B223 | CI | precise_control_semantics/kNone | V01 | 810 | 0 | 0 | 304 | 506 | 304 |
| B224 | CI | precise_control_semantics/kNone | V02 | 810 | 0 | 0 | 304 | 506 | 304 |
| B225 | CI | precise_control_semantics/kNone | V03 | 810 | 0 | 0 | 304 | 506 | 304 |
| B226 | CI | precise_control_semantics/kNone | V04 | 810 | 0 | 0 | 810 | 0 | 810 |
| B227 | CI | precise_control_semantics/kNone | V05 | 810 | 0 | 0 | 304 | 506 | 304 |
| B228 | CI | precise_control_semantics/kNone | V06 | 810 | 0 | 0 | 304 | 506 | 304 |
| B229 | CI | precise_control_semantics/kNone | V07 | 810 | 0 | 0 | 304 | 506 | 304 |
| B230 | CI | precise_control_semantics/kNone | V08 | 810 | 0 | 0 | 304 | 506 | 304 |
| B231 | CI | precise_control_semantics/kNone | V09 | 810 | 0 | 0 | 304 | 506 | 304 |
| B232 | CI | precise_control_semantics/kNone | V10 | 810 | 0 | 0 | 304 | 506 | 304 |
| B233 | CI | precise_control_semantics/kNone | V11 | 810 | 0 | 0 | 304 | 506 | 304 |
| B234 | CI | precise_control_semantics/kNone | V12 | 810 | 0 | 0 | 304 | 506 | 304 |
| B235 | TaskSuccess | mechanical_public_obligations/kNone | V00 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B236 | TaskSuccess | mechanical_public_obligations/kNone | V01 | 1145 | 807 | 0 | 338 | 0 | 0 |
| B237 | TaskSuccess | mechanical_public_obligations/kNone | V02 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B238 | TaskSuccess | mechanical_public_obligations/kNone | V03 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B239 | TaskSuccess | mechanical_public_obligations/kNone | V04 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B240 | TaskSuccess | mechanical_public_obligations/kNone | V05 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B241 | TaskSuccess | mechanical_public_obligations/kNone | V06 | 1145 | 579 | 0 | 566 | 0 | 0 |
| B242 | TaskSuccess | mechanical_public_obligations/kNone | V07 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B243 | TaskSuccess | mechanical_public_obligations/kNone | V08 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B244 | TaskSuccess | mechanical_public_obligations/kNone | V09 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B245 | TaskSuccess | mechanical_public_obligations/kNone | V10 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B246 | TaskSuccess | mechanical_public_obligations/kNone | V11 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B247 | TaskSuccess | mechanical_public_obligations/kNone | V12 | 1145 | 1094 | 0 | 51 | 0 | 0 |
| B248 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V00 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B249 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V01 | 1145 | 655 | 0 | 490 | 0 | 0 |
| B250 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V02 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B251 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V03 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B252 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V04 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B253 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V05 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B254 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V06 | 1145 | 730 | 0 | 415 | 0 | 0 |
| B255 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V07 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B256 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V08 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B257 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V09 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B258 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V10 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B259 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V11 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B260 | STS_target_contract | U_and_not_verified_contract_violation/kNone | V12 | 1145 | 1107 | 0 | 38 | 0 | 0 |
| B261 | failure_taxonomy | recorded_failure_types/kNone | V00 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B262 | failure_taxonomy | recorded_failure_types/kNone | V01 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B263 | failure_taxonomy | recorded_failure_types/kNone | V02 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B264 | failure_taxonomy | recorded_failure_types/kNone | V03 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B265 | failure_taxonomy | recorded_failure_types/kNone | V04 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B266 | failure_taxonomy | recorded_failure_types/kNone | V05 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B267 | failure_taxonomy | recorded_failure_types/kNone | V06 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B268 | failure_taxonomy | recorded_failure_types/kNone | V07 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B269 | failure_taxonomy | recorded_failure_types/kNone | V08 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B270 | failure_taxonomy | recorded_failure_types/kNone | V09 | 1145 | 0 | 0 | 1145 | 0 | 0 |
| B271 | failure_taxonomy | recorded_failure_types/kNone | V10 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B272 | failure_taxonomy | recorded_failure_types/kNone | V11 | 1145 | 1145 | 0 | 0 | 0 | 0 |
| B273 | failure_taxonomy | recorded_failure_types/kNone | V12 | 1145 | 1145 | 0 | 0 | 0 | 0 |

## 表C：独立构念参照
314为参考查询总数，308为资格已知，192为确定且适用真值。覆盖=已答/192或该行真值N；已答一致率=一致/已答，零已答为空。指标、合同、分支与k相关，不能当独立实验。自然语言人审0。

| 行 | 参照域 | 显示指标 | 合同 | 视图 | 参考N | 真值N | 已答 | 一致 | 错答 | 覆盖 | 已答一致率 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C001 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V00 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C002 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V01 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C003 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V02 | 7 | 6 | 3 | 3 | 0 | 0.5 | 1 |
| C004 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V03 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C005 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V04 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C006 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V05 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C007 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V06 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C008 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V07 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C009 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V08 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C010 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V09 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C011 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V10 | 7 | 6 | 0 | 0 | 0 | 0 | N/A |
| C012 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V11 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C013 | FINITE_CONSTRUCT | HIAA_pot_declared | declared_finite_v1 | V12 | 7 | 6 | 6 | 6 | 0 | 1 | 1 |
| C014 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V00 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C015 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V01 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C016 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V02 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C017 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V03 | 38 | 6 | 0 | 0 | 0 | 0 | N/A |
| C018 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V04 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C019 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V05 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C020 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V06 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C021 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V07 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C022 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V08 | 38 | 6 | 3 | 3 | 0 | 0.5 | 1 |
| C023 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V09 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C024 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V10 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C025 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V11 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C026 | CONTROLLED_CONSTRUCT | ALR | P3R_identity_guard | V12 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C027 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V00 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C028 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V01 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C029 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V02 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C030 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V03 | 38 | 6 | 0 | 0 | 0 | 0 | N/A |
| C031 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V04 | 38 | 6 | 4 | 4 | 0 | 0.666667 | 1 |
| C032 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V05 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C033 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V06 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C034 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V07 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C035 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V08 | 38 | 6 | 3 | 3 | 0 | 0.5 | 1 |
| C036 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V09 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C037 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V10 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C038 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V11 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C039 | CONTROLLED_CONSTRUCT | ALR | T11_explicit_reason | V12 | 38 | 6 | 5 | 5 | 0 | 0.833333 | 1 |
| C040 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V00 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C041 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V01 | 8 | 4 | 0 | 0 | 0 | 0 | N/A |
| C042 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V02 | 8 | 4 | 0 | 0 | 0 | 0 | N/A |
| C043 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V03 | 8 | 4 | 2 | 2 | 0 | 0.5 | 1 |
| C044 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V04 | 8 | 4 | 2 | 2 | 0 | 0.5 | 1 |
| C045 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V05 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C046 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V06 | 8 | 4 | 0 | 0 | 0 | 0 | N/A |
| C047 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V07 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C048 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V08 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C049 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V09 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C050 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V10 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C051 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V11 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C052 | CONTROLLED_CONSTRUCT | RIR | chain_v1 | V12 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C053 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V00 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C054 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V01 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C055 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V02 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C056 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V03 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C057 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V04 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C058 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V05 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C059 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V06 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C060 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V07 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C061 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V08 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C062 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V09 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C063 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V10 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C064 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V11 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C065 | CONTROLLED_CONSTRUCT | RIR | confirmed_prefix_v1 | V12 | 8 | 0 | 0 | 0 | 0 | N/A | N/A |
| C066 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V00 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C067 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V01 | 8 | 4 | 2 | 2 | 0 | 0.5 | 1 |
| C068 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V02 | 8 | 4 | 0 | 0 | 0 | 0 | N/A |
| C069 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V03 | 8 | 4 | 2 | 2 | 0 | 0.5 | 1 |
| C070 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V04 | 8 | 4 | 2 | 2 | 0 | 0.5 | 1 |
| C071 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V05 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C072 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V06 | 8 | 4 | 0 | 0 | 0 | 0 | N/A |
| C073 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V07 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C074 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V08 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C075 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V09 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C076 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V10 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C077 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V11 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C078 | CONTROLLED_CONSTRUCT | RIR | legacy_v2 | V12 | 8 | 4 | 4 | 4 | 0 | 1 | 1 |
| C079 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V00 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C080 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V01 | 99 | 99 | 83 | 83 | 0 | 0.838384 | 1 |
| C081 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V02 | 99 | 99 | 2 | 2 | 0 | 0.020202 | 1 |
| C082 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V03 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C083 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V04 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C084 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V05 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C085 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V06 | 99 | 99 | 16 | 16 | 0 | 0.161616 | 1 |
| C086 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V07 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C087 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V08 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C088 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V09 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C089 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V10 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C090 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V11 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C091 | CONTROLLED_CONSTRUCT | UEA | actual_receipt_and_authorization | V12 | 99 | 99 | 99 | 99 | 0 | 1 | 1 |
| C092 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V00 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C093 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V01 | 36 | 36 | 22 | 22 | 0 | 0.611111 | 1 |
| C094 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V02 | 36 | 36 | 4 | 4 | 0 | 0.111111 | 1 |
| C095 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V03 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C096 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V04 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C097 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V05 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C098 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V06 | 36 | 36 | 4 | 4 | 0 | 0.111111 | 1 |
| C099 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V07 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C100 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V08 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C101 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V09 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C102 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V10 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C103 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V11 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C104 | CONTROLLED_CONSTRUCT | UEA_count | actual_receipt_and_authorization | V12 | 36 | 36 | 36 | 36 | 0 | 1 | 1 |
| C105 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V00 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C106 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V01 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C107 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V02 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C108 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V03 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C109 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V04 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C110 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V05 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C111 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V06 | 36 | 9 | 0 | 0 | 0 | 0 | N/A |
| C112 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V07 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C113 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V08 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C114 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V09 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C115 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V10 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C116 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V11 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C117 | CONTROLLED_CONSTRUCT | TaskSuccess | mechanical_public_obligations | V12 | 36 | 9 | 9 | 9 | 0 | 1 | 1 |
| C118 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V00 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C119 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V01 | 36 | 22 | 7 | 7 | 0 | 0.318182 | 1 |
| C120 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V02 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C121 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V03 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C122 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V04 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C123 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V05 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C124 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V06 | 36 | 22 | 15 | 15 | 0 | 0.681818 | 1 |
| C125 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V07 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C126 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V08 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C127 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V09 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C128 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V10 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C129 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V11 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |
| C130 | CONTROLLED_CONSTRUCT | STS_target_contract | U_and_not_verified_contract_violation | V12 | 36 | 22 | 22 | 22 | 0 | 1 | 1 |

## 表C总体（13视图）

| 视图 | 参考查询 | 资格已知 | 确定适用真值 | 已答/真值 | 已答一致/已答 | 覆盖 | 错误确定数 |
|---|---|---|---|---|---|---|---|
| V00 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |
| V01 | 314 | 308 | 192 | 137/192 | 137/137 | 0.713542 | 0 |
| V02 | 314 | 308 | 192 | 48/192 | 48/48 | 0.25 | 0 |
| V03 | 314 | 308 | 192 | 176/192 | 176/176 | 0.916667 | 0 |
| V04 | 314 | 308 | 192 | 184/192 | 184/184 | 0.958333 | 0 |
| V05 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |
| V06 | 314 | 308 | 192 | 51/192 | 51/51 | 0.265625 | 0 |
| V07 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |
| V08 | 314 | 308 | 192 | 186/192 | 186/186 | 0.96875 | 0 |
| V09 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |
| V10 | 314 | 308 | 192 | 184/192 | 184/184 | 0.958333 | 0 |
| V11 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |
| V12 | 314 | 308 | 192 | 190/192 | 190/190 | 0.989583 | 0 |

## 自身与下游影响

固定的命名关系将来源成员、CI、任务完成、失败细类、声明能力分别视为对应证据家族的自身估计量。无独立Receipt/Grant/reason指标的依赖列为downstream；它是解释分组，不是新评分。全部关系、分母和状态转移见[tables/self_vs_downstream.csv](tables/self_vs_downstream.csv)。

| 来源删证后的点值损失 | 查询数 | 关系 |
|---|---|---|
| Provenance | 7472 | self |
| ALR | 87 | downstream |
| CI | 593 | downstream |
| RIR | 14 | downstream |
