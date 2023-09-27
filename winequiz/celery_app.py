"""
Wraps celery in an object with extra methods that help with
integration between celery and flask.
"""

from celery import Celery
import flask


class FlaskCelery(Celery):
    """
    A wrapper for the celery object that helps integrate with Flask
    """

    def __init__(self, *args, **kwargs):
        """
        Construct the Celery wrapper object
        """
        super().__init__(*args, **kwargs)
        self.patch_task()

        if "app" in kwargs:
            self.init_app(kwargs["app"])

    def patch_task(self):
        """
        Patch the celery task object to work with Flask app contexts
        """
        TaskBase = self.Task
        _celery = self

        class ContextTask(TaskBase):
            """
            Replacement for celery TaskBase that integrates with Flask
            app contexts
            """

            abstract = True

            def __call__(self, *args, **kwargs):
                if flask.has_app_context():
                    return TaskBase.__call__(self, *args, **kwargs)

                with _celery.app.app_context():
                    return TaskBase.__call__(self, *args, **kwargs)

            def apply_async(self, *args, **kwargs):
                """
                Testing-specific implementation of apply_async
                """
                if _celery.app.config["TESTING"]:
                    # When testing, we do not want calls to apply_async to
                    # actually run asynchronously, which would require celery
                    # infrastructure in the test environment.  Instead, we
                    # turn apply_async into a synchronous run call. This works
                    # fine unless there are no arguments, which is why I found
                    # the conditional necessary (JWN)
                    if len(args) == 1:
                        return self.run(*(args[0]), **kwargs)
                    return self.run(*args, **kwargs)

                return super().apply_async(*args, **kwargs)

        # pylint: disable=invalid-name
        self.Task = ContextTask

    def init_app(self, app):
        """
        Initialize celery with the Flask app
        """
        self.app = app
        self.config_from_object(app.config)


celery = FlaskCelery()
