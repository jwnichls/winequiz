"""
Checks that the Alembic migrations build the schema the models expect.

These only run against PostgreSQL (set TEST_DATABASE_URL), since the
migrations are written for the production database.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from winequiz.db import db

from tests.helpers import USING_POSTGRES


pytestmark = pytest.mark.skipif(not USING_POSTGRES, reason="needs TEST_DATABASE_URL (PostgreSQL)")

MIGRATIONS = str(Path(__file__).parent.parent / "migrations")


@pytest.fixture
def empty_database(app):
    """
    The database with no tables, as before the first deploy
    """
    db.drop_all()
    yield
    db.session.remove()
    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    db.drop_all()
    db.create_all()  # what the app fixture expects to tear down


def schema_differences():
    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(context, db.metadata)


def test_migrations_match_models(empty_database):
    upgrade(directory=MIGRATIONS)

    assert schema_differences() == []


def test_migrations_downgrade_cleanly(empty_database):
    upgrade(directory=MIGRATIONS)
    downgrade(directory=MIGRATIONS, revision="base")

    with db.engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )).scalars().all()
    assert set(tables) <= {"alembic_version"}
