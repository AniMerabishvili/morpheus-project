from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import dreams, graph

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
    allow_headers=["*"],
    allow_credentials=len(_origins) > 1 or _origins[0] != "*",
)

app.include_router(dreams.router, prefix="/v1")
app.include_router(graph.router, prefix="/v1", tags=["graph"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
