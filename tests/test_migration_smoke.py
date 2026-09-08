"""Smoke da migration contra o PostgreSQL local descartável."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

DATABASE_URL = os.getenv(
    "TRT_EXTRACTOR_DATABASE_URL",
    "postgresql://trt_extractor_dev:trt_extractor_dev_only@127.0.0.1:54329/"
    "trt_extractor_smoke",
)
MIGRATION = Path(__file__).parents[1] / "migrations" / "001_inicial.sql"


def _database_url_local(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != 54329
        or parsed.path != "/trt_extractor_smoke"
    ):
        raise ValueError(
            "TRT_EXTRACTOR_DATABASE_URL deve apontar para o PostgreSQL descartável "
            "em loopback na porta 54329 e banco trt_extractor_smoke"
        )
    return url


@pytest.mark.parametrize(
    ("url", "aceita"),
    [
        (DATABASE_URL, True),
        ("postgresql://user:password@db.example/trt_extractor_smoke", False),
        ("postgresql://user:password@127.0.0.1:54329/outro_banco", False),
    ],
)
def test_database_url_do_smoke_e_restrita_ao_banco_local(
    url: str, *, aceita: bool
) -> None:
    if aceita:
        assert _database_url_local(url) == url
    else:
        with pytest.raises(ValueError, match="loopback"):
            _database_url_local(url)


@pytest.mark.skipif(
    os.getenv("TRT_EXTRACTOR_RUN_LOCAL_DB_SMOKE") != "1",
    reason="smoke local desabilitado; defina TRT_EXTRACTOR_RUN_LOCAL_DB_SMOKE=1",
)
def test_initial_migration_applies_to_local_postgres() -> None:
    try:
        connection = psycopg.connect(_database_url_local(DATABASE_URL), autocommit=True)
    except (ValueError, psycopg.OperationalError):
        pytest.fail(
            "PostgreSQL local indisponível em 127.0.0.1:54329. "
            "Execute `docker compose up -d --wait` antes do smoke."
        )

    with connection:
        # O banco do compose usa tmpfs; ainda assim, cada execução começa limpa.
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
        connection.execute(MIGRATION.read_text(encoding="utf-8"))

        tables = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()

    assert {"job", "processo", "transicao_permitida"} <= {row[0] for row in tables}
