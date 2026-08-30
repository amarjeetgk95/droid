from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.api import auth, markets, health, contracts, calendar, tokens, ws, cache, circuit_breaker, timeseries, options, futures, regime, strategy, ai, historical, backtest, paper, alerts, ml, fii_dii, crypto, instruments, chart_analysis
from app.api import settings as settings_api
from app.api import watchlists as watchlists_api
from app.api import market_state as pipeline_api
from app.api import dashboard as dashboard_api
from app.api import benchmark as benchmark_api
from app.api import hpi as hpi_api
from app.services.central_feed import central_feed
from app.services.write_pipeline import write_pipeline
from app.services.snapshot_service import snapshot_service
from app.hpi.service import hpi_service
from app.providers.registry import get_provider
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

    # Start Micro-Batch Write Pipeline & Snapshot Persistence Worker
    await write_pipeline.start()
    await snapshot_service.start()

    # Start Central Market Data Feed & Upstream Provider Stream
    await central_feed.start()
    provider = get_provider()
    await provider.start_stream()

    # Start HPI (Historical Pattern Intelligence) — incl. optional auto-delete sweep (§12)
    await hpi_service.start()

    yield
    
    # Shutdown in reverse order
    await hpi_service.stop()
    await provider.stop_stream()
    await central_feed.stop()
    await snapshot_service.stop()
    await write_pipeline.stop()
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
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
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
    app.include_router(futures.router)
    app.include_router(regime.router)
    app.include_router(strategy.router)
    app.include_router(ai.router)
    app.include_router(ai.compat_router)
    app.include_router(historical.router)
    app.include_router(backtest.router)
    app.include_router(paper.router)
    app.include_router(alerts.router)
    app.include_router(ml.router)
    app.include_router(fii_dii.router)
    app.include_router(crypto.router)
    app.include_router(settings_api.router)
    app.include_router(watchlists_api.router)
    app.include_router(instruments.router)
    app.include_router(chart_analysis.router)
    app.include_router(hpi_api.router)
    app.include_router(pipeline_api.router)
    app.include_router(dashboard_api.router)
    app.include_router(benchmark_api.router)
    
    return app


app = create_app()
