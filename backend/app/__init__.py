from flask import Flask, jsonify  # pyright: ignore[reportMissingImports]
from flask_cors import CORS  # pyright: ignore[reportMissingImports,reportMissingModuleSource]

from config import Config
from .extensions import db  # pyright: ignore[reportMissingImports]
from .database import check_database_connection


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)

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

            return jsonify({
                "database": "disconnected",
                "status": "error",
                "message": "Database connection failed"
            }), 503

    return app