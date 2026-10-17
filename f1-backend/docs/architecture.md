# Architecture — F1 Telemetry Pipeline

## System Architecture Diagram

```mermaid
flowchart LR
    SIM["🏎️ Simulator\n(20 Hz, 5–20 cars)\nsimulator.py"]
    RAW["📦 Raw Landing Zone\nParquet (partitioned\nby race_id)\ndata/raw/"]
    VAL["🔍 Validate\npydantic v2\npipeline/validate.py"]
    QUA["🚫 Quarantine\nParquet + reason code\ndata/quarantine/"]
    CLN["🧹 Clean\ndedupe · fill · outlier\npipeline/clean.py"]
    ENR["⚙️ Enrich\nlap/sector/tire/G-load\npipeline/enrich.py"]

    subgraph CASS["🗃️ Cassandra 4.1 (f1_telemetry keyspace)"]
        TEL["telemetry\n(race,car,lap_bucket)\n+ TWCS + TTL 7d"]
        LAT["telemetry_latest\n(race,car) — 1 row"]
        LAP["lap_summary\n(race,car,lap)"]
        CNT["race_car_counters\nCOUNTER table"]
        PRD["predictions\nTTL 5 min"]
        QSM["quality_summary"]
    end

    ML["🤖 ML Feature Extract\nml/extract.py\nml/features.py"]
    TRN["📊 Train\nLogReg → RF → XGBoost\nml/train.py"]
    INF["⚡ Predict Live\nml/predict_live.py"]

    API["🌐 FastAPI\napi/main.py\nREST + WebSocket"]
    FE["📺 Frontend\nf1-frontend/\ndashboard.html"]

    SIM -->|"Parquet\n--historical"| RAW
    SIM -->|"streaming\nmicro-batch 200ms"| VAL
    RAW --> VAL
    VAL -->|"invalid"| QUA
    VAL -->|"valid"| CLN
    CLN --> ENR
    ENR --> TEL & LAT & LAP & CNT & QSM
    TEL & LAT --> ML
    ML --> TRN
    TRN -->|"xgb_pit_classifier.joblib"| INF
    INF --> PRD
    TEL & LAT & LAP & CNT & PRD & QSM --> API
    API -->|"REST JSON"| FE
    API -->|"WebSocket\ntelemetry@10Hz\nprediction@1s\nleaderboard@2s\nquality@10s"| FE
```

## Data Flow Summary

| Stage | Module | Input | Output |
|-------|--------|-------|--------|
| **Simulation** [DE] | `simulator/simulator.py` | CLI args | Parquet files in `data/raw/` |
| **Validation** [DE] | `pipeline/validate.py` | Parquet | Valid rows + quarantine |
| **Cleaning** [DE] | `pipeline/clean.py` | Valid rows | Deduplicated, imputed, outlier-corrected rows |
| **Enrichment** [DE] | `pipeline/enrich.py` | Cleaned rows | Rows + lap_number, sector, tire_wear_rate, G-cumulative, etc. |
| **Ingestion** [AD] | `ingestion/writer.py` | Enriched rows | Written to Cassandra (4 tables + counters) |
| **Feature extraction** [ML] | `ml/extract.py` + `ml/features.py` | Cassandra rows | Feature matrix (pandas DataFrame) |
| **Training** [ML] | `ml/train.py` | Feature matrix | Saved model `.joblib` |
| **Live inference** [ML] | `ml/predict_live.py` | Cassandra latest | `predictions` table row |
| **API** [AD] | `api/main.py` | Cassandra | JSON / WebSocket |

## Key Design Decisions

1. **Query-first Cassandra tables**: every table exists to serve one specific access pattern. No ad-hoc queries.
2. **No Kafka/message broker**: at 400 writes/s, a direct Python → Cassandra pipeline is sufficient for this scale. A Kafka adapter would add value above 10 000 writes/s.
3. **Lap bucket partitioning**: keeps `telemetry` partitions under 15 000 rows each.
4. **Same cleaning code for batch and streaming**: `pipeline/clean.py` is imported by both `run_batch.py` and `run_stream.py` — no training-serving skew.
5. **Cassandra as single source of truth**: the WebSocket feed reads from Cassandra, not an in-process cache.
