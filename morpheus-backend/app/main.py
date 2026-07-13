import logging
import sys

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
_log = logging.getLogger(__name__)

_log.info("Loading config...")
from app.config import settings
_log.info("Config loaded. USE_LOCAL_MODELS=%s", settings.USE_LOCAL_MODELS)
from app.security import RequestSizeLimitMiddleware

_log.info("Loading routers...")
from app.routers import dreams, graph
_log.info("Routers loaded.")

app = FastAPI(
    title="Morpheus API",
    description="Dream analytics backend for Project Morpheus",
    version="1.0.0",
)

app.add_middleware(RequestSizeLimitMiddleware)

# Build the allowed origins list from the env var, falling back to wildcard for local dev.
_raw = settings.ALLOWED_ORIGINS.strip()
_origins = [o.strip() for o in _raw.split(",") if o.strip()] if _raw else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    allow_credentials=len(_origins) > 1 or _origins[0] != "*",
)

app.include_router(dreams.router, prefix="/v1")
app.include_router(graph.router, prefix="/v1", tags=["graph"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    _log.warning("Request validation failed for %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Invalid request payload."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    _log.exception("Unhandled error while serving %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}
