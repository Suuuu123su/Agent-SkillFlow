"""反事实配对的纯计算规则。"""


def compute_scripted_ci(original: bool, neutral: bool) -> int:
    """按任务书定义计算单次 Scripted 配对的有符号 CI。"""
    return int(original) - int(neutral)
