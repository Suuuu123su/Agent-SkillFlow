"""Artifact 类白名单断言的确定性检查器。"""

from dataclasses import dataclass, replace
from typing import assert_never

from skillflow.experiment.t16.task_success_assertions import (
    ArtifactAliasResolvesAssertion,
    ArtifactContentCommitmentMatchesAssertion,
    ArtifactExistsAssertion,
    ArtifactSchemaValidAssertion,
    ArtifactStructuredFieldEqualsAssertion,
    ArtifactStructuredSetEqualsAssertion,
)
from skillflow.experiment.t16.task_success_evidence import (
    AssertionStatus,
    EvidenceReason,
    EvidenceSource,
)
from skillflow.experiment.t16.task_success_facts import (
    PlatformArtifactRecord,
    PlatformEvidenceSnapshot,
)
from skillflow.experiment.t16.task_success_observations import AssertionObservation

ArtifactAssertion = (
    ArtifactExistsAssertion
    | ArtifactAliasResolvesAssertion
    | ArtifactSchemaValidAssertion
    | ArtifactStructuredFieldEqualsAssertion
    | ArtifactStructuredSetEqualsAssertion
    | ArtifactContentCommitmentMatchesAssertion
)


@dataclass(frozen=True, slots=True)
class CommitmentExpectation:
    """一次 commitment 比较的期望值与失败原因。"""

    expected: str
    missing_reason: EvidenceReason
    mismatch_reason: EvidenceReason


def check_artifact_assertion(
    assertion: ArtifactAssertion,
    snapshot: PlatformEvidenceSnapshot,
) -> AssertionObservation:
    """按已解析的封闭断言类型检查平台 Artifact registry。"""
    alias = assertion.artifact_alias
    if not snapshot.artifact_registry_available:
        return AssertionObservation(
            AssertionStatus.NOT_EVALUABLE,
            EvidenceSource.PLATFORM_ARTIFACT_REGISTRY,
            EvidenceReason.ARTIFACT_REGISTRY_UNAVAILABLE,
            artifact_alias=alias,
        )
    artifact = _find_artifact(snapshot, alias)
    if artifact is None:
        match assertion:
            case ArtifactAliasResolvesAssertion():
                reason = EvidenceReason.ALIAS_NOT_RESOLVED
            case (
                ArtifactExistsAssertion()
                | ArtifactSchemaValidAssertion()
                | ArtifactStructuredFieldEqualsAssertion()
                | ArtifactStructuredSetEqualsAssertion()
                | ArtifactContentCommitmentMatchesAssertion()
            ):
                reason = EvidenceReason.ARTIFACT_MISSING
            case unreachable:
                assert_never(unreachable)
        return AssertionObservation(
            AssertionStatus.FAILED,
            EvidenceSource.PLATFORM_ARTIFACT_REGISTRY,
            reason,
            artifact_alias=alias,
        )
    common = _artifact_observation(artifact)
    match assertion:
        case ArtifactExistsAssertion() | ArtifactAliasResolvesAssertion():
            observation = common
        case ArtifactSchemaValidAssertion(schema_id=schema_id):
            observation = _match(
                common,
                schema_id in artifact.valid_schema_ids,
                EvidenceReason.SCHEMA_NOT_VALID,
            )
        case ArtifactStructuredFieldEqualsAssertion(
            field_path=field_path,
            expected_value_commitment_sha256=expected,
        ):
            observation = _match_commitment(
                common,
                artifact.structured_field_commitments.get(".".join(field_path)),
                CommitmentExpectation(
                    expected=expected,
                    missing_reason=EvidenceReason.STRUCTURED_FIELD_MISSING,
                    mismatch_reason=EvidenceReason.STRUCTURED_FIELD_MISMATCH,
                ),
            )
        case ArtifactStructuredSetEqualsAssertion(
            field_path=field_path,
            expected_value_commitment_sha256=expected,
        ):
            observation = _match_commitment(
                common,
                artifact.structured_set_commitments.get(".".join(field_path)),
                CommitmentExpectation(
                    expected=expected,
                    missing_reason=EvidenceReason.STRUCTURED_SET_MISSING,
                    mismatch_reason=EvidenceReason.STRUCTURED_SET_MISMATCH,
                ),
            )
        case ArtifactContentCommitmentMatchesAssertion(
            expected_value_commitment_sha256=expected,
        ):
            observation = _match_commitment(
                common,
                artifact.artifact_content_sha256,
                CommitmentExpectation(
                    expected=expected,
                    missing_reason=EvidenceReason.ARTIFACT_MISSING,
                    mismatch_reason=EvidenceReason.CONTENT_COMMITMENT_MISMATCH,
                ),
            )
        case unreachable:
            assert_never(unreachable)
    return observation


def _find_artifact(
    snapshot: PlatformEvidenceSnapshot,
    alias: str,
) -> PlatformArtifactRecord | None:
    return next((item for item in snapshot.artifacts if item.artifact_alias == alias), None)


def _artifact_observation(artifact: PlatformArtifactRecord) -> AssertionObservation:
    return AssertionObservation(
        AssertionStatus.PASSED,
        EvidenceSource.PLATFORM_ARTIFACT_REGISTRY,
        EvidenceReason.ASSERTION_PASSED,
        session_id=artifact.session_id,
        artifact_id=artifact.artifact_id,
        artifact_alias=artifact.artifact_alias,
        artifact_content_sha256=artifact.artifact_content_sha256,
    )


def _match(
    common: AssertionObservation,
    matches: bool,
    failure: EvidenceReason,
) -> AssertionObservation:
    if matches:
        return common
    return replace(common, status=AssertionStatus.FAILED, reason=failure)


def _match_commitment(
    common: AssertionObservation,
    observed: str | None,
    expectation: CommitmentExpectation,
) -> AssertionObservation:
    reason = (
        EvidenceReason.ASSERTION_PASSED
        if observed == expectation.expected
        else expectation.mismatch_reason
    )
    if observed is None:
        reason = expectation.missing_reason
    return AssertionObservation(
        status=(
            AssertionStatus.PASSED if observed == expectation.expected else AssertionStatus.FAILED
        ),
        source=common.source,
        reason=reason,
        session_id=common.session_id,
        artifact_id=common.artifact_id,
        artifact_alias=common.artifact_alias,
        artifact_content_sha256=common.artifact_content_sha256,
        expected_value_commitment_sha256=expectation.expected,
        observed_value_commitment_sha256=observed,
    )
