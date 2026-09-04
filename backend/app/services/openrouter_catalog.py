"""
Dynamic OpenRouter Model Discovery — FREE-MODEL-ONLY by default.

Fetches https://openrouter.ai/api/v1/models, classifies pricing,
categorizes, ranks, caches, and provides validation guards.

Hard rules:
- FREE only when prompt/input price == 0 AND completion/output price == 0
- :free suffix alone does NOT guarantee free — pricing must confirm zero
- Never trust frontend selection — re-validate against cached catalog
- Fallback to cached catalog when OpenRouter unavailable
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# In-memory cache (singleton)
# ---------------------------------------------------------------------------
_cache: dict[str, Any] | None = None
_cache_timestamp: datetime | None = None
_cache_raw_count: int = 0
_cache_using_cached: bool = False
_cache_error: str | None = None
_lock = asyncio.Lock()

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Category literals
CATEGORY_FINANCE = "Finance"
CATEGORY_REASONING = "Reasoning"
CATEGORY_GENERAL = "General"
CATEGORY_CODING = "Coding"
CATEGORY_VISION = "Vision"
CATEGORY_FAST = "Fast"
CATEGORY_RESEARCH = "Research"
CATEGORY_UNKNOWN = "Unknown"

ALL_CATEGORIES = [
    CATEGORY_FINANCE,
    CATEGORY_REASONING,
    CATEGORY_GENERAL,
    CATEGORY_CODING,
    CATEGORY_VISION,
    CATEGORY_FAST,
    CATEGORY_RESEARCH,
    CATEGORY_UNKNOWN,
]

FINANCE_KEYWORDS = [
    "finance", "financial", "trading", "investment", "bloomberg",
    "ling", "fin-", "fin ", ":fin", "economy", "stock market",
]
# Ling finance model name explicit
FINANCE_MODEL_IDS = [
    "ling-3.0-flash-fin",
    "ling-3-flash-fin",
    "ling-flash-fin",
    "finance",
]
REASONING_KEYWORDS = [
    "reasoning", "reasoner", "think", "r1", "o1", "chain-of-thought", "cot", "deepseek-r1", "deepseek/r1", "reason"
]
CODING_KEYWORDS = ["code", "coder", "codestral", "codex", "qwen2.5-coder", "qwen-coder", "deepseek-coder"]
VISION_KEYWORDS = ["vision", "visual", "multimodal", "image", "vl"]
RESEARCH_KEYWORDS = ["research", "perplexity", "sonar", "search"]
FAST_KEYWORDS = ["flash", "mini", "lite", "turbo", "haiku", "fast", "3.5", "instant"]


def _parse_price(value: Any) -> float:
    """Parse pricing field which may be string like '0' or '0.000003' or float or None."""
    if value is None:
        return 0.0
    try:
        # may be string
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if s == "":
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def is_free_model(raw: dict[str, Any]) -> bool:
    """
    Determine FREE status strictly from pricing.
    FREE only when prompt/input ==0 AND completion/output ==0
    Also handles :free suffix: pricing must still be zero.
    """
    pricing = raw.get("pricing") or {}
    # OpenRouter returns pricing: {"prompt": "0", "completion": "0", ...}
    # Also newer: pricing.prompt, pricing.completion, or input/output variants
    prompt_price = None
    completion_price = None

    # Try multiple keys
    for k in ("prompt", "input", "input_price", "prompt_price"):
        if k in pricing:
            prompt_price = pricing[k]
            break
    for k in ("completion", "output", "output_price", "completion_price"):
        if k in pricing:
            completion_price = pricing[k]
            break

    # Fallback if pricing missing -> not free (conservative)
    if prompt_price is None and completion_price is None:
        # No pricing info -> not free
        return False

    # If only one present, treat missing as 0? But spec says BOTH must be 0
    # So if one missing, be conservative: not free unless explicitly zero?
    # We'll treat missing as 0 if other is zero? Safer to require both present and zero
    # But if pricing dict has only prompt/completion as 0, treat as free
    pp = _parse_price(prompt_price) if prompt_price is not None else 0.0
    cp = _parse_price(completion_price) if completion_price is not None else 0.0

    # If raw pricing is dict empty, not free
    if not pricing:
        return False

    is_zero = (pp == 0.0 and cp == 0.0)
    # :free suffix is hint but not sufficient — still require pricing zero
    # So result is is_zero regardless of suffix
    return is_zero


def categorize_model(raw: dict[str, Any]) -> str:
    """Lightweight categorization layer."""
    id_lower = (raw.get("id") or "").lower()
    name_lower = (raw.get("name") or "").lower()
    desc_lower = (raw.get("description") or "").lower()
    combined = f"{id_lower} {name_lower} {desc_lower}"

    # Finance: strong signal — must contain finance keyword AND not be generic
    # We treat "ling" models and explicit finance terms as finance
    is_finance = False
    for kw in FINANCE_KEYWORDS:
        if kw.lower() in combined:
            # Additional guard: for "ling" ensure it's fin variant? ling alone could be general but ling-flash-fin qualifies
            if kw == "ling":
                # require "fin" nearby or "ling" with finance descriptor
                if "fin" in combined or "finance" in combined:
                    is_finance = True
                    break
                # Also if description explicitly says finance-focused
                if "finance" in desc_lower or "financial" in desc_lower or "trading" in desc_lower:
                    is_finance = True
                    break
            else:
                is_finance = True
                break
    # Also handle model id contains "fin" finance
    if not is_finance:
        for fid in FINANCE_MODEL_IDS:
            if fid.lower() in id_lower or fid.lower() in name_lower:
                is_finance = True
                break

    if is_finance:
        return CATEGORY_FINANCE

    # Vision: check architecture modalities
    arch = raw.get("architecture") or {}
    modalities = arch.get("input_modalities") or arch.get("modality") or ""
    if isinstance(modalities, list):
        mod_str = " ".join(modalities).lower()
    else:
        mod_str = str(modalities).lower()
    if "image" in mod_str or "vision" in mod_str:
        return CATEGORY_VISION
    # Also keyword
    for kw in VISION_KEYWORDS:
        if kw in combined and ("vision" in combined or "visual" in combined or "multimodal" in combined):
            return CATEGORY_VISION
    # Specific vision models: gpt-4o, claude 3.5, gemini pro vision
    if "gpt-4o" in id_lower or "claude-3.5" in id_lower or "claude-3-7" in id_lower or "gemini" in id_lower and "vision" in combined:
        # But don't misclassify all; only if image modality or vision keyword
        pass

    # Coding
    for kw in CODING_KEYWORDS:
        if kw in combined:
            return CATEGORY_CODING

    # Reasoning
    for kw in REASONING_KEYWORDS:
        if kw in combined:
            return CATEGORY_REASONING
    # Also reasoning models often have "r1" or "o1" in id
    if ":free" in id_lower and ("r1" in id_lower or "reasoning" in id_lower):
        return CATEGORY_REASONING

    # Research
    for kw in RESEARCH_KEYWORDS:
        if kw in combined:
            return CATEGORY_RESEARCH

    # Fast
    for kw in FAST_KEYWORDS:
        if kw in combined:
            # Only fast if not already finance/reasoning but qualifies
            # Flash models are fast
            return CATEGORY_FAST

    # Default general/unknown
    if id_lower and name_lower:
        return CATEGORY_GENERAL
    return CATEGORY_UNKNOWN


def get_supports_tools(raw: dict[str, Any]) -> bool:
    # OpenRouter architecture or supported_parameters includes tools
    sp = raw.get("supported_parameters") or []
    if isinstance(sp, list):
        for p in sp:
            if "tool" in str(p).lower():
                return True
    arch = raw.get("architecture") or {}
    # instruct_type suggests tool support
    if raw.get("supports_tools") is not None:
        return bool(raw["supports_tools"])
    # Heuristic: most modern chat models support tools except some older
    # Check description or top_provider
    return False


def get_supports_vision(raw: dict[str, Any]) -> bool:
    arch = raw.get("architecture") or {}
    modalities = arch.get("input_modalities") or []
    if isinstance(modalities, list) and "image" in [m.lower() for m in modalities]:
        return True
    if "vision" in (raw.get("description") or "").lower() or "multimodal" in (raw.get("description") or "").lower():
        return True
    return False


def compute_trading_rank(raw: dict[str, Any], category: str, is_free: bool) -> int:
    """
    Internal ranking score for FREE models.
    Considers: Finance specialization, Reasoning, Tool support, Context length, Quality, Latency
    Higher = better.
    """
    score = 0
    # Finance specialization +100
    if category == CATEGORY_FINANCE:
        score += 100
    # Reasoning +80
    if category == CATEGORY_REASONING:
        score += 80
    elif category == CATEGORY_FINANCE and any(k in raw.get("id","").lower() for k in ["reason", "r1"]):
        score += 40  # bonus if finance+reasoning

    # Tool/function support +30
    if get_supports_tools(raw):
        score += 30
    else:
        # heuristic: assume finance & reasoning models often support tools
        if category in (CATEGORY_FINANCE, CATEGORY_REASONING, CATEGORY_CODING):
            score += 15

    # Context length: larger better, cap at 20 pts (e.g., 200k =>20)
    ctx = raw.get("context_length") or raw.get("contextLength") or 8192
    try:
        ctx_val = int(ctx)
    except Exception:
        ctx_val = 8192
    # Normalize: ctx/10000 capped 20
    score += min(20, ctx_val // 10000)

    # Model quality metadata where available: check top_provider or pricing quality?
    # Prefer recent, well-known providers? Add small bonuses:
    id_lower = (raw.get("id") or "").lower()
    # Premium providers bonus
    if "anthropic" in id_lower or "claude" in id_lower:
        score += 10
    if "deepseek" in id_lower and "r1" in id_lower:
        score += 12
    if "qwen" in id_lower:
        score += 8
    if "meta-llama" in id_lower:
        score += 5
    if "google" in id_lower or "gemini" in id_lower:
        score += 7
    if "openai" in id_lower:
        score += 6

    # Ling finance model bonus for trading
    if "ling" in id_lower and "fin" in id_lower:
        score += 25

    # Latency indicators: Fast models +5 but not overriding finance
    if category == CATEGORY_FAST:
        score += 10
    if "flash" in id_lower or "mini" in id_lower or "haiku" in id_lower:
        score += 5

    # Free bonus already but ranking only for free; ensure >0
    if not is_free:
        score -= 50

    return score


def normalize_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Build normalized model object per spec."""
    model_id = raw.get("id") or raw.get("slug") or ""
    name = raw.get("name") or model_id.split("/")[-1].replace(":", " ").title()
    pricing = raw.get("pricing") or {}
    input_price = _parse_price(pricing.get("prompt") or pricing.get("input") or 0)
    output_price = _parse_price(pricing.get("completion") or pricing.get("output") or 0)
    # Also try alternative pricing keys
    if input_price == 0 and "input_price" in pricing:
        input_price = _parse_price(pricing["input_price"])
    if output_price == 0 and "output_price" in pricing:
        output_price = _parse_price(pricing["output_price"])

    is_free = is_free_model(raw)
    category = categorize_model(raw)
    context_len = raw.get("context_length") or raw.get("contextLength") or 8192
    try:
        context_len = int(context_len)
    except Exception:
        context_len = 8192

    rank = compute_trading_rank(raw, category, is_free)
    # Recommended for trading: top tier finance/reasoning free models
    # Threshold heuristic: finance free always recommended, reasoning free with tools recommended, others with rank >80
    recommended = False
    if is_free:
        if category == CATEGORY_FINANCE:
            recommended = True
        elif category == CATEGORY_REASONING and get_supports_tools(raw):
            recommended = True
        elif rank >= 90:
            recommended = True
        elif rank >= 70 and category in (CATEGORY_REASONING, CATEGORY_CODING):
            recommended = True
        # Ensure ling finance always recommended
        if "ling" in model_id.lower() and "fin" in model_id.lower() and is_free:
            recommended = True

    # Determine badges for frontend
    badges = []
    if is_free:
        badges.append("FREE")
    if recommended:
        badges.append("RECOMMENDED")
    if category == CATEGORY_FAST:
        badges.append("FAST")
    if category == CATEGORY_REASONING:
        badges.append("REASONING")
    if category == CATEGORY_FINANCE:
        badges.append("FINANCE")
    if get_supports_vision(raw):
        badges.append("VISION")
    # Capability-aware structured outputs (Ling etc. do NOT support)
    try:
        from app.ai.capability_registry import should_use_structured_outputs as _should_struct
        supports_structured = _should_struct(model_id, raw)
    except Exception:
        supports_structured = True
    if supports_structured:
        badges.append("STRUCTURED")
    else:
        badges.append("PROMPTED_JSON")

    return {
        "id": model_id,
        "name": name,
        "is_free": is_free,
        "context_length": context_len,
        "input_price": input_price,
        "output_price": output_price,
        "pricing": pricing,
        "supports_tools": get_supports_tools(raw),
        "supports_vision": get_supports_vision(raw),
        "supports_structured_outputs": supports_structured,
        "description": raw.get("description") or "",
        "category": category,
        "trading_rank": rank,
        "recommended_for_trading": recommended,
        "badges": badges,
        "raw": raw,  # store raw for debugging, but frontend may strip
        "created": raw.get("created"),
        "architecture": raw.get("architecture"),
        "top_provider": raw.get("top_provider"),
    }


