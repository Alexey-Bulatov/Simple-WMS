from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import get_db, init_db
from app.openapi_docs import install_bilingual_openapi
from app.universal_web import router as universal_web_router

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if get_db not in application.dependency_overrides:
        init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(universal_web_router)
install_bilingual_openapi(app)
