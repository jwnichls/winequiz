"""
Base module for Wine Quiz
"""

import os

from flask import Flask
from flask_bootstrap import Bootstrap

from winequiz.celery_app import celery
from . import (
    db,
    index,
)


def create_app(test_config=None):
    """
    Creates and sets up the Flask app using the factory pattern.
    """

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    Bootstrap(app)

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

    # Initialize DB Module
    db.init_db(app)

    # Initialize Celery
    celery.init_app(app)

    # Register Index module
    app.register_blueprint(index.bp)
    app.add_url_rule("/", endpoint="index")

    return app
