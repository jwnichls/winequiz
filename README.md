# Wine Quiz

A multi-user wine quiz web-based game.

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

## Tests

```sh
uv run pytest
```

Tests use an in-memory SQLite database by default. To run them against
PostgreSQL, as CI does, point `TEST_DATABASE_URL` at an empty database
(this also runs the migration checks):

```sh
TEST_DATABASE_URL=postgresql://localhost/winequiz_test uv run pytest
```

Tests marked `xfail` document known bugs. They're strict, so fixing one
of those bugs makes its test fail until the marker is removed.

## Deployment

Pushes to `main` run the tests in GitHub Actions
(`.github/workflows/tests.yml`). Heroku deploys `main` automatically once
those checks pass.
