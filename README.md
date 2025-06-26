## dify-plugin-kubernetes

**Author:** lework
**Version:** 0.0.1
**Type:** tool

### Description

Dify Plugin - Kubernetes Cluster Resource Management Tool. This plugin enables you to retrieve and manage resources in your Kubernetes clusters directly through Dify.

### Feature List

1. Basic Information Query Tool (dify-plugin-kubernetes)

   - Retrieve fundamental information about your Kubernetes cluster
   - Get cluster status, version, and node information
   - View available API resources

2. Pod Log Query Tool (get-pod-logs)

   - Fetch logs from specified Pods
   - Support for namespace specification, container name selection, and log line quantity control
   - Real-time monitoring and troubleshooting of applications
   - Filter logs based on specific time periods

3. Resource Description Tool (describe-resource)

   - Functionality similar to the `kubectl describe` command
   - Support for multiple resource types: Pod, Deployment, DaemonSet, StatefulSet, Service, Ingress, and more
   - Provides detailed resource status and configuration information
   - Custom namespace support
   - Displays events related to resources for easier troubleshooting
   - Extract key metrics and status indicators

4. Resource Listing Tool (list-resources)
   - List available resources by type across namespaces
   - Filter resources by labels and fields
   - Get concise overview of cluster resources
   - Support for wide output with additional details

### Requirements

- Properly configured kubectl environment with access to your Kubernetes cluster
- Python 3.8 or higher
- Required dependencies: `pip install -r requirements.txt`
- Appropriate RBAC permissions in your Kubernetes cluster to access resources

### Parameter Descriptions

#### Pod Log Query Tool

- `pod_name`: Pod name (required)
- `namespace`: Namespace (optional, defaults to "default")
- `container_name`: Container name (optional, returns logs from the first container if not specified)
- `tail_lines`: Number of log lines to return (optional, defaults to 100)

#### Resource Description Tool

- `resource_type`: Resource type (required, e.g., pod, deployment, daemonset, statefulset, service, etc.)
- `resource_name`: Resource name (required)
- `namespace`: Namespace (optional, defaults to "default")

#### Resource Listing Tool

- `resource_type`: Resource type (required, e.g., pods, deployments, services, etc.)
- `namespace`: Namespace (optional, defaults to "all-namespaces")
- `label_selector`: Label selector to filter resources (optional)
- `field_selector`: Field selector to filter resources (optional)

### Development and Debugging

```bash
# Install dependencies
pip install -r requirements.txt

# Run debug
python -m main

# Package plugin
dify plugin package ./dify-plugin-kubernetes
```
