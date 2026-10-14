import json
from pathlib import Path

import pytest

from clickup_mcp.redact import MASK, redact_text, redact_value

CASES = json.loads((Path(__file__).parent / "fixtures/synthetic-credentials.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_synthetic_fixture(case):
    text = redact_text(case["input"])
    for secret in case["must_not_contain"]:
        assert secret not in text
    for kept in case["must_contain"]:
        assert kept in text
    assert redact_text(text) == text
    assert redact_value({"nested": [case["input"]]}) == {"nested": [text]}


def test_nested_custom_fields_and_direct_credential_keys():
    original = {"id": "synthetic-task", "custom_fields": [
        {"name": "Portal PIN", "value": 7391},
        {"label": "API key", "value": "synthetic-key"},
        {"name": "Order number", "value": 4521},
    ], "password": "synthetic-password", "PIN": "7391", "none": None}
    safe = redact_value(original)
    assert safe["custom_fields"][0]["value"] == MASK
    assert safe["custom_fields"][1]["value"] == MASK
    assert safe["custom_fields"][2]["value"] == 4521
    assert safe["password"] == safe["PIN"] == MASK
    assert safe["id"] == original["id"]
    assert safe["none"] is None
    assert original["custom_fields"][0]["value"] == 7391
    assert redact_value(safe) == safe


@pytest.mark.parametrize("token", [
    "eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12,
    "ghp_" + "a" * 32, "github_pat_" + "a" * 42,
    "AIza" + "a" * 35, "sk_test_" + "a" * 20,
    "sk-" + "a" * 24, "AKIA" + "A" * 16, "xoxb-" + "a" * 20,
])
def test_shaped_synthetic_credentials(token):
    assert redact_text(token) == MASK
