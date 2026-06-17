from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings  # noqa: F401 — ensures env vars are validated on startup
from app.routers import dreams

app = FastAPI(
    title="Morpheus API",
    description="Dream analytics backend for Project Morpheus",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dreams.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
