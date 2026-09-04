"""请求前冻结第二版全部输入、格式和阶段合同。"""

from pathlib import Path
from typing import Literal

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.frozen import FrozenFile, inside, verify_files
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.prompt_contract import PromptContract
from skillflow.experiment.t17.v2.run_models import PhaseContract
from skillflow.experiment.t17.v2.schema_models import verify_v2_schemas, write_v2_schemas
from skillflow.experiment.t17.v2.stage_contract import freeze_phase
from skillflow.experiment.t17.v2.unit_execution import file_inventory
from skillflow.models.base import NonEmptyStr, StrictModel


class ProtocolManifest(StrictModel):
    """独立版本目录的不可变文件清单，不授予付费调用权限。"""

    schema_version: Literal["2.0"] = "2.0"
    protocol_id: NonEmptyStr
    configuration_sha256: NonEmptyStr
    files: dict[NonEmptyStr, FrozenFile]
    paid_calls_authorized: Literal[False] = False


def freeze_protocol(
    root: Path, output: Path, configuration: Path | None = None
) -> ProtocolManifest:
    """默认生成完整 T17；也允许从已登记的匹配技能目录机械展开。"""
    root = root.resolve()
    output = inside(root, output.resolve().relative_to(root).as_posix())
    if configuration is None:
        config, bundles = build_configuration(root, output)
    else:
        config, bundles = read_model(configuration, V2Configuration), {}
    write_configuration(root, output, config, bundles)
    for stage in T17LiveStage:
        matrix = build_matrix(root, config, stage)
        write_checked_json(output / ("matrix-" + stage.value + ".json"), matrix)
        write_checked_json(
            output / ("phase-" + stage.value + ".json"),
            freeze_phase(root, config, matrix, "live_reference"),
        )
    write_checked_json(output / "prompt-contract.json", PromptContract())
    write_v2_schemas(output / "schemas")
    manifest = ProtocolManifest(
        protocol_id=config.protocol_id,
        configuration_sha256=model_digest(config),
        files=file_inventory(output, output),
    )
    write_checked_json(output / "protocol-manifest.json", manifest)
    return manifest


def verify_protocol(root: Path, output: Path) -> tuple[V2Configuration, tuple[V2Matrix, ...]]:
    """只读检查真实文件、提示、格式、运行代码和五个阶段调度。"""
    manifest = read_model(output / "protocol-manifest.json", ProtocolManifest)
    verify_files(output, manifest.files)
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(manifest.files) | {"protocol-manifest.json"}:
        raise ValueError("v2_static_protocol_file_set")
    verify_v2_schemas(output / "schemas")
    config = read_model(output / "preregistration.json", V2Configuration)
    if model_digest(config) != manifest.configuration_sha256:
        raise ValueError("v2_static_configuration_binding")
    if read_model(output / "prompt-contract.json", PromptContract) != PromptContract():
        raise ValueError("v2_static_prompt_drift")
    matrices = []
    for stage in T17LiveStage:
        matrix = read_model(output / ("matrix-" + stage.value + ".json"), V2Matrix)
        phase = read_model(output / ("phase-" + stage.value + ".json"), PhaseContract)
        if matrix != build_matrix(root, config, stage) or phase != freeze_phase(
            root, config, matrix, "live_reference"
        ):
            raise ValueError("v2_static_matrix_or_runtime_drift")
        matrices.append(matrix)
    return config, tuple(matrices)
