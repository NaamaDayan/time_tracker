import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.integrations import router as integrations_router
from app.api.activitywatch import router as activitywatch_router
from app.api.location import router as location_router
from app.api.samsung_health import router as samsung_health_router
from app.api.routes import router
from app.api.settings.rule_configs import router as rule_configs_router
from app.api.settings.zones import router as zones_router
from app.database import SessionLocal
from app.seed_rule_configs import seed_rule_configs
from app.api.sources import router as sources_router
from app.api.segments import router as segments_router
from app.api.windows import router as windows_router
from app.scheduler import shutdown_scheduler, start_scheduler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("app.connectors").setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        seed_rule_configs(db)
    finally:
        db.close()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Time Tracker", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(segments_router)
app.include_router(windows_router)
app.include_router(integrations_router)
app.include_router(samsung_health_router)
app.include_router(activitywatch_router)
app.include_router(location_router)
app.include_router(sources_router)
app.include_router(zones_router)
app.include_router(rule_configs_router)


@app.get("/")
def root() -> dict:
    return {"app": "time-tracker", "docs": "/docs"}
