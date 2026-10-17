#!/usr/bin/env python3
"""
showcase/run_demo.py — Interactive teacher/viva presentation script.

Showcases Apache Cassandra concepts, CQL schema design, TWCS + TTL,
counter idempotency, pipeline data quality, and ML pit stop predictions.
[AD] Advanced Databases & [ML] Machine Learning
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(title: str) -> None:
    print(f"\n{CYAN}{'=' * 70}{RESET}")
    print(f"{BOLD}{GREEN}  {title}{RESET}")
    print(f"{CYAN}{'=' * 70}{RESET}\n")


def print_pause(text: str, delay: float = 0.5) -> None:
    print(text)
    time.sleep(delay)


def demo_cassandra_architecture():
    header("1. ARCHITECTURE & WHY APACHE CASSANDRA? (Cassandra vs SQL)")
    print_pause("""
  Concern                  PostgreSQL (SQL)                 Apache Cassandra (Wide-Column)
  -----------------------  -------------------------------  -------------------------------------
  Write throughput (20Hz)  B-tree index updates bottleneck  LSM-tree: Append-only commitlog & memtable
  Clustering & Partition   Single leader / sharding complex Distributed peer-to-peer (no SPOF)
  Time-series Compaction   Vacuum overhead & bloat          TimeWindowCompactionStrategy (TWCS)
  Data Expiry              Tombstone & index scans          TTL drops whole SSTables at window expiry
  Access Pattern           Ad-hoc JOIN queries              Query-first data modeling (1 table/query)
    """)


def demo_partition_sizing():
    header("2. PARTITION SIZE ANALYSIS & LAP-BUCKET DESIGN")
    print_pause("""
  At 20 Hz, a single car emits 72,000 readings per hour (144,000 rows over 2 hours).
  Row size ~ 140 bytes uncompressed (Snappy/LZ4 compresses to ~70 bytes).
  A single partition for an entire race would grow to > 20 MB and > 140,000 rows.
  
  Cassandra Best Practice: Keep partitions < 100 MB and < 100,000 cells.
  
  DESIGN SOLUTION:
    Partition Key: ((race_id, car_number, lap_bucket), sensor_timestamp)
    where lap_bucket = lap_number // 5.
    
    In a 50-lap race:
    - 10 buckets per car
    - Rows per bucket: ~14,400 rows (~1.5 MB compressed)
    - Perfectly bounded partitions for high-throughput reads and compaction!
    """)


def demo_twcs_and_ttl():
    header("3. TIME-WINDOW COMPACTION (TWCS) & TTL")
    print_pause("""
  Table: telemetry
  Compaction: TimeWindowCompactionStrategy (window_size = 1, unit = HOURS)
  Default TTL: 604800 (7 days)
  
  WHY TWCS + TTL?
  1. Writes within the same hour land in the same window's SSTable.
  2. Older SSTables are never rewritten or compacted against newer ones.
  3. When the 7-day TTL expires, the entire SSTable file can simply be unlinked
     from the filesystem without generating tombstones or compaction read-amplification!
    """)


def demo_counter_idempotency():
    header("4. CASSANDRA COUNTERS & IDEMPOTENCY WARNING")
    print_pause("""
  Table: race_car_counters (PRIMARY KEY: race_id, car_number)
  Columns: laps counter, pit_stops counter, total_pit_ms counter
  
  CRITICAL OPERATION WARNING:
  - Cassandra counters use CRDT delta updates: UPDATE ... SET laps = laps + 1
  - Counters are NOT IDEMPOTENT!
  - If a client network timeout occurs after the server incremented the counter,
    retrying the request will DOUBLE COUNT the event!
  
  DESIGN DECISION:
  - Counters are only incremented on discrete events (lap_completion, pit_exit),
    never on 20 Hz telemetry streams, and never with blind retries.
    """)


def demo_ml_and_quality():
    header("5. DATA QUALITY PIPELINE & ML PIT-STOP PREDICTIONS")
    meta_path = ROOT / "ml" / "models" / "model_metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"  Model Champion: {meta.get('model_name')}")
        print(f"  Features: {meta.get('features')}")
        print("  Validation Metrics:")
        metrics = meta.get("metrics", {})
        for k, v in metrics.items():
            print(f"    - {k}: {v}")
    else:
        print("  Model metadata available after training.")

    print_pause(
        "\n  Data Quality Pipeline: Quarantine isolates bad sensors (spikes, duplicates, NaN)"
    )
    print_pause("  Cleaned data guarantees zero training-serving skew.")


def main():
    print(f"\n{BOLD}{CYAN}F1 Telemetry & Apache Cassandra Showcase Demo{RESET}\n")
    demo_cassandra_architecture()
    demo_partition_sizing()
    demo_twcs_and_ttl()
    demo_counter_idempotency()
    demo_ml_and_quality()
    print(f"\n{GREEN}{BOLD}Showcase presentation complete.{RESET}\n")


if __name__ == "__main__":
    main()
