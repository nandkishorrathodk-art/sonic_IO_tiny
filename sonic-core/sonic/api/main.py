"""
SONIC-REDA — FastAPI Application Entry Point
================================================
Main API server with auth middleware, CORS, and route mounting.

Run:
    uvicorn sonic.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from sonic import __codename__, __version__
from sonic.api.routes import (
    agents,
    auth,
    engagements,
    experiments,
    findings,
    graph,
    health,
    jobs,
    live,
    llm,
    security,
    terminal,
    workstation,
)
from sonic.config import get_settings
from sonic.logger import get_logger
from sonic.memory.graph import get_graph_memory
from sonic.safety.scope import get_scope_checker

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
        from sonic.being.identity import get_or_create_being, get_being_store
        from sonic.being.life_loop import BeingLifeLoop
        from sonic.computer_use.agent import ComputerUseAgent
        from sonic.computer_use.curiosity import CuriosityLoop
        from sonic.memory.vector import get_vector_memory
        from sonic.sandbox.virtual_computer import get_sandbox_provider

        tenant_id = os.environ.get("SONIC_BEING_TENANT", "default")
        being = get_or_create_being(tenant_id)

        # Re-attach the home desktop (Phase 2 persistent body). Respect the
        # configured substrate: production/cloud mode must use Daytona, while
        # local development may use the native Docker workstation.
        provider = None
        try:
            from sonic.computer.models import ComputerState
            if os.environ.get("SONIC_USE_DAYTONA_CLOUD") == "1":
                from sonic.computer.daytona_computer import DaytonaComputerProvider
                candidate = DaytonaComputerProvider()
                persisted_workspace_id = next(iter(candidate.workspaces), "")
                if (
                    persisted_workspace_id
                    and await candidate.status(persisted_workspace_id) != ComputerState.FAILED
                ):
                    provider = candidate
            else:
                import shutil
                from sonic.computer.docker_computer import DockerComputerProvider
                if shutil.which("docker"):
                    candidate = DockerComputerProvider()
                    if await candidate.status(candidate.container_name) != ComputerState.FAILED:
                        provider = candidate
        except Exception as e:
            logger.warning("being_computer_provider_unavailable", error=str(e))
        if provider is None:
            provider = await get_sandbox_provider()
        # The life loop is a computer-use actor, not a generic command worker.
        # A ComputeProvider/DockerSandbox without screen capture cannot satisfy
        # the observe -> reason -> act contract, so do not start a loop that
        # will fail on every tick.
        if not callable(getattr(provider, "screenshot", None)):
            logger.warning(
                "being_life_loop_no_computer_provider",
                provider=type(provider).__name__,
                reason="screen_capture_unavailable",
            )
            return None
        home = None
        if hasattr(provider, "get_or_create_home"):
            home = await provider.get_or_create_home(tenant_id)
        if home is None or getattr(home, "id", None) is None or getattr(home, "id", "") == "":
            logger.warning("being_life_loop_no_home", being_id=being.being_id)
            return None

        from sonic.safety.sealed import seal_default, SealedActionPolicy
        # Tamper-evident safety envelope: config is frozen + hash-sealed, so a
        # self-evolving being cannot widen its own guards at runtime.
        # In development mode, allow intrusive commands without approval for smoother testing
        require_approval = os.environ.get("SONIC_REQUIRE_APPROVAL_FOR_INTRUSIVE", "true").lower() == "true"
        if require_approval:
            safety = seal_default(workspace_root="/home/sonic/workspace")
        else:
            safety = SealedActionPolicy(
                workspace_root="/home/sonic/workspace",
                require_approval_for_intrusive=False
            ).seal()
        # Reuse a shared LLM router if available; curiosity needs an LLM.
        from sonic.llm.router import ModelRouter
        router = ModelRouter.for_default() if hasattr(ModelRouter, "for_default") else ModelRouter()
        gui_only = callable(getattr(provider, "gui_action", None)) and callable(
            getattr(provider, "screenshot", None)
        )
        # Keep the initial capability set empty. The being may opt into a
        # registered capability only when target evidence justifies it.
        from sonic.tools.registry import get_default_registry
        security_registry = get_default_registry(provider)
        # Toolsmith loop (Phase A, AIOSR): the being authors NEW tools for
        # observation gaps.
        from sonic.being.craft import BeingCraft
        from sonic.being.toolsmith import ToolsmithLoop
        toolsmith = ToolsmithLoop(
            craft=BeingCraft(being_id=being.being_id),
            llm=router, registry=security_registry,
        )
        # Method-invention loop (Phase B, AIOSR): the being synthesizes NOVEL
        # offensive techniques (new methods, not just tools) from observation +
        # failure + the known-technique ledger (VectorMemory). Confirmed only
        # on real in-sandbox reproduction; confirmed techniques enter the ledger
        # so novelty compounds across cycles.
        from sonic.being.method_lab import MethodLab
        method_lab = MethodLab(
            llm=router, vector_memory=get_vector_memory(), toolsmith=toolsmith,
        )
        from sonic.being.lessons import LessonsLedger
        lessons_ledger = LessonsLedger(tenant_id=tenant_id, agent_id=being.being_id)
        from sonic.evolution.engine import EvolutionEngine
        from sonic.evolution.strategy import DynamicStrategyEngine
        evolution_engine = EvolutionEngine(
            strategy_engine=DynamicStrategyEngine(),
            method_lab=method_lab,
            toolsmith=toolsmith,
            lessons_ledger=lessons_ledger,
        )
        agent = ComputerUseAgent(
            computer_provider=provider, llm_router=router,
            security_tools=security_registry.as_dict(),
            safety=safety, self_host=True, tenant_id=tenant_id, agent_id=being.being_id,
            # Wire the browser so the being can navigate/click/type/screenshot as
            # a first-class reasoning action (was orphaned before).
            browser=None,
            gui_only=gui_only,
            # Wire the toolsmith so the being can author + run its own tools.
            toolsmith=toolsmith,
            # Wire the method lab so the being can invent new techniques.
            method_lab=method_lab,
            # Wire the lessons ledger so cross-mission lessons compound across sessions.
            lessons_ledger=lessons_ledger,
            # Wire the self-evolution engine for dynamic strategy adaptation and codebase upgrades.
            evolution_engine=evolution_engine,
            # Wire the being's persistent mind (mood) into reasoning — the LLM
            # actually sees curiosity_drive/focus/satiety when choosing actions.
            being_mind=get_being_store().get_mind(being.being_id),
        )
        curiosity = CuriosityLoop(llm_router=router, vector_memory=get_vector_memory(), max_cycles=1)
        tick_interval = float(os.environ.get("SONIC_BEING_TICK_INTERVAL", "60"))
        loop = BeingLifeLoop(being, agent, curiosity, home.id, tick_interval=tick_interval)
        loop.start()
        # Keep the agent's view of the mind fresh as cycles evolve it.
        loop.before_tick_hooks: list = getattr(loop, "before_tick_hooks", [])
        loop.before_tick_hooks.append(
            lambda: setattr(agent, "being_mind", get_being_store().get_mind(being.being_id))
        )
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
    get_scope_checker()
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
        from sonic.memory.router import get_smart_memory
        smart_mem = await get_smart_memory()
        logger.info("persistent_sqlite_graph_memory_ready", backend=type(smart_mem).__name__)

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
    # Release the shared computer provider client (aiohttp session) if one was created.
    # Name is `_primary_computer_instance` in workstation.py (was `_daytona_provider_instance`
    # during the Daytona era; the stale name crashed clean shutdowns with ImportError).
    from sonic.api.routes.workstation import _primary_computer_instance
    if _primary_computer_instance is not None:
        try:
            await _primary_computer_instance.close()
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
logger.info("cors_configured", origins=settings.cors_origins_list)
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
app.include_router(findings.router, prefix="/findings", tags=["Findings"])
app.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])
app.include_router(terminal.router, prefix="/terminal", tags=["Terminal"])
app.include_router(live.router, prefix="/live", tags=["Live Dashboard"])
app.include_router(jobs.router, prefix="/jobs", tags=["Async Jobs"])
app.include_router(workstation.router, tags=["Workstation"])
app.include_router(security.router, prefix="/security", tags=["Self-Security Lab"])



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
