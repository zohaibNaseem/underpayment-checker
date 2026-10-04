from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from underpayment_checker.report import appeal_letter_writer as writer

FINDINGS = pd.DataFrame(
    {
        "npi": ["1999999991"],
        "provider": ["NPI 1999999991"],
        "cpt": ["97110"],
        "year": [2026],
        "line_count": [100],
        "total_allowed": [3500.0],
        "expected_rate": [40.0],
        "gap_usd": [500.0],
        "confidence": ["HIGH"],
    }
)
CONTEXT = writer.LetterContext("Fixture Blue Cross", "Test Co", FINDINGS)


class FakeClient:
    """Records the request and returns a canned response, like client.beta.messages.create."""

    def __init__(self, response: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self._response


def _response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )


def test_template_letter_states_facts_without_inventing_details() -> None:
    letter = writer.template_letter(CONTEXT)
    assert "Fixture Blue Cross" in letter
    assert "code 97110" in letter and "$40.00" in letter and "$35.00" in letter
    assert "$500.00" in letter
    assert "[Name]" in letter  # placeholders, not invented people


def test_template_used_by_default() -> None:
    assert writer.write_letter(CONTEXT) == writer.template_letter(CONTEXT)


def test_ai_letter_sends_only_aggregated_facts() -> None:
    pytest.importorskip("anthropic")
    client = FakeClient(_response("Dear team, ..."))
    assert writer.write_letter(CONTEXT, use_ai=True, client=client) == "Dear team, ..."
    request = client.requests[0]
    assert request["model"] == writer.MODEL
    assert request["fallbacks"] == "default"
    prompt = request["messages"][0]["content"]
    assert "97110" in prompt and "patient" not in prompt.lower()


def test_ai_refusal_falls_back_to_template() -> None:
    pytest.importorskip("anthropic")
    client = FakeClient(_response("", stop_reason="refusal"))
    assert writer.write_letter(CONTEXT, use_ai=True, client=client) == writer.template_letter(
        CONTEXT
    )


def test_missing_sdk_falls_back_to_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "anthropic", None)
    assert writer.write_letter(CONTEXT, use_ai=True) == writer.template_letter(CONTEXT)
