"""F&O Volatility (IV) analysis — delegates to context + options service."""
from app.fno.context import get_fno_context
__all__ = ["get_fno_context"]
