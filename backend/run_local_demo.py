import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

raw_url = os.getenv("TEST_DATABASE_URL")

if not raw_url:
    raise RuntimeError("TEST_DATABASE_URL missing")

parsed = urlsplit(raw_url)
credentials, separator, host_port = parsed.netloc.rpartition("@")

if not separator:
    raise RuntimeError("Invalid database URL")

username, colon, password = credentials.partition(":")

if not colon:
    raise RuntimeError("Invalid credentials")

if ":" in host_port:
    host, port_text = host_port.rsplit(":", 1)
    port = int(port_text)
else:
    host = host_port
    port = 5432

if host not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError("Only local PostgreSQL is allowed")

database_url = URL.create(
    "postgresql+psycopg2",
    username=username,
    password=password,
    host=host,
    port=port,
    database="queueless_dev",
    query=dict(parse_qsl(parsed.query)),
)

os.environ["DATABASE_URL"] = database_url.render_as_string(
    hide_password=False
)
os.environ["FLASK_ENV"] = "development"
os.environ["QUEUELESS_ENABLE_DEMO_DATA"] = "true"

print("LOCAL DEMO ENVIRONMENT")
print("Database: queueless_dev")
print("Demo generation: ENABLED")
print("Production Supabase: NOT USED")

os.chdir(BASE_DIR)

subprocess.run(
    [sys.executable, "app.py"],
    cwd=BASE_DIR,
    env=os.environ.copy(),
    check=False,
)
