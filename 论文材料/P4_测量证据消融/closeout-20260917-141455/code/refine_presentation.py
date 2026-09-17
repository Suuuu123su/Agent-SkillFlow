from common import *
p=OUT/'code/common.py';s=p.read_text(encoding='utf-8');s=s.replace("ROOT=OUT.parents[2]", "ROOT=next((p for p in OUT.parents if (p/'AGENTS.md').is_file() and (p/'src/skillflow').is_dir()),OUT)");p.write_text(s,encoding='utf-8')
p=OUT/'code/render_tables.py';s=p.read_text(encoding='utf-8').replace('../p4-20260917-123623/../..//P3_机制测量','../../P3_机制测量').replace('不是两个独立实验，也没有可回填的历史reason。','不是两个独立实验；不得把独立参照保有的原因回填许可视图。这是既有受控遮蔽，不是自然历史遗失。');p.write_text(s,encoding='utf-8')
