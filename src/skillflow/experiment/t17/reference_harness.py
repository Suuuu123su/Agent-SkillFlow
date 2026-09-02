"""Reference Harness 的可注入工厂。"""

from dataclasses import dataclass

from skillflow.adapters.live_reference_harness import LiveReferenceHarnessAdapter
from skillflow.adapters.mock_harness import MockHarnessAdapter
from skillflow.benchmark.harness_factory import (
    HarnessFactorySetup,
    create_harness_with_backend,
)
from skillflow.experiment.t17.reference_backend import (
    ReferenceModelBackend,
    ReferenceModelClient,
    ReferenceRunContext,
)


@dataclass(frozen=True, slots=True)
class ReferenceHarnessFactory:
    """为每个 Run 创建独立 Reference Backend 与 Instrumented Harness。"""

    client: ReferenceModelClient
    task_prompt_override: str | None = None

    def __call__(self, setup: HarnessFactorySetup) -> MockHarnessAdapter:
        """复用当前 Run 的预注册 Fixture 动作目录。"""
        return create_harness_with_backend(
            setup,
            ReferenceModelBackend(
                setup.scripts,
                self.client,
                ReferenceRunContext(
                    setup.scenario.id,
                    self.task_prompt_override or setup.scenario.task.prompt,
                ),
            ),
            LiveReferenceHarnessAdapter,
        )
