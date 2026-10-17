import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in .env")
    return psycopg.connect(url, connect_timeout=20)
