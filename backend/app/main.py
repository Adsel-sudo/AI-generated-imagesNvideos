from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .auth_routes import router as auth_router
from .config import settings
from .db import init_db
from .routes import router
from .storage import ensure_data_dirs

app = FastAPI(title="AI image generation internal platform")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.session_cookie_name,
    https_only=False,
    same_site="lax",
)


@app.on_event("startup")
def startup_event() -> None:
    ensure_data_dirs()
    init_db()


app.include_router(auth_router)
app.include_router(router)
