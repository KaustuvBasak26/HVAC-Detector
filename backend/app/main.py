from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.viewer_token import ensure_viewer_token_secret
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.static_files import SecureStaticFiles

Base.metadata.create_all(bind=engine)
ensure_viewer_token_secret()

_openapi_url = None if settings.secure_deployment else "/openapi.json"
_docs_url = None if settings.secure_deployment else "/docs"
_redoc_url = None if settings.secure_deployment else "/redoc"

app = FastAPI(
    title=settings.app_name,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)
if settings.secure_deployment:
    app.add_middleware(SecurityHeadersMiddleware)

_cors_origins = [] if settings.secure_deployment else settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"] if settings.secure_deployment else ["*"],
    allow_headers=["Content-Type", "X-Job-Viewer-Token"] if settings.secure_deployment else ["*"],
)
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if settings.secure_deployment:

    @app.get("/robots.txt", include_in_schema=False)
    def robots_txt() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nDisallow: /\n")


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", SecureStaticFiles(directory=_STATIC_DIR, html=True), name="frontend")
