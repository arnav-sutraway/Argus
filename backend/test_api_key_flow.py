import os
from types import SimpleNamespace

import main


def test_runtime_gemini_key_override_and_restore(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    request = SimpleNamespace(
        gemini_api_key="override-key",
        api_key=None,
        gemini_model="gemini-2.5-flash",
    )

    with main.runtime_gemini_settings(request):
        assert os.environ["GEMINI_API_KEY"] == "override-key"
        assert os.environ["GOOGLE_API_KEY"] == "override-key"
        assert os.environ["GEMINI_MODEL"] == "gemini-2.5-flash"

    assert os.environ.get("GEMINI_API_KEY") is None
    assert os.environ.get("GOOGLE_API_KEY") is None
    assert os.environ.get("GEMINI_MODEL") is None


def test_analyze_request_accepts_runtime_api_key_override():
    request = main.AnalyzeRequest(
        repository_url="https://github.com/example/repo",
        gemini_api_key="runtime-key",
    )

    assert request.gemini_api_key == "runtime-key"
    assert request.api_key is None
