from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    CORS(app)

    @app.route("/")
    def home():
        return jsonify({
            "message": "QueueLess Backend API is running!",
            "status": "success"
        })

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "healthy",
            "application": "QueueLess"
        })

    return app
