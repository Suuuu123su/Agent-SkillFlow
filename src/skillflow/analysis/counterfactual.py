"""反事实配对的纯计算规则。"""

from typing import Literal


def compute_scripted_ci(original: bool, neutral: bool) -> Literal[-1, 0, 1]:
    """按任务书定义计算单次 Scripted 配对的有符号 CI。"""
    difference = int(original) - int(neutral)
    if difference == -1:
        return -1
    if difference == 1:
        return 1
    return 0
