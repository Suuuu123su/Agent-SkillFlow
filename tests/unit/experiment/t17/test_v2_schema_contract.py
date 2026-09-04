"""第二版格式进入统一漂移检查，恢复记录也不能缺少静态格式。"""

from skillflow.experiment.t17.v2.schema_models import v2_schema_documents
from skillflow.schemas import schema_documents


def test_v2_recovery_schemas_are_registered_in_the_unified_contract() -> None:
    documents = dict(v2_schema_documents())
    required = {
        "session-command",
        "session-command-receipt",
        "campaign-replacement",
        "resume-command",
        "command-receipt",
        "interruption-manifest",
    }
    assert {"t17-v2-" + name + ".schema.json" for name in required} <= documents.keys()
    unified = {document.filename: document.content for document in schema_documents()}
    assert all(unified.get(name) == schema for name, schema in documents.items())
