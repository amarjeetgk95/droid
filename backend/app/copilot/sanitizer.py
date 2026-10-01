"""Output sanitizer (spec §1.C, §16, §20, §33).

The backend — not the frontend — is responsible for making sure hidden
reasoning, tool traces, internal prompts and credentials can never reach a user
or a database row. Everything the LLM produces passes through here.
"""
from __future__ import annotations

import re
from typing import Any

#: Internal orchestration / chain-of-thought leakage.
_TRACE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*/?\s*(think|thinking|reasoning|scratchpad|analysis)\s*>", re.I),
    re.compile(r"^\s*(reasoning|chain[- ]of[- ]thought|internal (?:plan|monologue)|scratchpad)\s*:", re.I | re.M),
    re.compile(r"\b(?:calling|call)\s+(?:the\s+)?(?:tool\s+)?(?:get_|fetch_|calculate_)[a-z0-9_]+", re.I),
    re.compile(r"\btool\s+(?:call|result|output|returned)\b[^\n]*", re.I),
    re.compile(r"\b(?:invoking|executing)\s+tool\b[^\n]*", re.I),
    re.compile(r"^\s*(?:system|developer)\s*(?:prompt|message)\s*:", re.I | re.M),
)

#: Credentials / private infrastructure. Never render, never persist.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-or-v1-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"sk-[A-Za-z0-9\-_]{16,}"),
    re.compile(r"\bAQ\.[A-Za-z0-9\-_]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/=]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*[^\s,;\"']{8,}"),
    re.compile(r"(?i)\bpostgres(?:ql)?://[^\s]+"),
    re.compile(r"(?i)\bhttps?://(?:127\.0\.0\.1|localhost|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)[^\s]*"),
)

_SECRET_MASK = "[redacted]"

#: Unicode/whitespace noise the renderer does not need.
_ZERO_WIDTH = re.compile("[\u200b-\u200f\u202a-\u202e\ufeff]")

REMOVED_REASONING = "reasoning"
REMOVED_TOOL_TRACE = "tool_trace"
REMOVED_SECRET = "credential"


def _collapse(text: str) -> str:
    text = _ZERO_WIDTH.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    out: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(line)
    return "\n".join(out).strip()


def strip_reasoning_and_tool_traces(text: str) -> tuple[str, list[str]]:
    """Remove internal reasoning / tool-trace lines. Returns (clean, removals)."""
    if not text:
        return "", []
    removals: list[str] = []
    working = text
    for pattern in _TRACE_PATTERNS:
        if pattern.search(working):
            if pattern.pattern.startswith("<"):
                removals.append(REMOVED_REASONING)
            elif "tool" in pattern.pattern.lower() or "calling" in pattern.pattern:
                removals.append(REMOVED_TOOL_TRACE)
            else:
                removals.append(REMOVED_REASONING)
            working = pattern.sub("", working)
    return _collapse(working), sorted(set(removals))


def redact_secrets(text: str) -> tuple[str, bool]:
    """Mask credentials / private URLs. Returns (clean, redacted?)."""
    if not text:
        return "", False
    redacted = False
    working = text
    for pattern in _SECRET_PATTERNS:
        if pattern.search(working):
            redacted = True
            working = pattern.sub(_SECRET_MASK, working)
    return working, redacted


def sanitize_text(text: Any) -> tuple[str, list[str]]:
    """Full sanitize pass for any user-facing text. Never raises."""
    if text is None:
        return "", []
    try:
        working = text if isinstance(text, str) else str(text)
    except Exception:
        return "", []
    working, trace_removals = strip_reasoning_and_tool_traces(working)
    working, redacted = redact_secrets(working)
    flags = list(trace_removals)
    if redacted:
        flags.append(REMOVED_SECRET)
    return _collapse(working), flags


def sanitize_payload(value: Any) -> Any:
    """Deep-sanitize a JSON-able structure (strings cleaned recursively)."""
    if isinstance(value, str):
        cleaned, _flags = sanitize_text(value)
        return cleaned
    if isinstance(value, dict):
        return {str(key): sanitize_payload(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    return value


def contains_leakage(text: str) -> bool:
    """True when text still carries reasoning/tool-trace/credential signatures."""
    if not text:
        return False
    for pattern in _TRACE_PATTERNS + _SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False
