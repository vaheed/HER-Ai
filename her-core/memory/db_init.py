from __future__ import annotations

from pathlib import Path

import psycopg2

from config import AppConfig
from utils.retry import with_retry


def initialize_database(config: AppConfig) -> None:
    schema_path = Path(__file__).with_name("schemas.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")

    def _apply_schema() -> None:
        connection = psycopg2.connect(
            dbname=config.postgres_db,
            user=config.postgres_user,
            password=config.postgres_password,
            host=config.postgres_host,
            port=config.postgres_port,
        )
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(schema_sql)
        finally:
            connection.close()

    with_retry(_apply_schema)
