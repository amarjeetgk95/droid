import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.api import auth, markets, health, contracts, calendar, tokens, ws, cache, circuit_breaker, timeseries, options, regime, ai, historical, paper, ml, fii_dii, crypto, instruments, futures, strategy
from app.api import settings as settings_api
from app.api import watchlists as watchlists_api
from app.api import market_state as pipeline_api
from app.api import dashboard as dashboard_api
from app.api import hpi as hpi_api
from app.api import algo as algo_api
from app.api import institutional as institutional_api
from app.api import telegram as telegram_api
from app.api.signals import router as signals_api
from app.services.central_feed import central_feed
from app.services.write_pipeline import write_pipeline
from app.services.snapshot_service import snapshot_service
from app.services.pattern_outcome_worker import pattern_outcome_worker
from app.hpi.service import hpi_service
from app.core.service_lifecycle import (
    start_provider_with_retry,
    stop_provider_stream,
    start_telegram_stack,
    stop_telegram_stack,
)
import structlog


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    setup_logging()
    logger = structlog.get_logger()
    
    # Startup
    logger.info(
        "app_startup",
        app_name=settings.app_name,
        env=settings.app_env,
        provider=settings.market_data_provider,
        auth_required=settings.auth_required,
    )
    
    # Validate production configuration
    if settings.app_mode == "production" and settings.auth_required:
        if not settings.supabase_jwt_secret:
            logger.error("startup_config_error", detail="SUPABASE_JWT_SECRET required in production")
            raise RuntimeError("SUPABASE_JWT_SECRET must be configured in production mode")
    
    # Cold-Start Snapshot Recovery
    snapshot = snapshot_service.load_snapshot()
    if snapshot:
        logger.info("warm_start_restored", snapshot_time=snapshot.timestamp.isoformat())

    # Load persisted broker config from DB (so Groww token survives restart/Re-deploy)
    # Non-blocking with 3s timeout — previously blocked lifespan for 10s+ when DB cold (caused slow load)
    try:
        from app.core.database import get_async_session_factory
        from app.core.broker_runtime import apply_app_settings
        from app.providers.registry import reset_provider
        factory = get_async_session_factory()
        if factory is not None:
            async def _load_broker():
                async with factory() as _sess:
                    from sqlalchemy import text as _text
                    _res = await _sess.execute(_text("SELECT app_settings FROM user_settings WHERE app_settings IS NOT NULL ORDER BY updated_at DESC LIMIT 1"))
                    _row = _res.first()
                    if _row and _row[0]:
                        _changed = apply_app_settings(_row[0])
                        if _changed:
                            reset_provider()
                            logger.info("startup_broker_config_loaded_from_db", provider=_row[0].get("broker", {}).get("provider") if isinstance(_row[0], dict) else "unknown")
            try:
                await asyncio.wait_for(_load_broker(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("startup_broker_config_load_timeout", hint="DB slow — continuing with env config")
    except Exception as _e:
        logger.warning("startup_broker_config_load_failed", error=str(_e)[:200])

    # Start Micro-Batch Write Pipeline & Snapshot Persistence Worker
    await write_pipeline.start()
    await snapshot_service.start()

    # ── BACKEND STARTUP: start persistent services (once per process) ──
    # FYERS market-data + Telegram are backend-owned from here on. Frontend
    # browser sessions only subscribe to central_feed data; closing the
    # browser/dashboard NEVER stops these services.
    # Start Central Market Data Feed & Upstream Provider Stream (real ticks only; no synthetic)
    await central_feed.start()
    # Backend-owned FYERS start with retry — survives Render cold starts.
    # (Registry lazy autostart is disabled: no request path may start this.)
    await start_provider_with_retry()

    # Pre-warm dashboard summary cache in background so the very first user request loads in <5ms
    async def _safe_prewarm():
        try:
            await dashboard_api.prewarm_dashboard_summary()
        except Exception as prewarm_err:
            logger.warning("dashboard_summary_prewarm_failed", error=str(prewarm_err)[:200])

    asyncio.create_task(_safe_prewarm())

    # Start HPI (Historical Pattern Intelligence) — incl. optional auto-delete sweep (§12)
    await hpi_service.start()

    # Start Pattern Outcome Worker (Historical Intelligence v2)
    await pattern_outcome_worker.start()

    # ── BACKEND STARTUP: Telegram stack (independent of any browser) ──
    # Restores bindings from Supabase, starts outbound/update/notification
    # queues, registers webhook with retry. One instance per process.
    await start_telegram_stack()

    # Start Morning Briefing Service (08:50 AM IST pre-market brief)
    try:
        from app.services.morning_briefing_service import morning_briefing_service
        await morning_briefing_service.start()
        logger.info("morning_briefing_service_started")
    except Exception as e:
        logger.warning("morning_briefing_service_start_failed", error=str(e))

    # Auto-provision & restore Executed Signals from Supabase PostgreSQL
    try:
        from app.signals.signals_persistence import ensure_signals_tables, restore_signals_from_db
        await ensure_signals_tables()
        restored = await restore_signals_from_db()
        logger.info("signals_persistence_initialized", restored_count=restored)
    except Exception as e:
        logger.warning("signals_persistence_init_failed", error=str(e))

    # Start Automated Signal Engine & Outcome Worker (real-time signals, auto paper execution, telegram dispatch)
    try:
        from app.signals.worker import automated_signal_worker
        await automated_signal_worker.start()
        logger.info("automated_signal_worker_started")
    except Exception as e:
        logger.warning("automated_signal_worker_start_failed", error=str(e))

    yield

    # ── BACKEND SHUTDOWN: gracefully close persistent services ──
    # Only here (process teardown) are FYERS/Telegram stopped — never on
    # frontend disconnect.
    async def _shutdown_services():
        try:
            from app.signals.worker import automated_signal_worker
            await automated_signal_worker.stop()
        except Exception:
            pass
        try:
            from app.services.morning_briefing_service import morning_briefing_service
            await morning_briefing_service.stop()
        except Exception:
            pass
        await stop_telegram_stack()
        await pattern_outcome_worker.stop()
        await hpi_service.stop()
        await stop_provider_stream()
        await central_feed.stop()
        await snapshot_service.stop()
        await write_pipeline.stop()

    try:
        await asyncio.wait_for(_shutdown_services(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("app_shutdown_timeout", detail="Graceful shutdown timed out after 15s")
    except Exception as _shut_err:
        logger.warning("app_shutdown_error", error=str(_shut_err)[:200])

    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.3.0",
        description="AI-Powered Indian F&O Market Analysis Platform - High-Frequency & Caching Infrastructure",
        lifespan=lifespan,
    )
    
    # CORS
    origins = [
        settings.frontend_url,
        "https://fo-droid.web.app",
        "https://fo-droid.firebaseapp.com",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "User-Agent", "X-Requested-With"],
    )
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        return {
            "app": settings.app_name,
            "status": "online",
            "version": getattr(settings, "app_version", "1.0.0"),
            "docs_url": "/docs",
            "frontend_url": "https://fo-droid.web.app",
        }

    # Register routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(markets.router)
    app.include_router(contracts.router)
    app.include_router(calendar.router)
    app.include_router(tokens.router)
    app.include_router(ws.router)
    app.include_router(cache.router)
    app.include_router(circuit_breaker.router)
    app.include_router(timeseries.router)
    app.include_router(options.router)
    app.include_router(regime.router)
    app.include_router(ai.router)
    app.include_router(ai.compat_router)
    app.include_router(historical.router)
    app.include_router(paper.router)
    app.include_router(ml.router)
    app.include_router(fii_dii.router)
    app.include_router(crypto.router)
    app.include_router(settings_api.router)
    app.include_router(watchlists_api.router)
    app.include_router(instruments.router)
    app.include_router(hpi_api.router)
    app.include_router(pipeline_api.router)
    app.include_router(dashboard_api.router)
    app.include_router(algo_api.router)
    app.include_router(signals_api)
    app.include_router(institutional_api.router)
    app.include_router(telegram_api.router)
    app.include_router(futures.router)
    app.include_router(strategy.router)
    
    return app


app = create_app()
