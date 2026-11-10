from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from .extensions import db
from .database import check_database_connection
from .routes.auth import auth_bp
from .routes.business import business_bp, public_business_bp
from .routes.appointments import appointment_bp
from .routes.queue import queue_bp
from .routes.services import service_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(business_bp)
    app.register_blueprint(public_business_bp)
    app.register_blueprint(appointment_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(service_bp)

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
