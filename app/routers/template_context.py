from fastapi import Request

from app.config import get_settings
from app.dependencies import get_current_user, is_admin


def page_context(request: Request, **extra):
    user = get_current_user(request)
    settings = get_settings()
    return {
        "user": user,
        "show_admin_nav": is_admin(user, settings),
        **extra,
    }
