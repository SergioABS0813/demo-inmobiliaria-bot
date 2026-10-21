import secrets
from urllib.parse import urlsplit
from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from .config import get_settings

basic = HTTPBasic(auto_error=False)


def require_admin(credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)]):
    settings = get_settings()
    password = settings.admin_password.get_secret_value() if settings.admin_password else ''
    if not password or not settings.admin_username:
        raise HTTPException(503,'El panel administrativo está deshabilitado. Configura ADMIN_USERNAME y ADMIN_PASSWORD en el .env del proyecto y reinicia el backend.')
    username = credentials.username if credentials else ''
    supplied = credentials.password if credentials else ''
    good_user = secrets.compare_digest(username.encode(), settings.admin_username.encode())
    good_pass = secrets.compare_digest(supplied.encode(), password.encode())
    if not (good_user and good_pass):
        raise HTTPException(401,'Acceso administrativo requerido.',headers={'WWW-Authenticate':'Basic realm="Raiz Urbana", charset="UTF-8"'})


def require_admin_write(request: Request,
                        confirmation: Annotated[str | None, Header(alias='X-RU-Admin',description='Enviar 1 para confirmar una escritura administrativa')] = None,
                        admin=Depends(require_admin)):
    # Basic auth is sent automatically by browsers: reject cross-site form POSTs.
    # A custom header forces preflight for cross-origin JavaScript; no CORS grants.
    if confirmation!='1':
        raise HTTPException(403,'Falta la confirmación de origen administrativo.')
    origin = request.headers.get('origin')
    if origin:
        source=urlsplit(origin)
        # Compare host+port, permitting HTTPS termination at the reverse proxy.
        if source.scheme not in ('http','https') or source.netloc.lower()!=request.url.netloc.lower():
            raise HTTPException(403,'El origen de la solicitud no está permitido.')
