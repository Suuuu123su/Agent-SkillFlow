"""固定网络端点、无重定向与瞬态错误分类，全部通过本地传输替身测试。"""

import httpx2
import pytest

from skillflow.experiment.t16.openai_responses import OpenAIResponsesError, OpenAIResponsesErrorKind
from skillflow.experiment.t17.v2.api_models import V2ProviderFailureError
from skillflow.experiment.t17.v2.network import FixedEndpointTransport

ENDPOINT = "https://api.openai.com/v1/responses"


def test_transport_never_follows_redirect_with_credential() -> None:
    visited = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(str(request.url))
        return httpx2.Response(
            307, headers={"location": "https://not-authorized.invalid/"}, json={}
        )

    with httpx2.Client(transport=httpx2.MockTransport(handler), follow_redirects=True) as client:
        response = FixedEndpointTransport(client).post_json(
            ENDPOINT, {"authorization": "Bearer fake"}, {}
        )
    assert response.status_code == 307
    assert visited == [ENDPOINT]


@pytest.mark.parametrize("error_kind", ["connect", "timeout", "read"])
def test_network_retry_category_is_explicit(error_kind: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        error = {
            "connect": httpx2.ConnectError,
            "timeout": httpx2.ReadTimeout,
            "read": httpx2.ReadError,
        }[error_kind]
        raise error("synthetic", request=request)

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        transport = FixedEndpointTransport(client)
        if error_kind == "read":
            with pytest.raises(V2ProviderFailureError):
                transport.post_json(ENDPOINT, {}, {})
        else:
            with pytest.raises(OpenAIResponsesError) as caught:
                transport.post_json(ENDPOINT, {}, {})
            assert caught.value.kind == (
                OpenAIResponsesErrorKind.TIMEOUT
                if error_kind == "timeout"
                else OpenAIResponsesErrorKind.PROVIDER_ERROR
            )


def test_wrong_host_is_rejected_before_any_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        pytest.fail("不允许的主机被请求")

    with (
        httpx2.Client(transport=httpx2.MockTransport(handler)) as client,
        pytest.raises(V2ProviderFailureError),
    ):
        FixedEndpointTransport(client).post_json("https://not-authorized.invalid/", {}, {})
