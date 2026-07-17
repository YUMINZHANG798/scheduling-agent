from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, demo, hc, schedule
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(schedule.router, prefix=settings.api_prefix)
    app.include_router(agent.router, prefix=settings.api_prefix)
    app.include_router(demo.router, prefix=settings.api_prefix)
    app.include_router(hc.router, prefix=settings.api_prefix)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
