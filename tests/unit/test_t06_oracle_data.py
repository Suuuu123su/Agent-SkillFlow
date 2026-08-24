from datetime import UTC, datetime

import pytest

from skillflow.models.enums import CapabilityAction
from skillflow.models.resources import ResourceRef
from skillflow.models.scenario_parts import AssetSpec
from skillflow.models.tool_calls import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    WriteMemoryArgs,
)
from skillflow.oracle.effects import oracle_action_semantics
from skillflow.oracle.models import (
    OracleActionPlan,
    OracleAttemptEvidence,
    OracleReceiptEvidence,
)
from skillflow.oracle.state import OracleDataState
from skillflow.trace.contracts import ParentRelation

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ToolArguments = ReadFileArgs | WriteMemoryArgs | ReadMemoryArgs | HttpSendArgs | ShellExecArgs


def attempt_from(receipt: OracleReceiptEvidence) -> OracleAttemptEvidence:
    return OracleAttemptEvidence(
        action_id=receipt.action_id,
        actor_id=receipt.actor_id,
        call_id=receipt.call_id,
        tool=receipt.tool,
        argument_artifact_id=receipt.argument_artifact_id,
        executed=True,
    )


@pytest.mark.parametrize(
    ("arguments", "action", "source", "sink", "source_ids"),
    [
        (
            ReadFileArgs(resource=ResourceRef("workspace:/documents/report.txt")),
            CapabilityAction.FILE_READ,
            ResourceRef("workspace:/documents/report.txt"),
            ResourceRef("context:/task"),
            (),
        ),
        (
            WriteMemoryArgs(
                key="shared",
                source_artifact_id="artifact-1",
                source=ResourceRef("context:/task"),
            ),
            CapabilityAction.MEMORY_WRITE,
            ResourceRef("context:/task"),
            ResourceRef("memory:/shared"),
            ("artifact-1",),
        ),
        (
            ReadMemoryArgs(key="shared"),
            CapabilityAction.MEMORY_READ,
            ResourceRef("memory:/shared"),
            ResourceRef("context:/task"),
            (),
        ),
        (
            HttpSendArgs(
                source_artifact_id="artifact-1",
                source=ResourceRef("context:/task"),
                sink=ResourceRef("mock://external"),
            ),
            CapabilityAction.NETWORK_SEND,
            ResourceRef("context:/task"),
            ResourceRef("mock://external"),
            ("artifact-1",),
        ),
        (
            ShellExecArgs(command=("safe-fixture",)),
            CapabilityAction.SHELL_EXECUTE,
            None,
            ResourceRef("mock://shell"),
            (),
        ),
    ],
)
def test_oracle_mechanically_normalizes_every_scripted_tool_action(
    arguments: ToolArguments,
    action: CapabilityAction,
    source: ResourceRef | None,
    sink: ResourceRef,
    source_ids: tuple[str, ...],
) -> None:
    # When: 独立 Oracle 解释封闭脚本动作
    semantics = oracle_action_semantics(arguments)

    # Then: 不调用 Observed ToolProxy 也能得到确定 Effect 和数据父 ID
    assert semantics.effect.action is action
    assert semantics.effect.source == source
    assert semantics.effect.sink == sink
    assert semantics.source_artifact_ids == source_ids


def test_trace_parent_relations_are_closed_and_stable() -> None:
    assert {relation.value for relation in ParentRelation} == {
        "copy",
        "derive",
        "write",
        "load",
        "invoke",
    }


def test_oracle_memory_write_and_load_preserve_independent_data_lineage() -> None:
    # Given: 一个 Scenario asset 已被 read_file 机械绑定为稳定 Artifact
    state = OracleDataState(
        "run-1",
        (
            AssetSpec(
                id="report",
                uri=ResourceRef("fixture://documents/report.txt"),
                trust="user",
            ),
        ),
    )
    read_action = OracleActionPlan(
        "read-report",
        ReadFileArgs(resource=ResourceRef("workspace:/documents/report.txt")),
    )
    read_receipt = OracleReceiptEvidence(
        action_id="read-report",
        receipt_id="receipt-read",
        effect_id="effect-read",
        actor_id="skill-a",
        call_id="call-1",
        timestamp=NOW,
        tool=read_action.arguments.kind,
        argument_artifact_id="argument-read",
        receipt_artifact_id="receipt-artifact-read",
        output_artifact_ids=("file-1",),
    )
    read_semantics = oracle_action_semantics(read_action.arguments)
    state.record_argument("skill-a", read_semantics, attempt_from(read_receipt))
    state.record_outputs(read_action, read_receipt)

    # When: 同一真实值依次写入并读取 Persistent Memory
    write_action = OracleActionPlan(
        "write-shared",
        WriteMemoryArgs(
            key="shared",
            source_artifact_id="file-1",
            source=ResourceRef("workspace:/documents/report.txt"),
        ),
    )
    write_receipt = OracleReceiptEvidence(
        action_id="write-shared",
        receipt_id="receipt-write",
        effect_id="effect-write",
        actor_id="skill-a",
        call_id="call-1",
        timestamp=NOW,
        tool=write_action.arguments.kind,
        argument_artifact_id="argument-write",
        receipt_artifact_id="receipt-artifact-write",
        output_artifact_ids=("memory-1",),
    )
    state.record_argument(
        "skill-a",
        oracle_action_semantics(write_action.arguments),
        attempt_from(write_receipt),
    )
    state.record_outputs(write_action, write_receipt)
    load_action = OracleActionPlan("load-shared", ReadMemoryArgs(key="shared"))
    load_receipt = OracleReceiptEvidence(
        action_id="load-shared",
        receipt_id="receipt-load",
        effect_id="effect-load",
        actor_id="skill-a",
        call_id="call-2",
        timestamp=NOW,
        tool=load_action.arguments.kind,
        argument_artifact_id="argument-load",
        receipt_artifact_id="receipt-artifact-load",
        output_artifact_ids=("memory-2",),
    )
    state.record_argument(
        "skill-a",
        oracle_action_semantics(load_action.arguments),
        attempt_from(load_receipt),
    )
    state.record_outputs(load_action, load_receipt)

    # Then: WRITE/LOAD 父边和 asset 来源均不依赖 Observed label
    written = state.require("memory-1")
    loaded = state.require("memory-2")
    assert tuple(parent.model_dump(mode="json") for parent in written.parents) == (
        {"parent_id": "file-1", "relation": "write"},
    )
    assert tuple(parent.model_dump(mode="json") for parent in loaded.parents) == (
        {"parent_id": "memory-1", "relation": "load"},
    )
    assert written.gt_data == loaded.gt_data == ("workspace:/documents/report.txt",)
