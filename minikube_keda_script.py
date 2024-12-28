import os
import subprocess
import yaml
from kubernetes import client, config

def run_shell_command(command):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}\n{e.stderr}")
        raise

def load_minikube_config():
    """Load Minikube Kubernetes configuration."""
    print("Setting up Minikube context...")
    config.load_kube_config(context="minikube")

def start_minikube():
    """Start Minikube if it is not already running."""
    try:
        status = run_shell_command("minikube status")
        if "Running" in status:
            print("Minikube is already running.")
        else:
            print("Starting Minikube...")
            run_shell_command("minikube start")
    except Exception as e:
        print(f"Error checking Minikube status: {e}")
        raise

def install_helm():
    """Install Helm if not already installed."""
    try:
        print("Checking if Helm is installed...")
        run_shell_command("helm version")
        print("Helm is already installed.")
    except:
        print("Helm not found. Installing Helm...")
        run_shell_command("curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash")

def install_keda():
    """Install KEDA on the Kubernetes cluster using Helm."""
    print("Installing KEDA...")
    run_shell_command("helm repo add kedacore https://kedacore.github.io/charts")
    run_shell_command("helm repo update")
    run_shell_command("helm install keda kedacore/keda --namespace keda --create-namespace")
    print("KEDA installed successfully.")

def verify_keda_installation():
    """Verify that KEDA is installed and running."""
    print("Verifying KEDA installation...")
    pods = run_shell_command("kubectl get pods -n keda")
    print(pods)

def create_deployment(deployment_name, image, namespace="default", cpu_request="100m", cpu_limit="200m", memory_request="128Mi", memory_limit="256Mi", ports=None):
    """Create a Kubernetes deployment."""
    ports = ports or []
    container_ports = [{"containerPort": port} for port in ports]

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": deployment_name,
            "namespace": namespace
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": deployment_name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": deployment_name
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": deployment_name,
                            "image": image,
                            "resources": {
                                "requests": {
                                    "cpu": cpu_request,
                                    "memory": memory_request
                                },
                                "limits": {
                                    "cpu": cpu_limit,
                                    "memory": memory_limit
                                }
                            },
                            "ports": container_ports
                        }
                    ]
                }
            }
        }
    }

    api_instance = client.AppsV1Api()
    try:
        response = api_instance.create_namespaced_deployment(
            body=deployment,
            namespace=namespace
        )
        print(f"Deployment {deployment_name} created in namespace {namespace}.")
        return response.metadata.uid
    except client.exceptions.ApiException as e:
        print(f"Exception when creating deployment: {e}")
        raise

def create_service(deployment_name, namespace="default", ports=None):
    """Create a Kubernetes service for a deployment."""
    ports = ports or []
    service_ports = [{"port": port, "targetPort": port} for port in ports]

    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"{deployment_name}-service",
            "namespace": namespace
        },
        "spec": {
            "selector": {
                "app": deployment_name
            },
            "ports": service_ports
        }
    }

    api_instance = client.CoreV1Api()
    try:
        response = api_instance.create_namespaced_service(
            body=service,
            namespace=namespace
        )
        print(f"Service {deployment_name}-service created in namespace {namespace}.")
        return response.metadata.name
    except client.exceptions.ApiException as e:
        print(f"Exception when creating service: {e}")
        raise

def create_scaled_object(deployment_name, metric_name, threshold, namespace="default"):
    """Create a KEDA ScaledObject for event-driven scaling."""
    scaled_object = {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {
            "name": f"{deployment_name}-scaledobject",
            "namespace": namespace
        },
        "spec": {
            "scaleTargetRef": {
                "name": deployment_name
            },
            "triggers": [
                {
                    "type": metric_name,
                    "metadata": {
                        "value": str(threshold)
                    }
                }
            ]
        }
    }

    custom_objects_api = client.CustomObjectsApi()
    try:
        custom_objects_api.create_namespaced_custom_object(
            group="keda.sh",
            version="v1alpha1",
            namespace=namespace,
            plural="scaledobjects",
            body=scaled_object
        )
        print(f"ScaledObject {deployment_name}-scaledobject created in namespace {namespace}.")
    except client.exceptions.ApiException as e:
        print(f"Exception when creating ScaledObject: {e}")
        raise

def get_deployment_health(deployment_id, namespace="default"):
    """Check the health status of a deployment by ID."""
    api_instance = client.AppsV1Api()

    try:
        deployments = api_instance.list_namespaced_deployment(namespace=namespace).items
        for deployment in deployments:
            if deployment.metadata.uid == deployment_id:
                status = deployment.status
                ready_replicas = status.ready_replicas or 0
                replicas = status.replicas or 0
                health_status = "Healthy" if ready_replicas == replicas else "Unhealthy"
                print(f"Deployment {deployment.metadata.name} health status: {health_status}")
                return health_status
        print(f"Deployment with ID {deployment_id} not found.")
        return "Not Found"
    except client.exceptions.ApiException as e:
        print(f"Exception when checking deployment health: {e}")
        raise

def main():
    """Main script entry point."""
    try:
        start_minikube()
        load_minikube_config()
        install_helm()
        install_keda()
        verify_keda_installation()

        deployment_name = "example-deployment"
        image = "nginx:latest"
        namespace = "default"
        ports = [80]
        cpu_request = "100m"
        cpu_limit = "200m"
        memory_request = "128Mi"
        memory_limit = "256Mi"

        deployment_id = create_deployment(deployment_name, image, namespace, cpu_request, cpu_limit, memory_request, memory_limit, ports)
        create_service(deployment_name, namespace, ports)
        create_scaled_object(deployment_name, metric_name="cpu", threshold=50, namespace=namespace)

        # Check health status of the deployment
        get_deployment_health(deployment_id, namespace)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
