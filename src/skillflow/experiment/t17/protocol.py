"""T17 Live protocol identities and isolated configuration roots."""

from enum import StrEnum, unique
from pathlib import PurePosixPath

from skillflow.models.base import NonEmptyStr


@unique
class T17ProtocolId(StrEnum):
    """Immutable evidence-domain protocol revisions."""

    V1 = "t17-live-reference-v1"
    V2 = "t17-live-reference-v2"


PROTOCOL_CONFIG_ROOTS: dict[T17ProtocolId, PurePosixPath] = {
    T17ProtocolId.V1: PurePosixPath("experiments/t17"),
    T17ProtocolId.V2: PurePosixPath("experiments/t17v2"),
}
REFERENCE_BACKEND_BY_PROTOCOL: dict[T17ProtocolId, NonEmptyStr] = {
    T17ProtocolId.V1: "reference_harness",
    T17ProtocolId.V2: "reference_harness_v2",
}


def config_root_for_protocol(protocol_id: T17ProtocolId) -> str:
    """Return the project-relative immutable configuration root."""
    return PROTOCOL_CONFIG_ROOTS[protocol_id].as_posix()


def reference_backend_for_protocol(protocol_id: T17ProtocolId) -> str:
    """Return the report backend identity bound to the protocol."""
    return REFERENCE_BACKEND_BY_PROTOCOL[protocol_id]


def matrix_version_for_protocol(protocol_id: T17ProtocolId) -> str:
    """Return the stable matrix version suffix."""
    return "v2" if protocol_id is T17ProtocolId.V2 else "v1"


def permits_partial_core(protocol_id: T17ProtocolId) -> bool:
    """Only v2 turns missing required Tool results into failed task outcomes."""
    return protocol_id is T17ProtocolId.V2
