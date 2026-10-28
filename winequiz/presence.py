"""
Tracks which sockets each competitor is connected with, so we can tell
when their last connection goes away. The data lives in Redis so that it
is shared by every server process.
"""

import redis
from flask import current_app


SOCKETS_KEY = "winequiz:competitor:{}:sockets"

# Forget connections that a crashed process never got to clean up
SOCKETS_EXPIRY = 24 * 60 * 60


def init_app(app):
    """
    Connect to the Redis server in the app's BROKER_URL, if there is one
    """
    url = app.config.get("BROKER_URL")
    app.extensions["presence_redis"] = redis.Redis.from_url(url) if url else None


def get_redis():
    return current_app.extensions.get("presence_redis")


def add_socket(competitor_id, sid):
    """
    Record that a competitor is connected with the given socket
    """
    client = get_redis()
    if client is None:
        return

    key = SOCKETS_KEY.format(competitor_id)
    with client.pipeline() as pipe:
        pipe.sadd(key, sid)
        pipe.expire(key, SOCKETS_EXPIRY)
        pipe.execute()


def remove_socket(competitor_id, sid):
    """
    Record that a competitor's socket has disconnected. Returns True if
    that was the competitor's last connection.
    """
    client = get_redis()
    if client is None:
        return True

    key = SOCKETS_KEY.format(competitor_id)
    with client.pipeline() as pipe:
        pipe.srem(key, sid)
        pipe.scard(key)
        _, remaining = pipe.execute()
    return remaining == 0
