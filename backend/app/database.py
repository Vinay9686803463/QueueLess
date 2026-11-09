from sqlalchemy import text
from .extensions import db


def check_database_connection():
    """
    Check whether the application can connect to PostgreSQL.
    """
    db.session.execute(text("SELECT 1"))
    return True