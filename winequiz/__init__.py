"""
Base module for Wine Quiz
"""

import os

from flask import Flask
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO

from winequiz.celery_app import celery
from . import (
    admin,
    api,
    db,
    index,
    presence,
)


bootstrap = Bootstrap()
socketio = SocketIO()

from . import quiz, websocket


def load_config_for_heroku(app):
    """
    Load the configuration from Heroku environment variables
    """
    app.config['BROKER_URL'] = os.getenv('REDIS_URL')
    app.config['RESULT_BACKEND'] = os.getenv('REDIS_URL')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL'
    ).replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


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
        elif "ON_HEROKU" in os.environ:
            load_config_for_heroku(app)
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

    # Initialize tracking of connected competitors
    presence.init_app(app)

    # Initialize Celery
    celery.init_app(app)

    # Register Admin module
    app.register_blueprint(admin.bp)

    # Register API module
    app.register_blueprint(api.bp)

    # Register quiz module
    app.register_blueprint(quiz.bp)

    # Register Index module
    app.register_blueprint(index.bp)
    app.add_url_rule("/", endpoint="index")

    return app