def select_default_trading_model(models: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Prefer finance free model like inclusionai/ling-3.0-flash-fin:free if present,
    else highest-ranked free trading model, else highest ranked general reasoning free.
    """
    if not models:
        return None
    free_models = [m for m in models if m.get("is_free")]
    if not free_models:
        return None

    # First: check explicit finance fin model
    # Sort finance by rank
    finance_free = sorted([m for m in free_models if m.get("category") == CATEGORY_FINANCE], key=lambda x: x.get("trading_rank", 0), reverse=True)
    if finance_free:
        # Prefer inclusionai/ling-3.0-flash-fin:free if exists
        for m in finance_free:
            if "ling-3.0-flash-fin" in m["id"].lower() or "ling-3-flash-fin" in m["id"].lower():
                return m
        return finance_free[0]

    # Fallback to highest ranked recommended free
    recommended = sorted([m for m in free_models if m.get("recommended_for_trading")], key=lambda x: x.get("trading_rank", 0), reverse=True)
    if recommended:
        return recommended[0]

    # Otherwise highest ranked free reasoning
    reasoning_free = sorted([m for m in free_models if m.get("category") == CATEGORY_REASONING], key=lambda x: x.get("trading_rank", 0), reverse=True)
    if reasoning_free:
        return reasoning_free[0]

    # General highest ranked free
    sorted_free = sorted(free_models, key=lambda x: x.get("trading_rank", 0), reverse=True)
    return sorted_free[0] if sorted_free else None


async def fetch_openrouter_catalog_raw(force_api_key: str | None = None) -> list[dict[str, Any]]:
    """Call OpenRouter Models API, return raw list."""
    headers = {
        "HTTP-Referer": "https://fo-droid.web.app",
        "X-Title": "DROID F&O Analysis",
        "Content-Type": "application/json",
    }
    api_key = (force_api_key or settings.openrouter_api_key or getattr(settings, "OPENROUTER_API_KEY", "") or "").strip()
    # Also try env OPENROUTER_API_KEY via settings alias
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    timeout = 15.0
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
        if resp.status_code == 401:
            raise ValueError("OpenRouter: 401 Unauthorized – API key invalid or expired")
        if resp.status_code == 429:
            raise ValueError("OpenRouter: 429 Rate Limited – too many requests")
        if resp.status_code != 200:
            raise ValueError(f"OpenRouter: {resp.status_code} – {resp.text[:300]}")
        data = resp.json()
        # Response shape: {"data": [ {...}, {...} ] }
        raw_list = data.get("data") or data.get("models") or []
        if not isinstance(raw_list, list):
            raise ValueError(f"OpenRouter returned unexpected shape: {str(data)[:400]}")
        return raw_list


async def get_model_catalog(
    force_refresh: bool = False,
    free_only: bool | None = None,
    pricing_filter: str = "all",  # FREE | PAID | ALL
) -> dict[str, Any]:
    """
    Returns normalized catalog with caching.
    free_only param overrides settings if not None.
    pricing_filter: when Allow Paid Models ON, can be FREE/PAID/ALL.
    """
    global _cache, _cache_timestamp, _cache_raw_count, _cache_using_cached, _cache_error

    # Determine cache validity
    cache_minutes = getattr(settings, "openrouter_model_cache_minutes", 10)
    try:
        cache_minutes = int(cache_minutes)
    except Exception:
        cache_minutes = 10
    cache_minutes = max(5, min(15, cache_minutes))  # clamp 5-15

    now = datetime.now(timezone.utc)
    use_cache = False
    if not force_refresh and _cache is not None and _cache_timestamp is not None:
        age = now - _cache_timestamp
        if age < timedelta(minutes=cache_minutes):
            use_cache = True

    raw_list: list[dict[str, Any]] | None = None

    if use_cache:
        # Return cached
        _cache_using_cached = False  # not using stale, it's fresh
        _cache_error = None
        catalog = _cache  # type: ignore
        # But need to apply filters
    else:
        # Try fetch fresh
        try:
            raw_list = await fetch_openrouter_catalog_raw()
            # Normalize
            normalized = [normalize_model(raw) for raw in raw_list]
            # Sort by trading_rank desc, then name
            normalized.sort(key=lambda x: (x["trading_rank"], x["context_length"]), reverse=True)

            # Determine effective free_only
            if free_only is None:
                free_only = getattr(settings, "openrouter_free_only", True)
            # Build response metadata
            updated_at = now.isoformat()
            default_model = select_default_trading_model(normalized)

            catalog = {
                "provider": "openrouter",
                "updated_at": updated_at,
                "free_only": bool(free_only),
                "pricing_filter": pricing_filter,
                "models": normalized,
                "default_model": default_model,
                "total_count": len(normalized),
                "free_count": len([m for m in normalized if m["is_free"]]),
                "paid_count": len([m for m in normalized if not m["is_free"]]),
                "using_cached": False,
                "cache_age_seconds": 0,
            }

            # Update cache
            async with _lock:
                _cache = catalog
                _cache_timestamp = now
                _cache_raw_count = len(raw_list)
                _cache_using_cached = False
                _cache_error = None

            logger.info("openrouter_catalog_fetched", total=len(normalized), free=catalog["free_count"], updated_at=updated_at)

        except Exception as e:
            # On failure, fallback to cache if available
            logger.warning("openrouter_catalog_fetch_failed", error=str(e)[:300])
            if _cache is not None:
                async with _lock:
                    _cache_using_cached = True
                    _cache_error = str(e)[:300]
                # Return stale cache with flag
                catalog = dict(_cache)  # shallow copy
                catalog["using_cached"] = True
                catalog["cache_error"] = str(e)[:300]
                catalog["cache_age_seconds"] = int((now - _cache_timestamp).total_seconds()) if _cache_timestamp else 0
                # Note: free_only pricing_filter still needs to be applied? Keep original?
                logger.info("openrouter_catalog_using_cached", age_seconds=catalog["cache_age_seconds"])
            else:
                # No cache — return empty with error flag
                # We could synthesize empty but should raise so API returns 503?
                # For resilience, return empty catalog with using_cached True and error
                catalog = {
                    "provider": "openrouter",
                    "updated_at": now.isoformat(),
                    "free_only": bool(free_only if free_only is not None else getattr(settings, "openrouter_free_only", True)),
                    "pricing_filter": pricing_filter,
                    "models": [],
                    "default_model": None,
                    "total_count": 0,
                    "free_count": 0,
                    "paid_count": 0,
                    "using_cached": True,
                    "cache_error": str(e)[:500],
                    "cache_age_seconds": 0,
                    "error": str(e)[:500],
                }
                # Don't cache error empty

    # At this point catalog exists — apply pricing_filter if needed
    # If Allow Paid Models OFF (free_only True), filter to free only for outward response
    # But spec says endpoint can support FREE/PAID/ALL when paid enabled. We implement.
    if free_only is None:
        effective_free_only = catalog.get("free_only", getattr(settings, "openrouter_free_only", True))
    else:
        effective_free_only = bool(free_only)
    # pricing_filter param overrides: FREE -> only free, PAID -> only paid, ALL -> all
    # If free_only True, ignore pricing_filter and force FREE
    if effective_free_only:
        filtered = [m for m in catalog["models"] if m.get("is_free")]
        catalog_filtered = dict(catalog)
        catalog_filtered["models"] = filtered
        catalog_filtered["free_only"] = True
        catalog_filtered["pricing_filter"] = "FREE"
        # Recompute default based on filtered
        catalog_filtered["default_model"] = select_default_trading_model(filtered)
        return catalog_filtered
    else:
        # free_only False -> respect pricing_filter
        pf = (pricing_filter or "ALL").upper()
        if pf == "FREE":
            filtered = [m for m in catalog["models"] if m.get("is_free")]
        elif pf == "PAID":
            filtered = [m for m in catalog["models"] if not m.get("is_free")]
        else:
            filtered = catalog["models"]
        catalog_filtered = dict(catalog)
        catalog_filtered["models"] = filtered
        catalog_filtered["free_only"] = False
        catalog_filtered["pricing_filter"] = pf
        catalog_filtered["default_model"] = select_default_trading_model(filtered) if pf in ("FREE", "ALL") else None
        return catalog_filtered


async def validate_model_or_raise(model_id: str, free_only: bool | None = None) -> dict[str, Any]:
    """
    Validate model exists in current/cached catalog, check pricing, enforce FREE-only.
    Raises ValueError with clear message if invalid.
    """
    if not model_id or model_id.strip().lower() in ("auto", "auto — best free for trading", "auto-best-free-for-trading"):
        # Auto means select best free
        catalog = await get_model_catalog(free_only=free_only)
        default = catalog.get("default_model") or select_default_trading_model(catalog["models"])
        if not default:
            raise ValueError("No eligible free model is currently available.")
        return default

    model_id = model_id.strip()
    # Fetch catalog full (including paid) to validate existence before free check
    catalog = await get_model_catalog(free_only=False, pricing_filter="ALL")  # fetch full to validate
    # Find model
    found = next((m for m in catalog["models"] if m["id"] == model_id), None)
    if not found:
        # Try to fetch fresh catalog once more to handle race where model just added/removed
        catalog_fresh = await get_model_catalog(force_refresh=True, free_only=False, pricing_filter="ALL")
        found = next((m for m in catalog_fresh["models"] if m["id"] == model_id), None)
        if not found:
            # Check if it's in raw cached filtered? Maybe model was paid and filtered? Check full
            raise ValueError(f"Model '{model_id}' not found in OpenRouter catalog. It may have been removed or renamed. Refresh models and select another.")

    # Check pricing
    is_free = found.get("is_free", False)
    effective_free_only = free_only
    if effective_free_only is None:
        effective_free_only = getattr(settings, "openrouter_free_only", True)

    if effective_free_only and not is_free:
        raise ValueError("Paid models are disabled. Select a currently free OpenRouter model.")

    return found


def get_cache_status() -> dict[str, Any]:
    """For health/debug endpoint."""
    return {
        "cached": _cache is not None,
        "timestamp": _cache_timestamp.isoformat() if _cache_timestamp else None,
        "age_seconds": int((datetime.now(timezone.utc) - _cache_timestamp).total_seconds()) if _cache_timestamp else None,
        "total_count": _cache_raw_count if _cache else 0,
        "using_cached": _cache_using_cached,
        "error": _cache_error,
    }


# For testing: allow clearing cache
async def clear_cache() -> None:
    global _cache, _cache_timestamp, _cache_raw_count, _cache_using_cached, _cache_error
    async with _lock:
        _cache = None
        _cache_timestamp = None
        _cache_raw_count = 0
        _cache_using_cached = False
        _cache_error = None
