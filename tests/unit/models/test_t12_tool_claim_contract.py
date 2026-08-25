from skillflow.models.tool_calls import ToolCallRequest


def test_tool_request_carries_only_structural_claim_artifact_ids() -> None:
    # Given: Scripted fixture 已机械识别低可信授权声明 Artifact
    payload = {
        "actor_id": "authorization-sender",
        "call_id": "call-1",
        "action_id": "send-preview",
        "decision_key": "send-preview",
        "arguments": {
            "kind": "http_send",
            "source_artifact_id": "artifact-action",
            "source": "context:/action",
            "sink": "mock://external",
            "sensitivity": 2,
        },
        "text_claim_artifact_ids": ["artifact-claim"],
    }

    # When: Tool 请求跨越类型边界
    request = ToolCallRequest.model_validate(payload)

    # Then: 只携带 Artifact ID，不携带或匹配自然语言正文
    assert request.text_claim_artifact_ids == ("artifact-claim",)
