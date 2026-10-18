import os
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Load cloud configuration using the secure bundle and your Astra token
cloud_config = {
    'secure_connect_bundle': os.getenv('SECURE_CONNECT_BUNDLE', './secure-connect-f1-telemetry-system.zip')
}
auth_provider = PlainTextAuthProvider('token', os.getenv('ASTRA_TOKEN'))

cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
session = cluster.connect(os.getenv('ASTRA_KEYSPACE', 'f1_telemetry_system'))
