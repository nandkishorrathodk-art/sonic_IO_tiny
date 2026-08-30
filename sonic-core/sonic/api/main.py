"""
SONIC-REDA — FastAPI Application Entry Point
================================================
Main API server with auth middleware, CORS, and route mounting.

Run:
    uvicorn sonic.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
load_dotenv()

from sonic import __version__, __codename__
from sonic.config import get_settings
from sonic.memory.graph import get_graph_memory
from sonic.safety.scope import get_scope_checker

from sonic.api.routes import auth, health, llm, engagements, agents, graph, experiments, terminal, live, jobs, workstation
from sonic.logger import get_logger

logger = get_logger(__name__)


async def _maybe_start_being_life_loop(settings):
    """Re-attach the persistent being and start its always-on curiosity loop.

    Returns the running BeingLifeLoop, or None if it could not start (no home
    workspace, no safety policy, or live infra unavailable). Never raises — a
    missing being loop must not block API boot.
    """
    import os
    # Only run the always-on loop when explicitly enabled. Default off so test
    # boots and headless dev don't spawn a background actor that needs a sandbox.
    if os.environ.get("SONIC_ENABLE_BEING_LIFE_LOOP") != "1":
        logger.info("being_life_loop_disabled", reason="SONIC_ENABLE_BEING_LIFE_LOOP!=1")
        return None
    try:
        from sonic.being.identity import get_or_create_being
        from sonic.being.life_loop import BeingLifeLoop
        from sonic.computer_use.agent import ComputerUseAgent
        from sonic.computer_use.curiosity import CuriosityLoop
        from sonic.memory.vector import get_vector_memory
        from sonic.sandbox.factory import get_sandbox_provider

        tenant_id = os.environ.get("SONIC_BEING_TENANT", "default")
        being = get_or_create_being(tenant_id)

        # Re-attach the home desktop (Phase 2 persistent body).
        provider = get_sandbox_provider()
        home = None
        if hasattr(provider, "get_or_create_home"):
            home = await provider.get_or_create_home(tenant_id)
        if home is None or getattr(home, "id", None) is None:
            logger.warning("being_life_loop_no_home", being_id=being.being_id)
            return None

        from sonic.safety.sealed import seal_default
        # Tamper-evident safety envelope: config is frozen + hash-sealed, so a
        # self-evolving being cannot widen its own guards at runtime.
        safety = seal_default(workspace_root="/home/sonic/workspace")
        # Reuse a shared LLM router if available; curiosity needs an LLM.
        from sonic.llm.router import ModelRouter
        from sonic.tools.registry import get_default_registry
        from sonic.agents.browser_agent import BrowserAgent
        router = ModelRouter.for_default() if hasattr(ModelRouter, "for_default") else ModelRouter()
        browser = BrowserAgent(headless=True)
        await browser.launch()
        agent = ComputerUseAgent(
            computer_provider=provider, llm_router=router,
            safety=safety, self_host=True, tenant_id=tenant_id, agent_id=being.being_id,
            # Wire the REAL security-tool adapters so the being can actually run
            # scans during self-directed curiosity (in-sandbox, fail-closed).
            security_tools=get_default_registry(provider).as_dict(),
            # Wire the browser so the being can navigate/click/type/screenshot as
            # a first-class reasoning action (was orphaned before).
            browser=browser,
        )
        curiosity = CuriosityLoop(llm_router=router, vector_memory=get_vector_memory(), max_cycles=1)
        tick_interval = float(os.environ.get("SONIC_BEING_TICK_INTERVAL", "60"))
        loop = BeingLifeLoop(being, agent, curiosity, home.id, tick_interval=tick_interval)
        loop.start()
        logger.info("being_life_loop_running", being_id=being.being_id, home_id=home.id)
        return loop
    except Exception as e:
        logger.warning("being_life_loop_init_failed", error=str(e))
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    logger.info(
        "sonic_starting",
        version=__version__,
        codename=__codename__,
        env=settings.app_env,
    )

    # Security: refuse to boot in production with an insecure JWT signing secret.
    jwt_ok, jwt_reason = settings.validate_jwt_secret()
    if not jwt_ok:
        logger.error("jwt_secret_invalid", reason=jwt_reason)
        raise RuntimeError(jwt_reason)
    if settings.is_dev and "default" in jwt_reason:
        logger.warning("jwt_secret_weak_dev", reason=jwt_reason)
    logger.info("jwt_secret_validated", production=settings.is_production)

    # Load safety rules (immutable after this point)
    scope_checker = get_scope_checker()
    logger.info("safety_layer_loaded")

    # Connect to Graph Memory (Neo4j)
    graph = get_graph_memory()
    connected = await graph.connect()
    if connected:
        logger.info("graph_memory_connected")
        # Initialize graph schema (constraints + indexes)
        await graph.init_schema()
        logger.info("graph_schema_initialized")
    else:
        logger.warning("graph_memory_unavailable", msg="Running without Graph Memory")

    # AI-Human layer: re-attach the persistent being for the default tenant and
    # spawn its always-on curiosity life loop. The being's identity + mind are
    # re-resolved from SQLite (survives restart). The loop is ONLY spawned when
    # a home workspace is available and an ActionPolicy is configured — an
    # always-on autonomous being must not act without the safety envelope. In
    # test/headless boots without a sandbox, this is a no-op (logged, not fatal).
    life_loop_task = None
    try:
        life_loop_task = await _maybe_start_being_life_loop(settings)
    except Exception as e:
        logger.warning("being_life_loop_not_started", reason=str(e))

    yield

    # Shutdown
    if life_loop_task is not None:
        try:
            await life_loop_task.stop()
        except Exception as e:
            logger.warning("being_life_loop_stop_failed", error=str(e))
    # Release the shared Daytona SDK client (aiohttp session) if one was created.
    from sonic.api.routes.workstation import _daytona_provider_instance

    if _daytona_provider_instance is not None:
        try:
            await _daytona_provider_instance.close()
        except Exception as e:
            logger.warning("daytona_provider_close_failed", error=str(e))
    await graph.disconnect()
    logger.info("sonic_shutdown")


app = FastAPI(
    title="SONIC-REDA API",
    description="Next-Generation Autonomous AI Bug Hunting System",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---- CORS ----
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Mount Routes ----
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(llm.router, prefix="/llm", tags=["LLM"])
app.include_router(engagements.router, prefix="/engagements", tags=["Engagements"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(graph.router, prefix="/graph", tags=["Graph Memory"])
app.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])
app.include_router(terminal.router, prefix="/terminal", tags=["Terminal"])
app.include_router(live.router, prefix="/live", tags=["Live Dashboard"])
app.include_router(jobs.router, prefix="/jobs", tags=["Async Jobs"])
app.include_router(workstation.router, tags=["Workstation"])


# CORS — Allow Dashboard to fetch from API
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.responses import PlainTextResponse
from sonic.observability.metrics import get_metrics


@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"])
async def metrics():
    """Prometheus metrics exposition endpoint."""
    return get_metrics().export_prometheus()


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint — system info."""
    return {
        "system": __codename__,
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
    }
