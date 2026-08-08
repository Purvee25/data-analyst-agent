"""Shared test fixtures: a fake Anthropic client so no test ever hits the network.

WHY a hand-rolled fake instead of unittest.mock everywhere:
    The agents only touch three things on a response: stop_reason, content
    blocks with .type/.text, and the client's messages.create(). A tiny typed
    fake makes each test read as "given Claude returns X, we do Y" without
    MagicMock's anything-goes attribute access hiding typos.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

# Make `analyst` importable when pytest runs from the repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeMessages:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []  # kwargs of every create() call, for asserts

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    """Stands in for anthropic.Anthropic. Feed it a list of responses/exceptions."""

    def __init__(self, responses: list):
        self.messages = FakeMessages(responses)


def text_response(payload, stop_reason: str = "end_turn"):
    """Build a fake Message whose single text block contains JSON (or raw text)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason=stop_reason, content=[block])


@pytest.fixture
def superstore_like_df() -> pd.DataFrame:
    """Small frame mirroring the Superstore schema for chart/guardrail tests."""
    return pd.DataFrame(
        {
            "Order Date": pd.to_datetime(["2024-01-05", "2024-02-10", "2024-02-20", "2024-03-01"]),
            "Region": ["West", "East", "West", "South"],
            "Category": ["Furniture", "Technology", "Furniture", "Office Supplies"],
            "Sales": [100.0, 250.0, 80.0, 40.0],
            "Profit": [20.0, 60.0, -5.0, 10.0],
            "Quantity": [1, 2, 1, 3],
        }
    )
