"""
Specifies the setup and periodic tasks for Celery-run services
"""

import redis

from winequiz.celery_app import celery
from winequiz import create_app
from . import socketio

app = create_app()
app.app_context().push()


@celery.task
def emit_ping():
    """
    Emit a broadcast ping to all connected sockets
    """
    redis_client = redis.Redis()
    ping_counter_value = redis_client.get('PING_COUNTER_KEY')
    ping_counter = 0
    if ping_counter_value is not None:
        ping_counter = int(ping_counter_value)
    
    socketio.emit('ping', {'value': ping_counter})
    
    ping_counter += 1
    redis_client.set('PING_COUNTER_KEY', ping_counter)


@celery.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Set up periodic tasks that will be triggered by celery beat
    """
    sender.add_periodic_task(5.0, emit_ping.s(), name="send ping")
