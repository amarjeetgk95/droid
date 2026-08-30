import re
from app.instruments.registry import INSTRUMENT_REGISTRY, get_all_instruments
from app.instruments.schemas import InstrumentConfig

def normalize_query(q: str) -> str:
    if q is None:
        return ""
    # trim, case-insensitive, collapse whitespace, remove special chars for alias matching
    s = q.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _normalize_alias(a: str) -> str:
    return re.sub(r"[^a-z0-9]", "", a.lower().strip())

def resolve_instrument(query: str) -> InstrumentConfig | None:
    """Resolve exact symbol or alias to single instrument. Returns None if ambiguous or not found."""
    norm = normalize_query(query)
    if not norm:
        return None
    # direct symbol match (case-insensitive, no spaces)
    compact = re.sub(r"[^a-z0-9]", "", norm)
    upper = query.strip().upper().replace(" ", "").replace("-", "").replace("/", "").replace(":", "")
    # Try exact symbol in registry
    for sym, cfg in INSTRUMENT_REGISTRY.items():
        if sym.lower() == compact or sym.lower() == norm.replace(" ", ""):
            return cfg
        if cfg.data_provider_symbol.lower().replace(":", "").replace("/", "") == compact:
            return cfg
    # Alias match
    for cfg in INSTRUMENT_REGISTRY.values():
        for alias in cfg.aliases:
            if _normalize_alias(alias) == compact:
                return cfg
        # also check display_name alias
        if _normalize_alias(cfg.display_name) == compact:
            return cfg
    # symbol exact with original registry key
    if upper in INSTRUMENT_REGISTRY:
        return INSTRUMENT_REGISTRY[upper]
    return None

def search_instruments(query: str, asset_class: str | None = None, exchange: str | None = None,
                       instrument_type: str | None = None, fno_only: bool = False, limit: int = 20) -> list[InstrumentConfig]:
    norm = normalize_query(query)
    compact = re.sub(r"[^a-z0-9]", "", norm) if norm else ""
    results: list[tuple[int, InstrumentConfig]] = []
    for cfg in get_all_instruments():
        if asset_class and cfg.asset_class.lower() != asset_class.lower():
            continue
        if exchange and cfg.exchange.lower() != exchange.lower():
            continue
        if instrument_type and cfg.instrument_type.lower() != instrument_type.lower():
            continue
        if fno_only and not cfg.fno_available:
            continue
        if not norm:
            # empty query => return all (limited)
            results.append((0, cfg))
            continue
        score = -1
        symbol_compact = re.sub(r"[^a-z0-9]", "", cfg.symbol.lower())
        display_compact = re.sub(r"[^a-z0-9]", "", cfg.display_name.lower())
        # Exact symbol
        if compact == symbol_compact:
            score = 100
        elif symbol_compact.startswith(compact):
            score = 90
        elif compact in symbol_compact:
            score = 80
        else:
            # alias match
            for alias in cfg.aliases:
                ac = _normalize_alias(alias)
                if ac == compact:
                    score = 95
                    break
                elif ac.startswith(compact):
                    score = max(score, 85)
                elif compact in ac:
                    score = max(score, 75)
            # display name partial
            if display_compact.find(compact) != -1:
                score = max(score, 60)
            # data_provider_symbol partial
            dps = re.sub(r"[^a-z0-9]", "", cfg.data_provider_symbol.lower())
            if compact in dps:
                score = max(score, 50)
        if score >= 0:
            results.append((score, cfg))
    # Sort by score desc then symbol
    results.sort(key=lambda x: (-x[0], x[1].symbol))
    return [cfg for _, cfg in results[:limit]]
