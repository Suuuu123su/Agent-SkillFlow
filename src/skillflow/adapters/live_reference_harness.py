"""真实模型决策与 SkillFlow 受信 Runtime 组合的 Reference Harness。"""

from skillflow.adapters.mock_harness import MockHarnessAdapter


class LiveReferenceHarnessAdapter(MockHarnessAdapter):
    """复用完整插桩状态，只替换 Skill 决策后端。"""
