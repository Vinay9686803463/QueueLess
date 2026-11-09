from sqlalchemy import text
from .extensions import db


def check_database_connection():
    db.session.execute(text("SELECT 1"))
    return True
