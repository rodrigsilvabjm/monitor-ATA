from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.auth import create_session_token, verify_credentials

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    settings = get_settings()
    if not verify_credentials(username, password, settings):
        response = RedirectResponse("/login?error=1", status_code=303)
        return response

    token = create_session_token(username, settings)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_duration_minutes * 60,
    )
    return response


@router.get("/logout")
def logout() -> RedirectResponse:
    settings = get_settings()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.session_cookie_name)
    return response
