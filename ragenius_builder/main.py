"""
Quarantine shim for the archived builder FastAPI prototype.

The supported builder/admin runtime is the Flask application at
`ragenius_builder/flask_scaffold/app.py`.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "ragenius_builder/main.py is archived. "
        "Run the builder from ragenius_builder/flask_scaffold/app.py instead."
    )


if __name__ == "__main__":
    main()
