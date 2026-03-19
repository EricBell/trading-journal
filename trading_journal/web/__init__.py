"""Flask web application factory."""

import os
from importlib.metadata import version, PackageNotFoundError
from flask import Flask

try:
    _APP_VERSION = version('trading-journal')
except PackageNotFoundError:
    _APP_VERSION = 'dev'


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # Secret key for signed cookie sessions
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-change-in-production')
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    @app.context_processor
    def inject_version():
        return {'app_version': _APP_VERSION}

    # Register auth hooks (set/clear AuthContext per request)
    from .auth import register_auth_hooks
    register_auth_hooks(app)

    # Register blueprints
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.trades import bp as trades_bp
    from .routes.positions import bp as positions_bp
    from .routes.ingest import bp as ingest_bp
    from .routes.admin import bp as admin_bp
    from .routes.api import bp as api_bp
    from .routes.settings import bp as settings_bp
    from .routes.about import bp as about_bp
    from .routes.journal import bp as journal_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(about_bp)
    app.register_blueprint(journal_bp)

    return app
