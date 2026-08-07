"""Development entry point for the InterVue AI backend.

Run with:  python run.py
Serves the app via uvicorn with hot-reload and prints the docs URL.
"""

import uvicorn

from app.utils.config import get_settings


def main() -> None:
    """Boot the FastAPI application for local development."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    main()
