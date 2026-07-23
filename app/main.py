from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import init_db
from app.map_web import router as map_web_router
from app.task_web import router as task_web_router
from app.transfer_web import router as transfer_web_router
from app.web import router as web_router
from app.work_web import router as work_web_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


app.include_router(router)
app.include_router(web_router)
app.include_router(work_web_router)
app.include_router(map_web_router)
app.include_router(transfer_web_router)
app.include_router(task_web_router)
