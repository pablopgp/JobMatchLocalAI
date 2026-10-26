import json

import httpx
import pytest
from pydantic import ValidationError

from jobmatch.analysis import (
    analyze,
    OllamaConnectionError,
    OllamaTimeoutError,
    OllamaResponseError,
)
from jobmatch.config import Settings, home, initialize, settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()


def mock_client(monkeypatch, handler):
    original = httpx.Client

    def factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def test_settings_reject_external_endpoints():
    for endpoint in [
        "https://ollama.com",
        "http://192.168.1.2:11434",
        "http://localhost.evil.test:11434",
    ]:
        with pytest.raises(ValidationError):
            Settings(ollama_url=endpoint)


def test_windows_bom_settings():
    (home() / "settings.json").write_text(
        json.dumps({"model": "qwen3:4b-instruct"}), encoding="utf-8-sig"
    )
    assert settings().model == "qwen3:4b-instruct"


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ConnectError, OllamaConnectionError),
        (httpx.ReadTimeout, OllamaTimeoutError),
    ],
)
def test_network_errors_are_actionable(monkeypatch, error, expected):
    def handler(request):
        raise error("secret transport details", request=request)

    mock_client(monkeypatch, handler)
    with pytest.raises(expected) as caught:
        analyze({}, {}, "qwen3:4b-instruct")
    assert "secret" not in str(caught.value)


def test_remote_alias_rejected_before_personal_data(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        assert "candidate" not in request.content.decode()
        return httpx.Response(200, json={"remote_host": "https://ollama.com"})

    mock_client(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="Remote model"):
        analyze({}, {"cv": "private"}, "alias")
    assert paths == ["/api/show"]


@pytest.mark.parametrize("status", [302, 404, 500])
def test_http_failures_do_not_expose_response(monkeypatch, status):
    mock_client(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            text="secret response",
            headers={"location": "https://external.test"},
        ),
    )
    with pytest.raises(OllamaResponseError) as caught:
        analyze({}, {}, "qwen3:4b-instruct")
    assert "secret" not in str(caught.value)


def test_invalid_model_output_not_accepted(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={}
            if request.url.path == "/api/show"
            else {"message": {"content": '{"score":999}'}},
        )

    mock_client(monkeypatch, handler)
    with pytest.raises(OllamaResponseError):
        analyze({}, {}, "qwen3:4b-instruct")
