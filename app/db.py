from collections.abc import Generator

from psycopg import Connection, connect
from psycopg.rows import dict_row

from app.config import get_settings


def build_dsn() -> str:
    settings = get_settings()
    return (
        f"host={settings.db_server} "
        f"port={settings.db_port} "
        f"dbname={settings.db_name} "
        f"user={settings.db_username} "
        f"password={settings.db_password}"
    )


def get_db() -> Generator[Connection[dict], None, None]:
    conn = connect(build_dsn(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
