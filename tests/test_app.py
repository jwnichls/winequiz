"""
Tests for app creation, configuration and the Celery integration
"""

import ssl

import redis
from flask import Flask

from winequiz import create_app, load_config_for_heroku
from winequiz.celery_app import celery


def test_heroku_config_comes_from_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://example:6379")
    monkeypatch.setenv("SECRET_KEY", "from-env")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@db.example:5432/winequiz")
    app = Flask(__name__)

    load_config_for_heroku(app)

    assert app.config["BROKER_URL"] == "redis://example:6379"
    assert app.config["RESULT_BACKEND"] == "redis://example:6379"
    assert app.config["SECRET_KEY"] == "from-env"
    assert app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] is False
    # SQLAlchemy only accepts the postgresql:// scheme
    assert app.config["SQLALCHEMY_DATABASE_URI"] == (
        "postgresql://user:pw@db.example:5432/winequiz"
    )


def test_heroku_config_keeps_postgresql_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db.example/postgres_db")
    app = Flask(__name__)

    load_config_for_heroku(app)

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql://user:pw@db.example/postgres_db"


def test_settings_file_from_environment(monkeypatch, tmp_path):
    settings = tmp_path / "settings.py"
    settings.write_text(
        "SECRET_KEY = 'from-file'\n"
        "BROKER_URL = None\n"
        "SQLALCHEMY_DATABASE_URI = 'sqlite://'\n"
    )
    monkeypatch.setenv("WINE_QUIZ_SETTINGS", str(settings))
    monkeypatch.delenv("ON_HEROKU", raising=False)

    app = create_app()

    assert app.config["SECRET_KEY"] == "from-file"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"


def test_blueprints_are_registered(app):
    assert {"admin", "api", "index", "quiz"} <= set(app.blueprints)
    assert app.url_map.bind("").match("/") == ("index.index", {})


def test_celery_uses_app_config(app):
    assert celery.app is app
    assert celery.conf["TESTING"] is True


def test_celery_tasks_run_in_app_context_synchronously_when_testing(app):
    @celery.task
    def current_app_name():
        from flask import current_app
        return current_app.name

    @celery.task
    def add(x, y):
        return x + y

    assert add.apply_async((2, 3)) == 5
    assert current_app_name.apply_async() == app.name


def test_heroku_tls_redis_skips_certificate_verification(monkeypatch):
    # Heroku Redis serves a self-signed certificate
    monkeypatch.setenv("REDIS_URL", "rediss://:pw@redis.example:9780")
    monkeypatch.setenv("DATABASE_URL", "postgres://db.example/winequiz")
    app = Flask(__name__)

    load_config_for_heroku(app)

    expected = "rediss://:pw@redis.example:9780?ssl_cert_reqs=none"
    assert app.config["BROKER_URL"] == expected
    assert app.config["RESULT_BACKEND"] == expected


def test_heroku_tls_redis_url_with_existing_query(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://:pw@redis.example:9780/0?socket_timeout=5")
    monkeypatch.setenv("DATABASE_URL", "postgres://db.example/winequiz")
    app = Flask(__name__)

    load_config_for_heroku(app)

    assert app.config["BROKER_URL"] == (
        "rediss://:pw@redis.example:9780/0?socket_timeout=5&ssl_cert_reqs=none"
    )


def test_tls_redis_url_creates_unverified_ssl_connection(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://:pw@redis.example:9780")
    monkeypatch.setenv("DATABASE_URL", "postgres://db.example/winequiz")
    app = Flask(__name__)
    load_config_for_heroku(app)

    connection = redis.Redis.from_url(app.config["BROKER_URL"]).connection_pool.make_connection()

    assert isinstance(connection, redis.SSLConnection)
    assert connection.cert_reqs == ssl.CERT_NONE
