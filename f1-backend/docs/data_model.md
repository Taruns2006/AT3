# Data Model — F1 Telemetry Cassandra Design
# [AD] Advanced Databases

## 1. Why Apache Cassandra? (Cassandra vs SQL)

| Concern | PostgreSQL (SQL) | Apache Cassandra |
|---------|-----------------|-----------------|
| Write throughput at 20 Hz × 20 cars = 400 writes/s | Write amplification due to WAL + B-tree index updates | LSM tree: writes are appends to memtable → flushed to SSTables; very high throughput |
| Time-series reads ("last 60 s for car 44") | Requires index scan or table scan unless a time-index exists | Partition key maps directly to one replica set; O(1) lookup |
| Schema evolution (add `tyre_age_laps` column later) | ALTER TABLE is O(table size) — can lock writes | ALTER TABLE in Cassandra is O(1) — metadata only |
| Horizontal scaling | Requires read replicas + sharding complexity | Native ring topology; add nodes and data rebalances automatically |
| Aggregations (lap averages) | Native GROUP BY | Computed by the pipeline before storage; Cassandra reads are per-row |
| ACID transactions | Full ACID | No multi-row transactions; LWT (lightweight transactions) for CAS only |
| Leaderboard sort | `ORDER BY laps DESC` | Counters cannot be sorted in CQL; sort in the application layer |

**Summary**: For 400 writes/s of time-series sensor data with predictable primary-key access patterns, Cassandra's LSM-tree write model and partition-based data model outperform relational databases. We accept the trade-offs (no JOINs, no ad-hoc GROUP BY) because every query is known at design time.

---

## 2. Keyspace Design

```
CREATE KEYSPACE f1_telemetry
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
```

### SimpleStrategy vs NetworkTopologyStrategy [AD]

**SimpleStrategy** distributes replicas sequentially around the Cassandra token ring without regard to physical data centre boundaries. It is the correct choice for a **single data centre** (or single-node) development environment because:
- Configuration is minimal (only `replication_factor`).
- No rack or DC awareness overhead.
- RF=1 means each token range has exactly one replica; suitable for dev where data loss is acceptable.

**NetworkTopologyStrategy** specifies the replication factor **per data centre**:
```
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 3
}
```
This is **mandatory** for:
- Multi-data-centre deployments (replicate to DC2 for DR).
- Any production environment — it enables LOCAL_QUORUM reads/writes that stay within one DC, avoiding cross-DC latency.
- The optional 3-node cluster in `showcase/docker-compose.cluster.yml`.

We use SimpleStrategy RF=1 for dev. The schema comment and `docker-compose.cluster.yml` show the NetworkTopologyStrategy upgrade path.

---

## 3. Table Design and Partition Size Analysis [AD]

### 3.1 `telemetry` table

**Partition key**: `(race_id, car_number, lap_bucket)`

**Partition size analysis**:

| Parameter | Value |
|-----------|-------|
| Sensor rate | 20 Hz |
| Race duration | 2 hours = 7 200 s |
| Rows per car per race (no bucket) | 20 × 7 200 = **144 000 rows** |
| Estimated bytes per row | ~140 B (8 doubles + 4 ints + 2 text fields + metadata) |
| Uncompressed partition size | 144 000 × 140 B = **~20 MB** |
| With LZ4 compression (~2× ratio) | **~10 MB** |
| Cassandra guidance | < 100 MB, < 100 k rows per partition |
| At RF=1, 20-car race total | 20 × 20 MB = **400 MB** (fits) |

**Decision**: A `(race_id, car_number)` partition without bucketing stays under 20 MB compressed — within guidance. However, a 50-lap full-preset race at 20 Hz produces 50 × 2 min/lap × 120 s × 20 = 120 000 rows. This approaches the 100 k row guideline.

**We add a `lap_bucket` component** (`lap_number DIV 5`, grouping 5 laps per partition):
- Rows per bucket: 144 000 / 10 buckets ≈ **14 400 rows** — well under limits.
- Partition size: ~2 MB per bucket.
- Trade-off: history queries spanning bucket boundaries (e.g., the last 60 s straddles laps 9 and 10, buckets 1 and 2) require reading from 2 partitions. The writer computes affected buckets and the history query reads both. This is a 2× read in the worst case, acceptable because 60 s at 20 Hz = 1 200 rows.

