"""
conftest.py — Pytest configuration and shared fixtures.

Cassandra tests are marked with @pytest.mark.cassandra.
They skip automatically if Cassandra is unreachable on CASSANDRA_HOSTS:CASSANDRA_PORT.
"""

from __future__ import annotations

import os
import socket

import pytest


def _cassandra_reachable() -> bool:
    host = os.getenv("CASSANDRA_HOSTS", "127.0.0.1").split(",")[0].strip()
    port = int(os.getenv("CASSANDRA_PORT", "9042"))
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


_CASSANDRA_AVAILABLE = _cassandra_reachable()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "cassandra: tests requiring a live Cassandra instance (auto-skipped if unreachable)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip cassandra-marked tests if the database is not reachable."""
    if _CASSANDRA_AVAILABLE:
        return
    skip_cassandra = pytest.mark.skip(
        reason="Cassandra not reachable — set CASSANDRA_HOSTS and start docker compose"
    )
    for item in items:
        if "cassandra" in item.keywords:
            item.add_marker(skip_cassandra)
