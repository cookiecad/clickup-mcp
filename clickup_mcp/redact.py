"""Mask credential-bearing ClickUp responses before they become tool output."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

MASK = "[redacted credential]"
LINK_MASK = "[redacted secure link]"
RULES_VERSION = "2026-10-14.1"

STRONG_LABEL = (
    r"password|passwd|passphrase|pass[ _-]?code|api[ _-]?key|access[ _-]?key|"
    r"secret[ _-]?key|private[ _-]?key|client[ _-]?secret|"
    r"(?:access|refresh|auth)[ _-]?token|licen[cs]e[ _-]?key|activation[ _-]?key|keyCode"
)
GENERIC_LABEL = (
    r"PIN(?:[ _-]?(?:code|number))?|token|secret|pwd|"
    r"(?:security|verification|login|access|one[ _-]?time|2FA|MFA|backup|recovery)[ _-]?codes?|OTP"
)
LABEL = rf"(?:{STRONG_LABEL}|{GENERIC_LABEL})"
# Markdown underscores are word characters to regex \b, so use letter/digit
# boundaries rather than allowing emphasis wrappers to hide a label.
START = r"(?<![A-Za-z0-9])"
END = r"(?![A-Za-z0-9])"
LABEL_NAME = re.compile(rf"{START}{LABEL}{END}", re.I)
FIELD_NAME = re.compile(rf"{LABEL}", re.I)
WRAP = r"[\"'`*_“”‘’]*"
EXPLICIT_SEPARATOR = (
    rf"{WRAP}\s*(?:[:=|→-]|\bis\b\s*[:=]?)\s*[*_]*\s*"
    # A closing label quote may precede a separately quoted value. Do not
    # consume the value's opener: quoted secrets can contain whitespace.
    r"(?:[\"'`“”‘’](?=\s+[\"'`“”‘’]))?\s*"
)
VALUE = r'''(?:"[^"\r\n]+"|'[^'\r\n]+'|`[^`\r\n]+`|“[^”\r\n]+”|‘[^’\r\n]+’|[^\s|<>"'`“”‘’]+)'''
LABELLED = re.compile(
    rf"(?P<prefix>{START}{LABEL}{END}{EXPLICIT_SEPARATOR})(?P<value>{VALUE})", re.I
)
BARE = re.compile(
    rf"(?P<prefix>{START}(?:{STRONG_LABEL}){END}{WRAP}[ \t]+)(?P<value>{VALUE})", re.I
)
PROSE = set(
    "reset resets change changed changes update updated manager policy required field fields "
    "prompt protected protection recovery expired expires expiry rotation rotated for to of "
    "and in on is was will should must not the a an or this that it your my our their you "
    "we they from with".split()
)
URL_FIELD = re.compile(
    r"([?#&](?:amp;)?(?:api[_-]?key|access[_-]?key|key[_-]?code|key|token|"
    r"(?:access|refresh|auth|reset|download|id)[_-]?token|client[_-]?secret|secret|"
    r"password|signature|sig|auth|authorization)=)(?!\[redacted)[^\s&#\"'<>\\]+", re.I
)
SHAPED = re.compile(
    START + r"(?:eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AIza[\w-]{35}|"
    r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9_-]{20,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|xox[abposr]-[A-Za-z0-9-]{10,})" + END
)


def _mask_field(match: re.Match[str], *, bare: bool = False) -> str:
    value = match["value"]
    if value.startswith("[redacted") or (bare and value.lower().rstrip(".,;:)") in PROSE):
        return match[0]
    if bare and value in (":", "=", "-", "|", "→"):
        return match[0]
    suffix = ""
    if value[0] not in "\"'`“‘":
        suffix = value[len(value.rstrip(".,;:)")):]
    return match["prefix"] + MASK + suffix


def _mask_url(match: re.Match[str]) -> str:
    url = match[0]
    try:
        parsed = urlsplit(url.replace("&amp;", "&"))
        host = (parsed.hostname or "").lower()
        if parsed.username or parsed.password or host == "sendsafely.com" or host.endswith(".sendsafely.com"):
            return LINK_MASK
        if re.search(r"/(?:reset[-_]?password|password[-_]?reset|magic[-_]?link|authenticate|order[-_]?access)(?:/|$)", parsed.path, re.I):
            return LINK_MASK
    except ValueError:
        # Malformed credential-bearing URLs still go through field masking.
        return LINK_MASK
    return URL_FIELD.sub(lambda m: m[1] + MASK, url)


def redact_text(text: str) -> str:
    """Apply before truncation/serialization; never log the input."""
    text = re.sub(r"https?://[^\s\"'<>]+", _mask_url, text, flags=re.I)
    text = URL_FIELD.sub(lambda m: m[1] + MASK, text)
    text = re.sub(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----", MASK, text)
    text = LABELLED.sub(_mask_field, text)
    text = BARE.sub(lambda m: _mask_field(m, bare=True), text)
    text = re.sub(START + r"Bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer " + MASK, text, flags=re.I)
    return SHAPED.sub(MASK, text)


def redact_value(value: Any) -> Any:
    """Keep response structure and keys; mask strings and credential fields."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        # ClickUp rich comments split visible text across formatting runs.
        # Masking each run alone misses a label in one run and its value in
        # the next. If their combined text contains a credential, omit all
        # text runs; comment_text retains the masked readable alternative.
        text_runs = [item["text"] for item in value
                     if isinstance(item, dict) and isinstance(item.get("text"), str)]
        combined = "".join(text_runs)
        omit_runs = bool(text_runs) and redact_text(combined) != combined
        safe = [redact_value(item) for item in value]
        if omit_runs:
            return [{**item, "text": MASK} if isinstance(item, dict) and isinstance(item.get("text"), str)
                    else item for item in safe]
        return safe
    if isinstance(value, dict):
        credential_field = any(
            isinstance(value.get(key), str) and LABEL_NAME.search(value[key])
            for key in ("name", "label")
        )
        return {
            key: MASK if (
                (key == "value" and credential_field)
                or (isinstance(key, str) and FIELD_NAME.fullmatch(key))
            ) and item is not None else redact_value(item)
            for key, item in value.items()
        }
    return value