### 3.2 `telemetry_latest`

One row per `(race_id, car_number)`. Always a single-row lookup. No size concern.

### 3.3 `race_car_counters`

Counter table. PK `(race_id, car_number)`.

**Why counters are in a separate table** [AD]:
Cassandra stores counter columns using a special internal CRDT (Conflict-free Replicated Data Type) representation that tracks per-replica deltas. This representation is **incompatible** with the storage model for regular columns. Cassandra enforces this at the schema level: a table either contains only counter columns (plus the primary key) or it contains only regular columns. Mixing them causes a schema error.

**Counter idempotency** [AD]:
Counter updates are **not idempotent**. A `UPDATE ... SET laps = laps + 1` that reaches the server but whose response is lost will be double-applied if retried. This is why:
1. Counters are incremented **only on discrete events** (`lap_completed`, `pit_exit`), never on every 20 Hz sensor tick.
2. Counter failures go to a **dead-letter log** for human review — they are never automatically retried.
3. The `execute_async` path for counters has no retry policy.

### 3.4 TWCS + TTL [AD]

**TimeWindowCompactionStrategy (TWCS)**:
- Groups SSTables by time window (1 hour here).
- Once a window closes, its SSTables are merged into one and never rewritten.
- Expired data (TTL) within old windows is reclaimed by dropping the entire SSTable file — no tombstone accumulation.
- Ideal for immutable, time-ordered writes (sensor telemetry).

**Why not STCS (SizeTieredCompactionStrategy)?**
STCS groups SSTables by size. For time-series data, old data constantly gets merged with new data, causing write amplification and preventing clean TTL reclamation.

**TTL = 7 days** on `telemetry`:
Raw 20 Hz data is bulky (~400 MB per race at RF=1). We retain 7 days for replay/demo purposes. Aggregated data (`lap_summary`, `predictions`) is retained longer or indefinitely.

**TTL = 5 minutes** on `predictions`:
Predictions older than 5 minutes are stale — the ML model runs every 1 s and the frontend only displays the latest.

---

## 4. Consistency Levels [AD]

| Operation | Level | Justification |
|-----------|-------|---------------|
| Ingestion (write) | LOCAL_ONE | Maximum throughput; occasional missed replica is recovered by read repair |
| API reads (single-node dev) | LOCAL_ONE | Single node; ONE == QUORUM |
| API reads (cluster setup) | LOCAL_QUORUM | Guarantees reading latest committed write within the DC |
| Counter increments | LOCAL_ONE | Counters use a separate merge mechanism; LOCAL_ONE is standard |

**LOCAL_ONE vs LOCAL_QUORUM trade-off**: LOCAL_ONE allows a read to succeed even if (RF-1) replicas are down. LOCAL_QUORUM requires `⌈RF/2⌉ + 1 = 2` replicas to respond (for RF=3). It provides strong consistency within the DC at the cost of higher read latency when a replica is slow.

---

## 5. Write Path [AD]

```
Application → Prepared Statement → Cassandra Node (coordinator)
  → Memtable (in-memory, all replicas)
  → Commit log (WAL, for durability)
  → SSTable (on-disk, when memtable flushes)
  → TWCS Compaction (periodically, per window)
```

vs SQL write path:
```
Application → SQL Parser → Query Planner → B-tree index update + WAL write
```

Cassandra's append-only design (no B-tree rebalancing) enables ~10× higher write throughput than PostgreSQL at equivalent hardware for pure-append workloads.

---

## 6. Leaderboard Design Decision

Cassandra counters cannot be used in `ORDER BY` or `WHERE` comparisons. The leaderboard endpoint:
1. Reads `race_car_counters` for all cars in a race (one CQL query per car, or `IN` clause — documented trade-off).
2. Sorts the result in Python: laps DESC, then by `completed_at` ASC (using `lap_summary` for the last lap time).
3. Returns the ranked list.

This is an intentional trade-off: using a dedicated leaderboard table with materialized views would require Cassandra Enterprise or manual maintenance. For a university demo with ≤ 20 cars, the application-side sort is fast and honest about the Cassandra limitation.
