"""
Base module for Wine Quiz
"""

import os

from flask import Flask
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO

from winequiz.celery_app import celery
from . import (
    db,
    index,
)


bootstrap = Bootstrap()
socketio = SocketIO()

from . import websocket

def create_app(test_config=None, main=True):
    """
    Creates and sets up the Flask app using the factory pattern.
    """

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    bootstrap.init_app(app)

    if test_config is None:
        # load config from an environment variable, if it exists
        if "WINE_QUIZ_SETTINGS" in os.environ:
            app.config.from_envvar("WINE_QUIZ_SETTINGS")
        # overwrite with the instance config, if it exists
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize SocketIO
    if main:
        socketio.init_app(app,
                          message_queue=app.config['BROKER_URL'])
    else:
        socketio.init_app(None,
                          message_queue=app.config['SOCKETIO_MESSAGE_QUEUE'],
                          async_mode='threading')

    # Initialize DB Module
    db.init_db(app)

    # Initialize Celery
    celery.init_app(app)

    # Register Index module
    app.register_blueprint(index.bp)
    app.add_url_rule("/", endpoint="index")

    return app
