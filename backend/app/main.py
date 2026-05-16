import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.integrations import router as integrations_router
from app.api.routes import router
from app.api.segments import router as segments_router
from app.api.windows import router as windows_router
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# Clockify sync logs each API entry at INFO
logging.getLogger("app.connectors").setLevel(logging.INFO)

app = FastAPI(title="Time Tracker", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(segments_router)
app.include_router(windows_router)
app.include_router(integrations_router)


@app.get("/")
def root() -> dict:
    return {"app": "time-tracker", "docs": "/docs"}
