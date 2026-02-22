"""Root conftest: load test environment variables and configure structlog for tests."""

from pathlib import Path

import pytest
import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.tests")

# Configure structlog to route through stdlib logging so caplog works in tests.
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=False,
)


@pytest.fixture(autouse=True)
def _clear_log_context():
    """Prevent context leaking between tests."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
