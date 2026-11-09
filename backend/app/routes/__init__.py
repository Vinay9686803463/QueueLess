from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from .extensions import db
from .database import check_database_connection
from .routes.auth import auth_bp


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)

    # Register authentication routes
    app.register_blueprint(auth_bp)

    # Configure CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": "*"
        }
    })

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