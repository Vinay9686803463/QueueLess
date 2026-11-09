import importlib.util

from flask import Flask, jsonify  # type: ignore[reportMissingImports]

CORS = None
if importlib.util.find_spec("flask_cors") is not None:
    try:
        from flask_cors import CORS  # type: ignore[reportMissingImports]
    except ImportError:  # pragma: no cover - optional dependency
        CORS = None

from config import Config
from ..extensions import db

try:
    from .database import check_database_connection  # type: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - fallback for alternate package layouts
    from app.routes.database import check_database_connection  # type: ignore[reportMissingImports]

from .auth import auth_bp


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)

    CORS(app, resources={
        r"/api/*": {
            "origins": "*"
        }
    })

    app.register_blueprint(auth_bp)

    @app.route("/")
    def home():
        return jsonify({
            "application": "QueueLess",
            "message": "QueueLess Backend API is running!",
            "status": "success"
        })

    @app.route("/api/health")
    def health():
        return jsonify({
            "application": "QueueLess",
            "status": "healthy"
        })

    @app.route("/api/health/db")
    def database_health():

        try:
            check_database_connection()

            return jsonify({
                "database": "connected",
                "status": "success"
            }), 200

        except Exception:

            db.session.rollback()

            app.logger.exception("Database health check failed")

            return jsonify({
                "database": "disconnected",
                "status": "error",
                "message": "Database connection failed"
            }), 503

    return app