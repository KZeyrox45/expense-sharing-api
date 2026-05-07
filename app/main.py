# Entry point of FastAPI application.
# Phase 1: Just health check, routers will be added in Phase 3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


app = FastAPI(
    title="Expense Sharing API",
    description=(
        "Split expenses with friends and groups. "
        "Features: multi-currency splits, debt simplification algorithm, "
        "async email notifications."
    ),
    version="1.0.0",
    # Turn off docs in production (optional, can turn on if needed)
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None
)

# CORS - allow frontend calls API (reconfigure in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Routers will be included gradually ---------------------------------
# from app.api.v1 import auth, groups, expenses, settlements
# app.include_router(auth.router, prefix="/api/v1")
# ...


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Used by Docker healthcheck, load balancer, monitoring tools.
    """
    return {
        "status": "ok",
        "environment": settings.APP_ENV
    }