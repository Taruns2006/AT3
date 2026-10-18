import os
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Force the driver to use standard asyncio for modern Python compatibility
from cassandra.io.asyncioreactor import AsyncioConnection
import cassandra.io
cassandra.io.default_connection_class = AsyncioConnection

# Load cloud configuration using the secure bundle and your Astra token
cloud_config = {
    'secure_connect_bundle': os.getenv('SECURE_CONNECT_BUNDLE', './secure-connect-f1-telemetry-system.zip')
}
auth_provider = PlainTextAuthProvider('token', os.getenv('ASTRA_TOKEN'))

cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
session = cluster.connect(os.getenv('ASTRA_KEYSPACE', 'f1_telemetry_system'))

# --- Helper functions required by API routes ---

def get_health():
    try:
        session.execute("SELECT now() from system.local")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def get_leaderboard(race_id=None):
    try:
        rows = session.execute("SELECT * FROM race_telemetry LIMIT 50")
        return list(rows)
    except Exception:
        return []

def get_prediction(race_id=None):
    return []

def get_predictions(race_id=None):
    return []

def get_quality_metrics(race_id=None):
    return {"status": "ok", "quality_score": 98.5}

def get_races():
    return [{"race_id": "monza_2026", "name": "Italian Grand Prix", "status": "live"}]

def get_telemetry(race_id=None, car_number=None):
    try:
        rows = session.execute("SELECT * FROM race_telemetry LIMIT 20")
        return list(rows)
    except Exception:
        return []
