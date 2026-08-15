from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

from app.routers import auth, environments, admin, web
from app.services.teardown_service import teardown_expired_environments

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        teardown_expired_environments,
        "interval",
        minutes=5,
        id="teardown_job",
        replace_existing=True,
    )
    scheduler.start()
    print("[startup] Teardown scheduler started (runs every 5 minutes)")
    yield
    scheduler.shutdown()
    print("[shutdown] Teardown scheduler stopped")


app = FastAPI(title="CloudForge", version="0.1.0", lifespan=lifespan)

app.include_router(web.router)
app.include_router(auth.router)
app.include_router(environments.router)
app.include_router(admin.router)

@app.get("/health")
def health():
    return {"status": "ok"}
