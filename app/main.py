# Entry point of FastAPI application.

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Logging setup -----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)

# --- Rate limiter - shared instance, imported by routers ---------------------
# key_func=get_remote_address: limit per client IP
limiter = Limiter(key_func=get_remote_address)

# --- FastAPI app -------------------------------------------------------------
app = FastAPI(
    title="Expense Sharing API",
    description=(
        "Split expenses with friends and groups. "
        "Features: equal / exact / percentage / shares splits, "
        "debt simplification algorithm (greedy min cash flow), "
        "async email notifications via Celery."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "System", "description": "Health check and system status"},
        {"name": "Authentication", "description": "Register, login, JWT token management"},
        {"name": "Groups", "description": "Create and manage expense groups, members, and balances"},
        {"name": "Expenses", "description": "Add expenses with flexible split types"},
        {"name": "Settlements", "description": "Record debt payments and view settlement history"},
    ]
    # Turn off docs in production (optional, can turn on if needed)
    # docs_url="/docs" if not settings.is_production else None,
    # redoc_url="/redoc" if not settings.is_production else None,
)

# Attach limiter to app state - required by slowapi
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS --------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Request logging middleware ----------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with method, path, status code, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    logger.info(
        "%s %s status=%d duration=%.3fs",
        request.method,
        request.url.path,
        response.status_code,
        duration
    )
    return response

# --- Global exception handler (production only) ------------------------------
if settings.is_production:
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """
        Catch unhandled exceptions in production.
        Returns a generic 500 response - never leaks stack traces to clients.
        Stack trace is logged server-side for debugging.
        """
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# --- Routers -----------------------------------------------------------------
from app.api.v1 import auth, groups, expenses, settlements  # noqa: E402

app.include_router(auth.router, prefix="/api/v1")
app.include_router(groups.router, prefix="/api/v1")
app.include_router(expenses.router, prefix="/api/v1")
app.include_router(settlements.router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker, load balancer, and monitoring."""
    return {"status": "ok", "environment": settings.APP_ENV}