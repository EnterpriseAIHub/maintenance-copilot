from __future__ import annotations

import pytest

from app.services.escalation_policy import should_escalate_for_confidence


def test_confidence_below_threshold_escalates() -> None:
    assert should_escalate_for_confidence(0.4, threshold=0.55) is True


def test_confidence_above_threshold_does_not_escalate() -> None:
    assert should_escalate_for_confidence(0.7, threshold=0.55) is False


def test_confidence_exactly_at_threshold_does_not_escalate() -> None:
    # The threshold is the minimum acceptable confidence, not the maximum
    # escalatable one — a value exactly at threshold should pass.
    assert should_escalate_for_confidence(0.55, threshold=0.55) is False


def test_confidence_just_below_threshold_escalates() -> None:
    assert should_escalate_for_confidence(0.549999, threshold=0.55) is True


def test_confidence_just_above_threshold_does_not_escalate() -> None:
    assert should_escalate_for_confidence(0.550001, threshold=0.55) is False


def test_zero_confidence_escalates_against_any_positive_threshold() -> None:
    assert should_escalate_for_confidence(0.0, threshold=0.01) is True


def test_zero_confidence_does_not_escalate_against_zero_threshold() -> None:
    assert should_escalate_for_confidence(0.0, threshold=0.0) is False


def test_max_confidence_never_escalates() -> None:
    assert should_escalate_for_confidence(1.0, threshold=1.0) is False
    assert should_escalate_for_confidence(1.0, threshold=0.99) is False


def test_default_threshold_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.escalation_policy.settings.confidence_threshold", 0.9)

    assert should_escalate_for_confidence(0.8) is True
    assert should_escalate_for_confidence(0.95) is False


def test_explicit_threshold_overrides_settings_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.escalation_policy.settings.confidence_threshold", 0.9)

    # Passing threshold explicitly should win over whatever settings says.
    assert should_escalate_for_confidence(0.8, threshold=0.5) is False
