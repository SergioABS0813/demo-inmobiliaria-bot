"""API documentation with a CSP scoped to these two HTML responses."""
import secrets
from fastapi import Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html


def _allow_documentation_assets(response):
    nonce = secrets.token_urlsafe(24)
    # Swagger's inline initializer needs a nonce; CDN scripts receive it too.
    response.body = response.body.replace(b"<script", f'<script nonce="{nonce}"'.encode())
    response.headers["content-length"] = str(len(response.body))
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' data:; img-src 'self' https: data:; "
        "connect-src 'self'; worker-src 'self' blob:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


def install_documentation(app):
    @app.get("/docs", include_in_schema=False)
    def swagger(request: Request):
        prefix = request.scope.get("root_path", "").rstrip("/")
        return _allow_documentation_assets(get_swagger_ui_html(
            openapi_url=f"{prefix}{app.openapi_url}",
            title=f"{app.title} — Swagger UI",
            swagger_favicon_url=f"{prefix}/static/img/logotipo-inmobiliaria-sin-fondo.png",
            swagger_ui_parameters={"validatorUrl": None, "persistAuthorization": False},
        ))

    @app.get("/redoc", include_in_schema=False)
    def redoc(request: Request):
        prefix = request.scope.get("root_path", "").rstrip("/")
        return _allow_documentation_assets(get_redoc_html(
            openapi_url=f"{prefix}{app.openapi_url}",
            title=f"{app.title} — ReDoc",
            redoc_favicon_url=f"{prefix}/static/img/logotipo-inmobiliaria-sin-fondo.png",
            with_google_fonts=False,
        ))
