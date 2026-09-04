"""纯本地的封闭动作选择，用于执行链验证，不产生真实模型结果。"""

from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest


class V2FakeClient:
    """两种固定选择都不连接网络，也不生成授权或安全判定。"""

    def __init__(self, request_all: bool = True) -> None:
        """选择全部或不选动作，工具执行仍由可信运行环境控制。"""
        self.request_all = request_all

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """只返回普通文本和合法动作编号。"""
        return ReferenceModelDecision(
            selected_action_ids=request.allowed_action_ids if self.request_all else (),
            output_text=request.expected_output_text,
        )
