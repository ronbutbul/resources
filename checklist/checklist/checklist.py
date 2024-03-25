import yaml
from kubernetes import client, config

def print_pod_statuses(namespace, label_selector):
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    for pod in pods.items:
        print(f"    Pod Name: {pod.metadata.name}, Pod Status: {pod.status.phase}")

def check_kubernetes_resources(namespace, app_name, label_selector, resource_type):
    print(f"\nChecking resources for {app_name.capitalize()} in {namespace}...")

    # Adjusted to directly use the provided label_selector for fetching pods
    pod_label_selector = label_selector

    # Check for Deployments if specified
    if resource_type.lower() in ("deployment", "both"):
        deployments = apps_v1.list_namespaced_deployment(namespace, label_selector=label_selector)
        if deployments.items:
            print(f"Deployment(s) found: {len(deployments.items)}")
            for deployment in deployments.items:
                print(f"  Deployment Name: {deployment.metadata.name}")
                print_pod_statuses(namespace, pod_label_selector)
        else:
            print("No Deployments found.")

    # Check for StatefulSets if specified
    if resource_type.lower() in ("statefulset", "both"):
        statefulsets = apps_v1.list_namespaced_stateful_set(namespace, label_selector=label_selector)
        if statefulsets.items:
            print(f"StatefulSet(s) found: {len(statefulsets.items)}")
            for statefulset in statefulsets.items:
                print(f"  StatefulSet Name: {statefulset.metadata.name}")
                print_pod_statuses(namespace, pod_label_selector)
        else:
            print("No StatefulSets found.")

if __name__ == "__main__":
    # Load kube config from default location (`~/.kube/config`)
    config.load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()

    # Load the application configuration file
    with open('app_config.yaml', 'r') as file:
        app_config = yaml.safe_load(file)

    # Iterate over the applications in the configuration
    for app_name, app_details in app_config.items():
        namespace = app_details['namespace']
        label_selector = app_details.get('label_selector', None)  # Safely get the label_selector
        resource_type = app_details.get('resource_type', 'both')  # Default to both if not specified
        check_kubernetes_resources(namespace, app_name, label_selector, resource_type)
