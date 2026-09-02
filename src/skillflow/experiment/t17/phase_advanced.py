"""T17 HIAA、ALR 与 RIR 的必需可测状态。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.models.reports import ExperimentRiskReport

EXPECTED_HIAA_DESIGNS = 2


def advanced_metric_statuses(
    standard: ExperimentRiskReport,
) -> dict[str, MeasurementStatus]:
    """要求两套 HIAA_run/pot 与 ALR、RIR(1/3) 都有数值。"""
    statuses = {
        f"hiaa_run:{item.design_id}": (
            MeasurementStatus.MEASURED
            if item.hiaa_run.value is not None
            else MeasurementStatus.NOT_AVAILABLE
        )
        for item in standard.hiaa_designs
    }
    statuses.update(
        {f"hiaa_pot:{item.design_id}": MeasurementStatus.MEASURED for item in standard.hiaa_designs}
    )
    if len(standard.hiaa_designs) != EXPECTED_HIAA_DESIGNS:
        statuses["hiaa_designs"] = MeasurementStatus.NOT_AVAILABLE
    statuses.update(
        {
            "alr": (
                MeasurementStatus.MEASURED
                if standard.alr.value is not None
                else MeasurementStatus.NOT_AVAILABLE
            ),
            "rir_1": (
                MeasurementStatus.MEASURED
                if standard.rir_1.value is not None
                else MeasurementStatus.NOT_AVAILABLE
            ),
            "rir_3": (
                MeasurementStatus.MEASURED
                if standard.rir_3.value is not None
                else MeasurementStatus.NOT_AVAILABLE
            ),
        }
    )
    return statuses
