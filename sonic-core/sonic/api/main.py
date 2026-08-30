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

    yield

    # Shutdown
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
