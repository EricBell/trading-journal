"""Web authentication: session management + route decorators."""

import functools
import logging
from typing import Optional

from flask import Flask, abort, redirect, session, url_for
from werkzeug.security import check_password_hash

from ..auth.base import AuthUser
from ..authorization import AuthContext
from ..database import db_manager
from ..models import User

logger = logging.getLogger(__name__)


def _load_user(user_id: int) -> Optional[AuthUser]:
    """Load an AuthUser from the database by user_id."""
    try:
        with db_manager.get_session() as db_session:
            user = db_session.get(User, user_id)
            if user is None or not user.is_active:
                return None
            return AuthUser(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                is_admin=user.is_admin,
                is_active=user.is_active,
                auth_method='session',
                timezone=user.timezone or 'US/Eastern',
            )
    except Exception:
        logger.exception("Failed to load user from session")
        return None


def register_auth_hooks(app: Flask) -> None:
    """Register before/teardown request hooks that manage AuthContext."""

    @app.before_request
    def _set_auth_context() -> None:
        user_id = session.get('user_id')
        if user_id:
            user = _load_user(user_id)
            if user:
                AuthContext.set_current_user(user)
            else:
                session.clear()

    @app.teardown_request
    def _clear_auth_context(exc: Optional[Exception]) -> None:
        AuthContext.clear()


def authenticate_user(username: str, password: str) -> Optional[AuthUser]:
    """Verify username+password, return AuthUser on success or None on failure."""
    try:
        with db_manager.get_session() as db_session:
            user = db_session.query(User).filter_by(username=username).first()
            if user is None or not user.is_active:
                return None
            if not user.password_hash:
                return None
            if not check_password_hash(user.password_hash, password):
                return None
            return AuthUser(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                is_admin=user.is_admin,
                is_active=user.is_active,
                auth_method='session',
                timezone=user.timezone or 'US/Eastern',
            )
    except Exception:
        logger.exception("Authentication error")
        return None


def login_required(f):
    """Decorator: redirect to /login if no authenticated session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: 403 if authenticated user is not an admin."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        user = AuthContext.get_current_user()
        if user is None or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated
