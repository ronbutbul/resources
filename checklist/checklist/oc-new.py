import json
import socket
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import requests
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from kubernetes import client, config, dynamic
from kubernetes.client.rest import ApiException
import subprocess
import yaml

# Load the in-cluster configuration
#config.load_incluster_config()
config.load_kube_config()

v1 = client.CoreV1Api()
#apps_v1 = client.AppsV1Api()

dyn_client = dynamic.DynamicClient(
    client.ApiClient(configuration=config.load_kube_config())
)

def build_mongo_connection_string(endpoint, username, password, database_name):
    """Builds a MongoDB connection string."""
    return f"mongodb://{username}:{password}@{endpoint}/{database_name}?authSource=admin&directConnection=true"

def check_mongodb(app_details):
    """Checks MongoDB connectivity and tests write permissions."""
    endpoint = app_details.get('endpoint')
    database_name = app_details.get('database_name')
    username = app_details.get('username')
    password = app_details.get('password')
    
    connection_string = build_mongo_connection_string(endpoint, username, password, database_name)
    
    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        # Ping the server to test connectivity
        client.admin.command('ping')
        print(f"MongoDB connection check succeeded for {database_name}.")

        # Create a test collection and insert a document
        test_db = client['test_db']
        test_collection = test_db['test_collection']
        test_document = {"name": "test", "message": "This is a test document"}
        insert_result = test_collection.insert_one(test_document)
        
        if insert_result.inserted_id:
            print(f"Successfully inserted document into MongoDB. Document ID: {insert_result.inserted_id}")
            
            # Optionally, clean up by dropping the test collection or document after the test
            # test_collection.drop()
            # Or, to just delete the inserted document:
            # test_collection.delete_one({"_id": insert_result.inserted_id})
        
        client.close()
    except ConnectionFailure as e:
        print(f"MongoDB connection check failed: {e}")
    except Exception as e:
        print(f"MongoDB test operation failed: {e}")



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


def check_config_map_exists(config_map_details):
    cm_name = config_map_details.get('name')
    cm_namespace = config_map_details.get('namespace')

    try:
        v1 = client.CoreV1Api()
        cm = v1.read_namespaced_config_map(name=cm_name, namespace=cm_namespace)
        print(f"ConfigMap '{cm_name}' exists in namespace '{cm_namespace}'.")
    except ApiException as e:
        if e.status == 404:
            print(f"ConfigMap '{cm_name}' does not exist in namespace '{cm_namespace}'.")
        else:
            print(f"Error checking ConfigMap '{cm_name}' in namespace '{cm_namespace}': {e}")


def check_secret_exists(secret_details):
    secret_name = secret_details.get('name')
    secret_namespace = secret_details.get('namespace')

    try:
        # Ensure the API client is fresh
        v1_client = client.CoreV1Api()
        secret = v1_client.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
        print(f"Secret '{secret_name}' exists in namespace '{secret_namespace}'.")
    except ApiException as e:
        if e.status == 404:
            print(f"Secret '{secret_name}' does not exist in namespace '{secret_namespace}'.")
        else:
            print(f"Error checking Secret '{secret_name}' in namespace '{secret_namespace}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred while checking Secret '{secret_name}' in namespace '{secret_namespace}': {e}")


def check_application_exists(app_details):
    app_name = app_details.get('name')
    app_namespace = app_details.get('namespace')

    try:
        # Assuming 'applications' is the plural name of the Application CRD and using the correct API version
        api = dyn_client.resources.get(api_version='argoproj.io/v1alpha1', kind='Application')

        app = api.get(name=app_name, namespace=app_namespace)
        print(f"Application '{app_name}' exists in namespace '{app_namespace}'.")
    except ApiException as e:
        if e.status == 404:
            print(f"Application '{app_name}' does not exist in namespace '{app_namespace}'.")
        else:
            print(f"Error checking Application '{app_name}' in namespace '{app_namespace}': {e}")
    except Exception as e:
        # Catch other potential exceptions
        print(f"An unexpected error occurred while checking Application '{app_name}' in namespace '{app_namespace}': {e}")


def get_clf_and_check_namespace(clf_name, namespace, target_namespace):
    cmd = f"kubectl get clf {clf_name} -n {namespace} -o yaml"
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Error executing '{cmd}': {process.stderr}")
        return
    
    clf_yaml = process.stdout
    clf_data = yaml.safe_load(clf_yaml)
    
    found = False
    for input_item in clf_data.get("spec", {}).get("inputs", []):
        if "application" in input_item and target_namespace in input_item["application"].get("namespaces", []):
            print(f"Namespace '{target_namespace}' found in ClusterLogForwarder.")
            found = True
            break
    
    if not found:
        print(f"Namespace '{target_namespace}' not found in any 'application' input of ClusterLogForwarder '{clf_name}'.")



if __name__ == "__main__":
    with open('oc-config.json', 'r') as file:
        config = json.load(file)

    # Handle apps checks
    apps = config.get('apps', {})
    for app_name, app_details in apps.items():
        app_type = app_details.get('type')
        print(f"\nChecking {app_name} connectivity...")

        if app_type == "mongodb":
            check_mongodb(app_details)

        elif app_type == "kafka":
            check_kafka(app_details)

    # ConfigMap check
    config_map_details = config.get('configMapCheck', None)
    if config_map_details:
        print("\nChecking ConfigMap existence...")
        check_config_map_exists(config_map_details)
    else:
        print("No ConfigMapCheck configuration found.")

    secrets_checks = config.get('secretsChecks', [])
    for secret_details in secrets_checks:
        print("\nChecking Secret existence...")
        check_secret_exists(secret_details)

    application_checks = config.get('applicationChecks', [])
    for app_details in application_checks:
        print("\nChecking Application existence...")
        check_application_exists(app_details)        

    clf_details = config.get('clusterLogForwarderDetails', None)
    if clf_details:
        print("\nChecking ClusterLogForwarder configuration...")
        get_clf_and_check_namespace(clf_details["name"], clf_details["namespace"], clf_details["targetNamespace"])
    else:
        print("No ClusterLogForwarder configuration found.")
