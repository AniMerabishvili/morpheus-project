import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
_log = logging.getLogger(__name__)

_log.info("Loading config...")
from app.config import settings
_log.info("Config loaded. USE_LOCAL_MODELS=%s", settings.USE_LOCAL_MODELS)

_log.info("Loading routers...")
from app.routers import dreams, graph
_log.info("Routers loaded.")

app = FastAPI(
    title="Morpheus API",
    description="Dream analytics backend for Project Morpheus",
    version="1.0.0",
)

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


@app.get("/health")
def health_check():
    return {"status": "ok"}
