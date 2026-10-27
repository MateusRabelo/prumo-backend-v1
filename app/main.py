from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import (
    auth,
    family,
    settings as settings_api,
    transactions,
    installments,
    budgets,
    goals,
    dashboard,
    reports,
    audit,
    cards,
    imports,
    import_drafts,
    subscriptions,
)

from app.services.automatic_audit import install_audit_hooks
install_audit_hooks()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API do MSFinanças — Sistema completo de gestão financeira pessoal e familiar",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(family.router, prefix=settings.API_V1_STR)
app.include_router(settings_api.router, prefix=settings.API_V1_STR)
app.include_router(transactions.router, prefix=settings.API_V1_STR)
app.include_router(installments.router, prefix=settings.API_V1_STR)
app.include_router(budgets.router, prefix=settings.API_V1_STR)
app.include_router(goals.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(reports.router, prefix=settings.API_V1_STR)
app.include_router(audit.router, prefix=settings.API_V1_STR)
app.include_router(cards.router, prefix=settings.API_V1_STR)
app.include_router(imports.router, prefix=settings.API_V1_STR)
app.include_router(import_drafts.router,prefix=settings.API_V1_STR)
app.include_router(subscriptions.router,prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT
    }


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Operação viola uma restrição de integridade ou registro já existente"})
