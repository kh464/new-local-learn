from fastapi import FastAPI

from app.api.routes.tasks import router as tasks_router


def create_app() -> FastAPI:
    app = FastAPI(title="Github Tech Doc Generator")
    app.include_router(tasks_router, prefix="/api/v1")
    return app


app = create_app()
