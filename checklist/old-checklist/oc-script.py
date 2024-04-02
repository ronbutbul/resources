import json
import socket
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import requests
import redis
from kafka import KafkaConsumer
from kafka.errors import KafkaError

def build_mongo_connection_string(endpoint, username, password, database_name):
    """Builds a MongoDB connection string."""
    return f"mongodb://{username}:{password}@{endpoint}/{database_name}?authSource=admin&directConnection=true"

def check_mongodb(app_details):
    """Checks MongoDB connectivity using the provided details."""
    endpoint = app_details.get('endpoint')
    database_name = app_details.get('database_name')
    username = app_details.get('username')
    password = app_details.get('password')
    
    connection_string = build_mongo_connection_string(endpoint, username, password, database_name)
    
    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print(f"MongoDB connection check succeeded for {database_name}.")
        client.close()
    except ConnectionFailure as e:
        print(f"MongoDB connection check failed: {e}")

def check_http_endpoint(endpoint):
    """Checks if an HTTP endpoint is accessible."""
    try:
        response = requests.get(endpoint, timeout=10)
        if response.status_code == 200:
            print(f"HTTP endpoint {endpoint} is reachable.")
        else:
            print(f"HTTP endpoint {endpoint} returned status code {response.status_code}.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to reach HTTP endpoint {endpoint}: {e}")

def check_grpc_endpoint(endpoint):
    """Checks if a gRPC endpoint is accessible."""
    host, port = endpoint.split(':')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    result = sock.connect_ex((host, int(port)))
    if result == 0:
        print(f"gRPC endpoint {endpoint} is reachable.")
    else:
        print(f"Failed to reach gRPC endpoint {endpoint}.")
    sock.close()

def check_redis(app_details):
    """Checks Redis connectivity using the provided details."""
    endpoint = app_details.get('endpoint')
    password = app_details.get('password', None)

    try:
        host, port = endpoint.split(":")
        r = redis.Redis(host=host, port=int(port), password=password, decode_responses=True, socket_timeout=5)
        if r.ping():
            print(f"Redis at {endpoint} connection check succeeded.")
        else:
            print(f"Redis at {endpoint} connection check failed.")
    except redis.RedisError as e:
        print(f"Redis at {endpoint} connection check failed: {e}")

def check_kafka(app_details):
    """Checks connectivity to Kafka brokers."""
    brokers = app_details.get('brokers')
    
    try:
        # Attempt to create a Kafka consumer to list topics, which tests connectivity
        consumer = KafkaConsumer(bootstrap_servers=brokers, client_id='test_consumer', request_timeout_ms=10000)
        topics = consumer.topics()
        print(f"Successfully connected to Kafka brokers: {brokers}. And there are Topics available.")
        consumer.close()
    except KafkaError as e:
        print(f"Failed to connect to Kafka brokers {brokers}: {e}")


if __name__ == "__main__":
    with open('oc-config.json', 'r') as file:
        config = json.load(file)

    apps = config.get('apps', {})
    for app_name, app_details in apps.items():
        app_type = app_details.get('type')
        print(f"\nChecking {app_name} connectivity...")
        if app_type == "mongodb":
            check_mongodb(app_details)
        elif app_type == "http":
            check_http_endpoint(app_details.get('endpoint'))
        elif app_type == "grpc":
            check_grpc_endpoint(app_details.get('endpoint'))
        elif app_type == "redis":
            check_redis(app_details)
        elif app_type == "kafka":
            check_kafka(app_details)            