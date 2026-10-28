"""
Tests for tracking connected competitors in Redis (winequiz.presence)
"""

import fakeredis
from flask import Flask

from winequiz import presence


def test_single_connection(app):
    presence.add_socket(1, "sid-a")
    assert presence.remove_socket(1, "sid-a") is True


def test_last_of_several_connections(app):
    presence.add_socket(1, "sid-a")
    presence.add_socket(1, "sid-b")

    assert presence.remove_socket(1, "sid-a") is False
    assert presence.remove_socket(1, "sid-b") is True


def test_competitors_are_tracked_separately(app):
    presence.add_socket(1, "sid-a")
    presence.add_socket(2, "sid-b")

    assert presence.remove_socket(2, "sid-b") is True
    assert presence.remove_socket(1, "sid-a") is True


def test_same_socket_joining_twice_is_one_connection(app):
    presence.add_socket(1, "sid-a")
    presence.add_socket(1, "sid-a")

    assert presence.remove_socket(1, "sid-a") is True


def test_unknown_socket_counts_as_last_connection(app):
    assert presence.remove_socket(1, "never-joined") is True


def test_connections_expire(app):
    presence.add_socket(1, "sid-a")

    ttl = presence.get_redis().ttl(presence.SOCKETS_KEY.format(1))
    assert 0 < ttl <= presence.SOCKETS_EXPIRY


def test_connections_are_shared_between_processes():
    server = fakeredis.FakeServer()
    process_a, process_b = Flask("a"), Flask("b")
    process_a.extensions["presence_redis"] = fakeredis.FakeRedis(server=server)
    process_b.extensions["presence_redis"] = fakeredis.FakeRedis(server=server)

    with process_a.app_context():
        presence.add_socket(1, "sid-a")
    with process_b.app_context():
        presence.add_socket(1, "sid-b")

    with process_a.app_context():
        assert presence.remove_socket(1, "sid-a") is False
    with process_b.app_context():
        assert presence.remove_socket(1, "sid-b") is True


def test_init_app_uses_broker_url():
    app = Flask(__name__)
    app.config["BROKER_URL"] = "redis://redis.example:6380/2"

    presence.init_app(app)

    kwargs = app.extensions["presence_redis"].connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("redis.example", 6380, 2)


def test_without_redis_every_disconnect_is_the_last():
    app = Flask(__name__)
    app.config["BROKER_URL"] = None
    presence.init_app(app)

    with app.app_context():
        presence.add_socket(1, "sid-a")
        presence.add_socket(1, "sid-b")
        assert presence.remove_socket(1, "sid-a") is True
