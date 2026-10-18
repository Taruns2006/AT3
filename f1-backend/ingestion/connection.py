import os
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Patch for Python 3.12+ / 3.14 asyncore deprecation
from cassandra.io.asyncioreactor import AsyncioConnection
import cassandra.io
cassandra.io.default_connection_class = AsyncioConnection

def get_connection():
    bundle = os.getenv('SECURE_CONNECT_BUNDLE', './secure-connect-f1-telemetry-system.zip')
    token = os.getenv('ASTRA_TOKEN', '')
    keyspace = os.getenv('ASTRA_KEYSPACE', 'f1_telemetry_system')

    cloud_config = {'secure_connect_bundle': bundle}
    
    if token:
        auth_provider = PlainTextAuthProvider('token', token)
        cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
    else:
        cluster = Cluster(cloud=cloud_config)

    return cluster.connect(keyspace)
