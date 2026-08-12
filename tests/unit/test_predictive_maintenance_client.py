from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.rag.predictive_maintenance_client import fetch_risk_context


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            # A plain exception is enough here — fetch_risk_context()
            # catches any Exception broadly (see its own docstring on
            # why), so the specific type raised by a real non-2xx
            # response doesn't need to be reproduced exactly.
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json_body


def test_returns_none_when_base_url_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url", None
    )

    result = fetch_risk_context("EQ-1")

    assert result is None


def test_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.httpx.get",
        lambda url, timeout: _FakeResponse(json_body={"risk_score": 0.7}),
    )

    result = fetch_risk_context("EQ-1")

    assert result == {"risk_score": 0.7}


def test_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    def _raise_timeout(url: str, timeout: float) -> _FakeResponse:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _raise_timeout)

    assert fetch_risk_context("EQ-1") is None


def test_returns_none_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    def _raise_connect_error(url: str, timeout: float) -> _FakeResponse:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _raise_connect_error)

    assert fetch_risk_context("EQ-1") is None


def test_returns_none_on_non_2xx_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.httpx.get",
        lambda url, timeout: _FakeResponse(status_code=500),
    )

    assert fetch_risk_context("EQ-1") is None


def test_returns_none_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    class _BadJsonResponse(_FakeResponse):
        def json(self) -> Any:
            raise ValueError("not valid json")

    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.httpx.get",
        lambda url, timeout: _BadJsonResponse(),
    )

    assert fetch_risk_context("EQ-1") is None


def test_returns_none_when_body_is_not_an_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.httpx.get",
        lambda url, timeout: _FakeResponse(json_body=[1, 2, 3]),
    )

    assert fetch_risk_context("EQ-1") is None


def test_request_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_timeout_seconds",
        1.5,
    )
    captured_timeout = []

    def _capture(url: str, timeout: float) -> _FakeResponse:
        captured_timeout.append(timeout)
        return _FakeResponse(json_body={})

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _capture)

    fetch_risk_context("EQ-1")

    assert captured_timeout == [1.5]
