import sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UP=Path('<WORKSPACE>/ClawTrojan-openai-luna-evidence-v3-39/upstream')
sys.path.insert(0,str(UP))
# Avoid eager imports of unrelated training and detector stacks in package __init__.
for name in ['agent_eval','agent_eval.sandbox']:
    mod=types.ModuleType(name); mod.__path__=[str(UP.joinpath(*name.split('.')))]; sys.modules[name]=mod
from claw_trojan.loader import load_all_trojan_envs
from agent_eval.sandbox.sandbox_eval import SandboxEvaluator
from agent_eval.sandbox.config_builder import build_sandbox_config
if __name__=='__main__':
    a=load_all_trojan_envs(str(UP/'claw_trojan'/'envs'))
    ids=sorted({s.sample_id for s in a if s.is_malicious})
    first=ids[0]
    selected=sorted([s for s in a if s.sample_id==first and s.is_malicious],key=lambda s:s.step_idx)
    clean=sorted([s for s in a if not s.is_malicious and s.sample_id not in ids and (s.outcome_category=='none' or s.attack_type=='none')],key=lambda s:s.eval_id)
    import json
    print(json.dumps({'all_steps':len(a),'first_malicious_sample':first,'selected':[s.eval_id for s in selected],'first_clean':clean[0].eval_id if clean else None}))
