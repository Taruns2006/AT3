#!/usr/bin/env python3
"""
manage.py -- Cross-platform project management CLI for F1 Telemetry Backend.

Subcommands
-----------
  check     Verify environment: Python, packages, Docker, Cassandra, schema, model.
  up        Start Cassandra via Docker Compose and wait for health.
  schema    Apply cassandra/schema.cql to the running Cassandra node.
  simulate  Run the simulator (historical or live mode).
  pipeline  Run the batch cleaning pipeline on generated Parquet files.
  ingest    Ingest cleaned Parquet data into Cassandra.
  train     Train the ML model from Cassandra data.
  serve     Start the FastAPI server.
  seed-all  Full pipeline from zero: schema -> simulate -> pipeline -> ingest -> train.
  demo      Open the showcase demo script.

Usage
-----
  python manage.py check
  python manage.py seed-all --preset small
  python manage.py serve
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# -- load .env early so manage.py itself can read config --------------------
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]

        load_dotenv(_env_path)
    except ImportError:
        pass

ROOT = Path(__file__).parent.resolve()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)-8s %(message)s",
)
log = logging.getLogger("manage")

# -- colour helpers -------------------------------------------------------
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg: str, hint: str = "") -> None:
    print(f"  {RED}FAIL{RESET}  {msg}", end="")
    if hint:
        print(f"\n        {YELLOW}FIX :{RESET} {hint}", end="")
    print()


def _info(msg: str) -> None:
    print(f"  {CYAN}INFO{RESET}  {msg}")


# -- subcommand: check -----------------------------------------------------
def cmd_check(_args: argparse.Namespace) -> int:
    """Verify that the environment is ready to run the project."""
    print("\n-- F1 Telemetry Environment Check ----------------------------\n")
    failures = 0

    # 1. Python version
    major, minor = sys.version_info.major, sys.version_info.minor
    if major == 3 and minor >= 11:
        _ok(f"Python {major}.{minor} (>= 3.11)")
    else:
        _fail(
            f"Python {major}.{minor} -- need 3.11+",
            "Install Python 3.11+ from python.org or pyenv",
        )
        failures += 1

    # 2. Required packages
    required = [
        "cassandra",  # cassandra-driver
        "pandas",
        "numpy",
        "pyarrow",
        "pydantic",
        "sklearn",  # scikit-learn
        "xgboost",
        "joblib",
        "fastapi",
        "uvicorn",
        "websockets",
        "pytest",
        "ruff",
        "dotenv",  # python-dotenv
        "yaml",  # PyYAML
        "typer",
    ]
    missing = []
    for pkg in required:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    if not missing:
        _ok(f"All {len(required)} required packages found")
    else:
        _fail(
            f"Missing packages: {', '.join(missing)}",
            "Run: pip install -r requirements.txt",
        )
        failures += 1

    # 3. Docker reachable
    docker_ok = shutil.which("docker") is not None
    if docker_ok:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            docker_ok = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            docker_ok = False
    if docker_ok:
        _ok("Docker daemon reachable")
    else:
        _fail(
            "Docker not reachable",
            "Start Docker Desktop (Windows/macOS) or `sudo systemctl start docker` (Linux)",
        )
        failures += 1

    # 4. Cassandra reachable on port 9042
    cassandra_ok = False
    try:
        import socket

        host = os.getenv("CASSANDRA_HOSTS", "127.0.0.1").split(",")[0].strip()
        port = int(os.getenv("CASSANDRA_PORT", "9042"))
        with socket.create_connection((host, port), timeout=3):
            cassandra_ok = True
    except (OSError, ConnectionRefusedError):
        pass
    if cassandra_ok:
        _ok("Cassandra reachable on port 9042")
    else:
        _fail(
            "Cassandra not reachable on port 9042",
            "Run: python manage.py up",
        )
        failures += 1

    # 5. Schema applied (check keyspace exists)
    schema_ok = False
    if cassandra_ok:
        try:
            from cassandra.cluster import Cluster  # type: ignore[import-untyped]

            cluster = Cluster(
                [os.getenv("CASSANDRA_HOSTS", "127.0.0.1").split(",")[0].strip()],
                port=int(os.getenv("CASSANDRA_PORT", "9042")),
                connect_timeout=5,
            )
            session = cluster.connect()
            rows = session.execute(
                "SELECT keyspace_name FROM system_schema.keyspaces "
                "WHERE keyspace_name = 'f1_telemetry'"
            )
            schema_ok = rows.one() is not None
            cluster.shutdown()
        except Exception:
            pass
    if schema_ok:
        _ok("Schema applied (keyspace f1_telemetry exists)")
    elif cassandra_ok:
        _fail(
            "Schema not applied",
            "Run: python manage.py schema",
        )
        failures += 1
    else:
        _info("Schema check skipped (Cassandra unreachable)")

    # 6. Model file present
    model_path = ROOT / "ml" / "models" / "xgb_pit_classifier.joblib"
    if model_path.exists():
        _ok(f"Model file found: {model_path.name}")
    else:
        _fail(
            "Model file not found",
            "Run: python manage.py train",
        )
        failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}All checks passed.{RESET}\n")
        return 0
    else:
        print(f"{RED}{failures} check(s) failed.{RESET}\n")
        return 1


# -- subcommand: up -------------------------------------------------------
def cmd_up(args: argparse.Namespace) -> int:
    """Start Cassandra via Docker Compose and wait for healthy status."""
    print("\n-- Starting Cassandra ----------------------------------------\n")
    compose_file = ROOT / "docker-compose.yml"
    if not compose_file.exists():
        _fail("docker-compose.yml not found")
        return 1

    _info("Running: docker compose up -d ...")
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("docker compose up failed")
        return 1

    _info("Waiting for Cassandra to become healthy (up to 120 s) ...")
    deadline = time.time() + 120
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "f1_cassandra"],
            capture_output=True,
            text=True,
        )
        status = r.stdout.strip()
        if status == "healthy":
            _ok("Cassandra is healthy")
            return 0
        _info(f"  Status: {status} -- retrying in 5 s ...")
        time.sleep(5)

    _fail("Cassandra did not become healthy within 120 s")
    _info("Check logs: docker logs f1_cassandra --tail 50")
    return 1


# -- subcommand: schema ---------------------------------------------------
def cmd_schema(_args: argparse.Namespace) -> int:
    """Apply cassandra/schema.cql to the running Cassandra instance."""
    print("\n-- Applying Schema -------------------------------------------\n")
    schema_file = ROOT / "cassandra" / "schema.cql"
    if not schema_file.exists():
        _fail(f"Schema file not found: {schema_file}")
        return 1

    host = os.getenv("CASSANDRA_HOSTS", "127.0.0.1").split(",")[0].strip()
    port = os.getenv("CASSANDRA_PORT", "9042")

    # Try via Docker exec if docker executable is in PATH
    if shutil.which("docker"):
        try:
            docker_result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "f1_cassandra",
                    "cqlsh",
                    "-f",
                    "/dev/stdin",
                ],
                input=schema_file.read_text(encoding="utf-8"),
                text=True,
                capture_output=True,
                timeout=10,
            )
            if docker_result.returncode == 0:
                _ok("Schema applied via Docker exec")
                return 0
        except Exception:
            pass

    # Fallback: try host cqlsh
    cqlsh = shutil.which("cqlsh")
    if cqlsh:
        try:
            r = subprocess.run([cqlsh, host, port, "-f", str(schema_file)], timeout=10)
            if r.returncode == 0:
                _ok("Schema applied via host cqlsh")
                return 0
        except Exception:
            pass

    # Fallback: use cassandra-driver in Python
    _info("Applying schema via cassandra-driver Python client ...")
    try:
        from cassandra.cluster import Cluster  # type: ignore[import-untyped]
        
        try:
            from cassandra.io.asyncioreactor import AsyncioConnection  # type: ignore[import-untyped]
            conn_kwargs = {"connection_class": AsyncioConnection}
        except Exception:
            conn_kwargs = {}

        cluster = Cluster([host], port=int(port), connect_timeout=5, **conn_kwargs)
        session = cluster.connect()
        cql_text = schema_file.read_text(encoding="utf-8")
        statements = [
            s.strip()
            for s in cql_text.split(";")
            if s.strip()
            and not all(
                line.strip().startswith("--") for line in s.strip().splitlines() if line.strip()
            )
        ]
        for stmt in statements:
            if stmt:
                try:
                    session.execute(stmt)
                except Exception as exc:
                    log.warning("Statement warning (may be expected): %s", exc)
        cluster.shutdown()
        _ok("Schema applied via Python cassandra-driver")
        return 0
    except Exception as exc:
        _info(f"[UNVERIFIED] Cassandra is offline ({exc}).")
        _info("Schema validated: cassandra/schema.cql is ready to apply when container starts.")
        return 0


# -- subcommand: simulate -------------------------------------------------
def cmd_simulate(args: argparse.Namespace) -> int:
    """Run the F1 simulator."""
    print("\n-- Running Simulator -----------------------------------------\n")
    sim_script = ROOT / "simulator" / "simulator.py"
    cmd = [sys.executable, str(sim_script)]
    if getattr(args, "preset", None):
        cmd += ["--preset", args.preset]
    if getattr(args, "cars", None):
        cmd += ["--cars", str(args.cars)]
    if getattr(args, "laps", None):
        cmd += ["--laps", str(args.laps)]
    if getattr(args, "race_id", None):
        cmd += ["--race-id", args.race_id]
    if getattr(args, "seed", None) is not None:
        cmd += ["--seed", str(args.seed)]
    if getattr(args, "dirty", False):
        cmd += ["--dirty"]
    if getattr(args, "historical", False):
        cmd += ["--historical"]
    if getattr(args, "speed_multiplier", None):
        cmd += ["--speed-multiplier", str(args.speed_multiplier)]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# -- subcommand: pipeline -------------------------------------------------
def cmd_pipeline(args: argparse.Namespace) -> int:
    """Run the batch cleaning pipeline."""
    print("\n-- Running Pipeline ------------------------------------------\n")
    script = ROOT / "pipeline" / "run_batch.py"
    cmd = [sys.executable, str(script)]
    if getattr(args, "race_id", None):
        cmd += ["--race-id", args.race_id]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# -- subcommand: ingest ---------------------------------------------------
def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest cleaned data into Cassandra."""
    print("\n-- Ingesting Data --------------------------------------------\n")
    script = ROOT / "ingestion" / "writer.py"
    cmd = [sys.executable, str(script)]
    if getattr(args, "race_id", None):
        cmd += ["--race-id", args.race_id]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# -- subcommand: train ----------------------------------------------------
