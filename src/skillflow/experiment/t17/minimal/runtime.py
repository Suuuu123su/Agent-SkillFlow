"""最小实验的明确执行域与无网络 Fake 决策日志。"""

import time
from dataclasses import dataclass, field

from skillflow.adapters.mock_harness import MockHarnessAdapter
from skillflow.benchmark.harness_factory import HarnessFactorySetup, create_scenario_harness
from skillflow.experiment.t17.minimal.run_models import FakeDecisionRecord, MinimalDomain
from skillflow.experiment.t17.reference_backend import (
    FakeReferenceModelClient,
    ReferenceModelDecision,
    ReferenceModelRequest,
)
from skillflow.experiment.t17.reference_harness import ReferenceHarnessFactory


class RecordingFakeClient:
    """只包装固定无 I/O Fake；不接受真实 Provider 或凭据。"""

    def __init__(self, client: FakeReferenceModelClient) -> None:
        """保留完整决策分类，不保存输入输出正文。"""
        self._client = client
        self.records: list[FakeDecisionRecord] = []

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """记录是否发起允许动作；空动作目录不算 no-call。"""
        result = self._client.decide(request)
        self.records.append(
            FakeDecisionRecord(
                sequence=len(self.records) + 1,
                allowed_action_ids=request.allowed_action_ids,
                selected_action_ids=result.selected_action_ids,
                behavior="no_call"
                if request.allowed_action_ids and not result.selected_action_ids
                else "normal",
                schema_valid=True,
            )
        )
        return result


@dataclass(slots=True)
class RunTelemetry:
    """单 Run 的计时与零费用决策事实。"""

    started_ns: int
    client: RecordingFakeClient | None = None


@dataclass(slots=True)
class MinimalHarnessFactory:
    """共享同一受信 Runtime；只有决策驱动域不同。"""

    domain: MinimalDomain
    telemetry: dict[str, RunTelemetry] = field(default_factory=dict)

    def __call__(self, setup: HarnessFactorySetup) -> MockHarnessAdapter:
        """每个 core/source/replay 分支均创建独立 Fake 状态。"""
        telemetry = RunTelemetry(time.perf_counter_ns())
        self.telemetry[setup.run_id] = telemetry
        if self.domain == "scripted":
            return create_scenario_harness(setup)
        client = RecordingFakeClient(
            FakeReferenceModelClient(
                {
                    root: ReferenceModelDecision(
                        selected_action_ids=tuple(item.action_id for item in script.actions),
                        output_text=script.output.decode(),
                        output_mime_type=script.output_mime_type,
                    )
                    for root, script in setup.scripts.items()
                }
            )
        )
        telemetry.client = client
        return ReferenceHarnessFactory(client)(setup)
