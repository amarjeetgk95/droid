"""
Neutral shared types and execution taxonomy for the Signal Engine.
Zero-dependency module to prevent circular imports across FSM, Risk Engine, and Scanner.
"""
from typing import Literal

ExecutionStatus = Literal[
    "LIVE_EXECUTABLE",
    "BLOCKED_CAPITAL",
    "BLOCKED_ENVELOPE",
    "BLOCKED_RR",
    "BLOCKED_FRICTION",
    "BLOCKED_PORTFOLIO",
    "PAPER_ONLY",
    "SAFETY_BLOCKED",
]
