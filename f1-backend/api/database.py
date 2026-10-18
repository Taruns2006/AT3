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

# Required helper function for health check routes
def get_health():
    try:
        # Simple query to verify database connectivity
        session.execute("SELECT now() from system.local")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
