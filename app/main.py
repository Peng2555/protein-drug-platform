"""BoltzFold platform API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from sqlalchemy import text

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.db_migrate import run_migrations
from app.models import Job, JobStatus
from app.routers import auth, batches, jobs, md_jobs, maturation_jobs
from app.schemas import HealthOut

ROOT = Path(__file__).resolve().parents[1]
LEGACY_WEB_DIR = ROOT / "web"
VUE_DIST_DIR = ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serve Vue dist; unknown paths fall back to index.html for client-side routing."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and path not in ("", "/"):
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="BoltzFold Platform", version="1.0.0", description="Protein structure prediction platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(batches.router)
app.include_router(md_jobs.router)
app.include_router(maturation_jobs.router)


@app.on_event("startup")
def _startup_migrate() -> None:
    run_migrations()


@app.get("/api/health", response_model=HealthOut)
def health():
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    redis_status = "ok"
    queue_depth = None
    try:
        import redis

        r = redis.from_url(settings.redis_url)
        r.ping()
        q = settings.celery_gpu_queue
        queue_depth = r.llen(q)
        if queue_depth == 0:
            queue_depth = r.llen("celery")  # legacy fallback
    except Exception as exc:
        redis_status = f"error: {exc}"

    running_jobs = None
    if db_status == "ok":
        db: Session = SessionLocal()
        try:
            running_jobs = (
                db.query(Job).filter(Job.status == JobStatus.running.value).count()
            )
        finally:
            db.close()

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthOut(
        status=overall,
        database=db_status,
        redis=redis_status,
        queue_depth=queue_depth,
        running_jobs=running_jobs,
        gpu_workers=settings.celery_gpu_count,
    )


if LEGACY_WEB_DIR.exists():
    app.mount(
        "/legacy-app",
        StaticFiles(directory=str(LEGACY_WEB_DIR), html=True),
        name="legacy-web",
    )

if VUE_DIST_DIR.exists():
    app.mount("/", SPAStaticFiles(directory=str(VUE_DIST_DIR), html=True), name="web")
elif LEGACY_WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(LEGACY_WEB_DIR), html=True), name="web")
