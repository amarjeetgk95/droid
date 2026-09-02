import pytest
from app.ai.streaming import (
    ReasoningExtractor,
    sse_event,
    sse_content_chunk,
    sse_reasoning_chunk,
    sse_tool_call_chunk,
    sse_done_chunk,
)
from app.models.ai import AIChatStreamChunk


def test_reasoning_extractor_basic():
    extractor = ReasoningExtractor()
    chunks = [
        "<think>",
        "Checking NIFTY 24800 PE open interest buildup. ",
        "Put wall is strong at 24800.",
        "</think>",
        "Based on the options data, NIFTY has strong support at ₹24,800.",
    ]
    results = []
    for c in chunks:
        results.extend(extractor.process(c))

    reasoning_text = "".join([t[1] for t in results if t[0] == "reasoning"])
    content_text = "".join([t[1] for t in results if t[0] == "content"])

    assert "Checking NIFTY 24800 PE" in reasoning_text
    assert "Put wall is strong" in reasoning_text
    assert "strong support at ₹24,800" in content_text


def test_reasoning_extractor_split_across_tokens():
    extractor = ReasoningExtractor()
    chunks = [
        "Pre-text <th",
        "ink>Reasoning line</thi",
        "nk> Post-text",
    ]
    results = []
    for c in chunks:
        results.extend(extractor.process(c))

    reasoning_text = "".join([t[1] for t in results if t[0] == "reasoning"])
    content_text = "".join([t[1] for t in results if t[0] == "content"])

    assert "Reasoning line" in reasoning_text
    assert "Pre-text " in content_text
    assert " Post-text" in content_text


def test_sse_formatting():
    c1 = sse_content_chunk("Hello trader")
    assert c1.startswith("data: {")
    assert c1.endswith("}\n\n")
    assert '"delta":"Hello trader"' in c1

    c2 = sse_reasoning_chunk("Thinking about PCR")
    assert '"reasoning_delta":"Thinking about PCR"' in c2

    c3 = sse_tool_call_chunk({"name": "get_market_quote", "arguments": '{"symbol":"NIFTY"}'})
    assert '"type":"tool_call"' in c3
    assert '"get_market_quote"' in c3

    c4 = sse_done_chunk()
    assert '"type":"done"' in c4
    assert '"finish_reason":"stop"' in c4
