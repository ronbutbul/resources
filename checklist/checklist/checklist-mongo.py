import yaml
from kubernetes import client, config
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

def print_pod_statuses(namespace, label_selector):
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    for pod in pods.items:
        print(f"    Pod Name: {pod.metadata.name}, Pod Status: {pod.status.phase}")

def get_service_external_ip_or_hostname(namespace, service_name):
    try:
        svc = v1.read_namespaced_service(name=service_name, namespace=namespace)
        if svc.spec.type == "LoadBalancer":
            ingress = svc.status.load_balancer.ingress[0]
            external_ip_or_hostname = ingress.hostname or ingress.ip
            print(f"Found Service with external IP/hostname: {external_ip_or_hostname}")
            return external_ip_or_hostname
    except client.exceptions.ApiException as e:
        print(f"Error fetching service: {e}")
    print("No external IP/hostname found for Service.")
    return None

def check_mongodb_connection(mongodb_uri):
    try:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("MongoDB connection check succeeded.")
        client.close()
    except ConnectionFailure as e:
        print(f"MongoDB connection check failed: {e}")

def check_kubernetes_resources(namespace, app_name, label_selector, resource_type, service_name=None):
    print(f"\nChecking resources for {app_name.capitalize()} in {namespace}...")
    if resource_type.lower() in ("deployment", "both"):
        deployments = apps_v1.list_namespaced_deployment(namespace, label_selector=label_selector)
        if deployments.items:
            print(f"Deployment(s) found: {len(deployments.items)}")
            for deployment in deployments.items:
                print(f"  Deployment Name: {deployment.metadata.name}")
                print_pod_statuses(namespace, label_selector)
        else:
            print("No Deployments found.")
    if resource_type.lower() in ("statefulset", "both"):
        statefulsets = apps_v1.list_namespaced_stateful_set(namespace, label_selector=label_selector)
        if statefulsets.items:
            print(f"StatefulSet(s) found: {len(statefulsets.items)}")
            for statefulset in statefulsets.items:
                print(f"  StatefulSet Name: {statefulset.metadata.name}")
                print_pod_statuses(namespace, label_selector)
        else:
            print("No StatefulSets found.")
    if service_name:
        external_ip_or_hostname = get_service_external_ip_or_hostname(namespace, service_name)
        if external_ip_or_hostname:
            if app_name.lower() == "mongodb":
                mongodb_uri = f"mongodb://{external_ip_or_hostname}:27017/"
                check_mongodb_connection(mongodb_uri)

if __name__ == "__main__":
    with open('app_config.yaml', 'r') as file:
        app_config = yaml.safe_load(file)
    for app_name, app_details in app_config.items():
        namespace = app_details['namespace']
        label_selector = app_details.get('label_selector', None)
        resource_type = app_details.get('resource_type', 'both')
        service_name = app_details.get('service_name', None)
        check_kubernetes_resources(namespace, app_name, label_selector, resource_type, service_name)
