"""
ingestion/connection.py — Cassandra session manager and connection pool.

Handles cluster discovery, retry policies, keyspace creation, and provides
a fallback mode when Cassandra is unreachable.
[AD] Advanced Databases
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("cassandra_connection")

_cluster = None
_session = None


def get_cassandra_session(keyspace: str = "f1_telemetry", auto_keyspace: bool = True) -> Any | None:
    """
    Returns an active cassandra.cluster.Session, or None if Cassandra is unavailable.
    """
    global _cluster, _session

    if _session is not None and not _session.is_shutdown:
        return _session

    hosts_env = os.getenv("CASSANDRA_HOSTS", "127.0.0.1")
    port = int(os.getenv("CASSANDRA_PORT", "9042"))
    hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]

    try:
        from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile  # type: ignore[import-untyped]
        from cassandra.policies import DCAwareRoundRobinPolicy  # type: ignore[import-untyped]

        # In Python 3.12+, asyncore is removed, so AsyncioConnection must be used
        try:
            from cassandra.io.asyncioreactor import AsyncioConnection  # type: ignore[import-untyped]

            conn_kwargs = {"connection_class": AsyncioConnection}
        except Exception:
            conn_kwargs = {}

        profile = ExecutionProfile(
            load_balancing_policy=DCAwareRoundRobinPolicy(),
            request_timeout=15.0,
        )

        _cluster = Cluster(
            hosts,
            port=port,
            connect_timeout=5.0,
            execution_profiles={EXEC_PROFILE_DEFAULT: profile},
            **conn_kwargs,
        )
        session = _cluster.connect()

        if auto_keyspace:
            session.execute(
                f"""
                CREATE KEYSPACE IF NOT EXISTS {keyspace}
                WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
                AND durable_writes = true;
                """
            )
            session.set_keyspace(keyspace)

        _session = session
        log.info(f"Connected to Cassandra on {hosts}:{port}, keyspace={keyspace}")
        return _session

    except Exception as exc:
        log.warning(
            f"Could not connect to Cassandra on {hosts_env}:{port} ({exc}). Fallback active."
        )
        return None


def close_cassandra() -> None:
    global _cluster, _session
    if _session:
        with contextlib.suppress(Exception):
            _session.shutdown()
        _session = None
    if _cluster:
        with contextlib.suppress(Exception):
            _cluster.shutdown()
        _cluster = None
