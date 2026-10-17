import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = pathlib.Path(__file__).parent


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set in .env")

    migrations = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
    if not migrations:
        sys.exit(f"no migrations found in {MIGRATIONS_DIR}")

    with psycopg.connect(url, connect_timeout=15) as conn:
        for path in migrations:
            print(f"applying {path.name}")
            conn.execute(path.read_text())
        conn.commit()

    print(f"applied {len(migrations)} migration(s)")


if __name__ == "__main__":
    main()
