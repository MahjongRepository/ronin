"""Root conftest: load test environment variables before any test collection."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.tests")
