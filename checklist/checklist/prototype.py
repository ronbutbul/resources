import json
import socket
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import requests
from kubernetes import client, config, dynamic
from kubernetes.client.rest import ApiException
import subprocess
import yaml
import time
import sys
from kubernetes.dynamic import DynamicClient
# Load the in-cluster configuration
config.load_incluster_config()
#config.load_kube_config()

v1 = client.CoreV1Api()
#apps_v1 = client.AppsV1Api()

dyn_client = DynamicClient(client.ApiClient())

#dyn_client = dynamic.DynamicClient(
#    client.ApiClient(configuration=config.load_kube_config())
#)

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


def check_jaeger_endpoint_from_otc(namespace, expected_jaeger_endpoint):
    cmd = f"kubectl get opentelemetrycollector -n {namespace} -o yaml"
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Error executing '{cmd}': {process.stderr}")
        return
    
    otel_yaml = yaml.safe_load(process.stdout)
    items = otel_yaml.get('items', [])

    # Check if OpenTelemetryCollectors are found
    if not items:
        print(f"No OpenTelemetryCollector found in namespace '{namespace}'.")
        return
    else:
        print(f"Found {len(items)} OpenTelemetryCollector(s) in namespace '{namespace}'.")

    found = False
    for item in items:
        config_str = item.get('spec', {}).get('config', '').replace('\\n', '\n')
        config_str_cleaned = '\n'.join(line for line in config_str.split('\n') if not line.strip().startswith('#'))
        config_yaml = yaml.safe_load(config_str_cleaned)
        if 'exporters' in config_yaml:
            jaeger_endpoint = config_yaml.get('exporters', {}).get('jaeger', {}).get('endpoint', '')
            if jaeger_endpoint:
                if jaeger_endpoint == expected_jaeger_endpoint:
                    print(f"Jaeger endpoint '{jaeger_endpoint}' matches expected value in namespace '{namespace}'.")
                else:
                    print(f"Jaeger endpoint '{jaeger_endpoint}' does not match expected value '{expected_jaeger_endpoint}' in namespace '{namespace}'.")
                found = True
                break  # Break after finding the first configured Jaeger endpoint
    if not found:
        print(f"No active Jaeger endpoint configuration found in namespace '{namespace}' matching expected value.")



def check_deployment_status(namespace, partial_name):
    cmd = f"kubectl get deployments -n {namespace} -o json"
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Error executing '{cmd}': {process.stderr}\n")
        return
    deployments = json.loads(process.stdout)
    found = False
    for deployment in deployments.get("items", []):
        deployment_name = deployment.get("metadata", {}).get("name", "")
        if partial_name in deployment_name:
            found = True
            replicas = deployment.get("status", {}).get("replicas", 0)
            available_replicas = deployment.get("status", {}).get("availableReplicas", 0)
            if replicas == available_replicas:
                print(f"Deployment '{deployment_name}' in namespace '{namespace}' is up and running.\n")
            else:
                print(f"Deployment '{deployment_name}' in namespace '{namespace}' is not fully up (Available: {available_replicas}/{replicas}).\n")
            break  # Assuming only one deployment matches the partial name criteria
    if not found:
        print(f"No deployment containing '{partial_name}' found in namespace '{namespace}'.\n")


def check_prometheus_target_by_job(endpoint, job_name):
    query_url = f"{endpoint}/api/v1/targets"
    print(f"Querying Prometheus API at: {query_url}")

    try:
        response = requests.get(query_url)
        response.raise_for_status()  # Ensure no HTTP errors
        targets_data = response.json()

        print("Successfully fetched data from Prometheus API.")
        print(f"Searching for job: {job_name}")

        found = False
        for target in targets_data.get('data', {}).get('activeTargets', []):
            if target.get('labels', {}).get('job') == job_name:
                health = target.get('health')
                print(f"Job '{job_name}' found with state: {health}.\n")
                found = True
                break  # Assuming you only need to find one instance of the job

        if not found:
            print(f"Job '{job_name}' not found.\n")
    except requests.exceptions.RequestException as e:
        print(f"Failed to query Prometheus API: {e}\n")


def check_elasticsearch_index_existence(endpoint, partial_index_name):
    # This URL queries the _cat/indices API of Elasticsearch to list all indices
    query_url = f"{endpoint}/_cat/indices/{partial_index_name}*?format=json"
    print(f"Querying Elasticsearch directly at: {query_url}")

    try:
        response = requests.get(query_url)
        if response.status_code == 200:
            indices = response.json()
            if indices:
                print(f"Indices containing '{partial_index_name}' found:")
                for index in indices:
                    print(f"- {index['index']}")
            else:
                print(f"No indices containing '{partial_index_name}' found.")
        else:
            print("Failed to fetch indices. Please check the Elasticsearch endpoint and your network connection.")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

 

if __name__ == "__main__":  
    while True:  
       with open('/etc/script-config/config.json', 'r') as file:
           config = json.load(file)

       # Open the output file in write mode to overwrite existing content
       with open('/data/check_results.txt', 'w') as output_file:
           # Redirect print statements to write to the output file instead of the screen
           original_stdout = sys.stdout  # Save a reference to the original standard output
           sys.stdout = output_file  # Change the standard output to the file we created.

           # Handle apps checks
           apps = config.get('apps', {})
           for app_name, app_details in apps.items():
               app_type = app_details.get('type')
               print(f"\nChecking {app_name} connectivity...")
          
               if app_type == "mongodb":
                   check_mongodb(app_details)
          
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
          
           jaeger_check_config = config.get('jaegerCheck', None)
           if jaeger_check_config:
               print("\nChecking Jaeger endpoint configuration...")
               check_jaeger_endpoint_from_otc(jaeger_check_config["namespace"], jaeger_check_config["expectedJaegerEndpoint"])
          
          
           deployment_check_config = config.get('deploymentCheck', None)
           if deployment_check_config:
               print("\nChecking deployment status...")
               check_deployment_status(deployment_check_config["namespace"], deployment_check_config["partialName"])        
          
           prometheus_check_config = config.get('prometheusCheck', {})
           if prometheus_check_config:
               prometheus_endpoint = prometheus_check_config.get("endpoint")
               job_name = prometheus_check_config.get("jobName")
               check_prometheus_target_by_job(prometheus_endpoint, job_name)
           else:
               print("No Prometheus check configuration found.")
          
           es_check_config = config.get('elasticsearchCheck', {})
           if es_check_config:
               es_endpoint = es_check_config.get("endpoint")
               partial_index_name = es_check_config.get("partialIndexName")
               check_elasticsearch_index_existence(es_endpoint, partial_index_name)
           else:
               print("No Elasticsearch check configuration found.")
           time.sleep(10)    

           sys.stdout = original_stdout  # Reset the standard output to its original value

       print("Checks completed and results written to check_results.txt")


       time.sleep(400)    