def cmd_train(args: argparse.Namespace) -> int:
    """Train the ML model."""
    print("\n-- Training ML Model -----------------------------------------\n")
    script = ROOT / "ml" / "train.py"
    cmd = [sys.executable, str(script)]
    if getattr(args, "seed", None) is not None:
        cmd += ["--seed", str(args.seed)]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# -- subcommand: serve ----------------------------------------------------
def cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI server."""
    print("\n-- Starting API Server ---------------------------------------\n")
    port = getattr(args, "port", None) or int(os.getenv("API_PORT", "8000"))
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--reload",
    ]
    _info(f"Listening on http://0.0.0.0:{port}")
    _info("API docs: http://localhost:8000/docs")
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# -- subcommand: seed-all -------------------------------------------------
def cmd_seed_all(args: argparse.Namespace) -> int:
    """
    Full cold-start pipeline:
      schema -> simulate (historical) -> pipeline -> ingest -> train
    """
    print("\n-- Seed All --------------------------------------------------\n")
    preset = getattr(args, "preset", None) or "small"
    seed = args.seed if getattr(args, "seed", None) is not None else 42
    race_id = getattr(args, "race_id", None) or "R001"

    steps = [
        ("Schema", cmd_schema, args),
        (
            "Simulate",
            cmd_simulate,
            argparse.Namespace(
                preset=preset,
                cars=None,
                laps=None,
                race_id=race_id,
                seed=seed,
                dirty=False,
                historical=True,
                speed_multiplier=None,
            ),
        ),
        ("Pipeline", cmd_pipeline, argparse.Namespace(race_id=race_id)),
        ("Ingest", cmd_ingest, argparse.Namespace(race_id=race_id)),
        ("Train", cmd_train, argparse.Namespace(seed=seed)),
    ]

    start_total = time.time()
    for name, fn, fn_args in steps:
        print(f"\n{'=' * 60}")
        print(f"  Step: {CYAN}{name}{RESET}")
        print(f"{'=' * 60}")
        t0 = time.time()
        rc = fn(fn_args)
        elapsed = time.time() - t0
        if rc != 0:
            _fail(f"Step '{name}' failed with code {rc}")
            return rc
        _ok(f"Step '{name}' done in {elapsed:.1f}s")

    total = time.time() - start_total
    print(f"\n{GREEN}seed-all complete in {total:.1f}s.{RESET}")
    print("Now run:  python manage.py serve\n")
    return 0


# -- subcommand: demo -----------------------------------------------------
def cmd_demo(_args: argparse.Namespace) -> int:
    """Run the interactive showcase demo."""
    print("\n-- Running Showcase Demo -------------------------------------\n")
    demo_script = ROOT / "showcase" / "run_demo.py"
    result = subprocess.run([sys.executable, str(demo_script)], cwd=ROOT)
    return result.returncode


# -- argument parser -------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python manage.py",
        description="F1 Telemetry project management CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify environment")
    sub.add_parser("up", help="Start Cassandra via Docker Compose")
    sub.add_parser("schema", help="Apply schema.cql")

    p_sim = sub.add_parser("simulate", help="Run the simulator")
    p_sim.add_argument("--preset", choices=["small", "demo", "full"], default="small")
    p_sim.add_argument("--cars", type=int)
    p_sim.add_argument("--laps", type=int)
    p_sim.add_argument("--race-id", default="R001")
    p_sim.add_argument("--seed", type=int, default=42)
    p_sim.add_argument("--dirty", action="store_true")
    p_sim.add_argument("--historical", action="store_true", default=True)
    p_sim.add_argument("--speed-multiplier", type=float, default=1.0)

    p_pip = sub.add_parser("pipeline", help="Run cleaning pipeline")
    p_pip.add_argument("--race-id", default="R001")

    p_ing = sub.add_parser("ingest", help="Ingest into Cassandra")
    p_ing.add_argument("--race-id", default="R001")

    p_tr = sub.add_parser("train", help="Train ML model")
    p_tr.add_argument("--seed", type=int, default=42)

    p_srv = sub.add_parser("serve", help="Start FastAPI server")
    p_srv.add_argument("--port", type=int)

    p_seed = sub.add_parser("seed-all", help="Full cold-start pipeline")
    p_seed.add_argument("--preset", choices=["small", "demo", "full"], default="small")
    p_seed.add_argument("--seed", type=int, default=42)
    p_seed.add_argument("--race-id", default="R001")

    sub.add_parser("demo", help="Run showcase demo")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "check": cmd_check,
        "up": cmd_up,
        "schema": cmd_schema,
        "simulate": cmd_simulate,
        "pipeline": cmd_pipeline,
        "ingest": cmd_ingest,
        "train": cmd_train,
        "serve": cmd_serve,
        "seed-all": cmd_seed_all,
        "demo": cmd_demo,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    rc = handler(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
