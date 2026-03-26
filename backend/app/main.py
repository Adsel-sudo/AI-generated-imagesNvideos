from fastapi import FastAPI

from .db import init_db
from .routes import router
from .storage import ensure_data_dirs

app = FastAPI(title="AI image generation internal platform")


@app.on_event("startup")
def startup_event() -> None:
    ensure_data_dirs()
    init_db()


app.include_router(router)
