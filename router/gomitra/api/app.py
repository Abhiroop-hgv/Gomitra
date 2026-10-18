"""The FastAPI application: routes, the error mapping, the rate-limit guard and the static web app.

Layers: api (this package: HTTP only) -> services (use-cases) -> domain (pure rules) and infra (Firestore, models).
"""
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from gomitra import config
from gomitra.api.routes import assistant, auth, checks, cows, devices, system
from gomitra.core.ratelimit import RateLimiter, client_ip
from gomitra.errors import AppError
from gomitra.services import auth as auth_service


def create_app() -> FastAPI:
    app = FastAPI(title="GoMitra router")
    limiter = RateLimiter(config.RATE_LIMITS)

    @app.on_event("startup")
    def make_farmer_account():
        try:
            auth_service.ensure_env_user()
        except Exception:
            logging.getLogger("gomitra").exception("could not create the farmer account")

    @app.exception_handler(AppError)
    async def app_error(_, exc: AppError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    @app.middleware("http")
    async def guard(request, call_next):
        path, admin = request.url.path, bool(config.ADMIN_KEY) and request.headers.get("x-admin-key") == config.ADMIN_KEY
        if request.method in ("POST", "GET") and path.startswith("/api/") and not admin:
            ip = client_ip(request.headers.get("x-forwarded-for", ""), request.client.host if request.client else "?")
            if not limiter.allow(ip, path, request.method):
                return JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429,
                                    headers={"Retry-After": "60"})
        if config.AUTH_REQUIRED and path.startswith("/api/") and not admin and not auth_service.is_open(path, request.headers):
            try:
                auth_service.user_from_header(request.headers.get("authorization", ""))
            except AppError as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    for module in (auth, cows, checks, devices, assistant, system):
        app.include_router(module.router)

    @app.get("/")
    def index():
        return FileResponse(config.STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
    return app


app = create_app()
