from collections.abc import Generator
from typing import Any
import yaml
import base64
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from dify_plugin.errors.model import InvokeServerUnavailableError

class ListResourcesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 获取参数
            namespace = tool_parameters.get("namespace", "").strip().lower()
            resource_type = tool_parameters.get("resource_type", "").strip().lower()
            label_selector = tool_parameters.get("label_selector", "").strip()
            field_selector = tool_parameters.get("field_selector", "").strip()
            kubeconfig = tool_parameters.get("kubeconfig", "").strip()
            limit = tool_parameters.get("limit", 10)
            
            # 验证资源类型
            if not resource_type:
                raise InvokeServerUnavailableError("未配置资源类型")
            
            # 如果提供了limit，确保它是一个有效的整数
            try:
                if limit:
                    limit = int(limit)
            except ValueError:
                limit = 0
            
            # 加载Kubernetes配置
            if kubeconfig:
                missing_padding = len(kubeconfig) % 4
                if missing_padding != 0:
                    kubeconfig += '='* (4 - missing_padding)
                kubeconfig_str = base64.b64decode(kubeconfig).decode('utf-8')
                config.load_kube_config_from_dict(yaml.safe_load(kubeconfig_str))
            else:
                kubeconfig = self.runtime.credentials["kubeconfig"]
                missing_padding = len(kubeconfig) % 4
                if missing_padding != 0:
                    kubeconfig += '='* (4 - missing_padding)
                kubeconfig_str = base64.b64decode(kubeconfig).decode('utf-8')
                config.load_kube_config_from_dict(yaml.safe_load(kubeconfig_str))

            # 创建Kubernetes API客户端
            core_v1 = client.CoreV1Api()
            apps_v1 = client.AppsV1Api()
            networking_v1 = client.NetworkingV1Api()
            batch_v1 = client.BatchV1Api()

            # 根据资源类型获取列表信息
            resources = []
            api_response = None
            
            try:
                if resource_type == "pod" or resource_type == "pods":
                    if namespace:
                        api_response = core_v1.list_namespaced_pod(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = core_v1.list_pod_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_pod_list(api_response.items)
                
                elif resource_type == "deployment" or resource_type == "deployments":
                    if namespace:
                        api_response = apps_v1.list_namespaced_deployment(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = apps_v1.list_deployment_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_deployment_list(api_response.items)
                
                elif resource_type == "service" or resource_type == "services" or resource_type == "svc":
                    if namespace:
                        api_response = core_v1.list_namespaced_service(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = core_v1.list_service_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_service_list(api_response.items)
                
                elif resource_type == "node" or resource_type == "nodes":
                    api_response = core_v1.list_node(
                        label_selector=label_selector, 
                        field_selector=field_selector,
                        limit=limit if limit > 0 else None
                    )
                    resources = self._extract_node_list(api_response.items)
                
                elif resource_type == "namespace" or resource_type == "namespaces" or resource_type == "ns":
                    api_response = core_v1.list_namespace(
                        label_selector=label_selector, 
                        field_selector=field_selector,
                        limit=limit if limit > 0 else None
                    )
                    resources = self._extract_namespace_list(api_response.items)
                
                elif resource_type == "configmap" or resource_type == "configmaps" or resource_type == "cm":
                    if namespace:
                        api_response = core_v1.list_namespaced_config_map(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = core_v1.list_config_map_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_configmap_list(api_response.items)
                
                elif resource_type == "secret" or resource_type == "secrets":
                    if namespace:
                        api_response = core_v1.list_namespaced_secret(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = core_v1.list_secret_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_secret_list(api_response.items)
                
                elif resource_type == "ingress" or resource_type == "ingresses" or resource_type == "ing":
                    if namespace:
                        api_response = networking_v1.list_namespaced_ingress(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = networking_v1.list_ingress_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_ingress_list(api_response.items)
                
                elif resource_type == "daemonset" or resource_type == "daemonsets" or resource_type == "ds":
                    if namespace:
                        api_response = apps_v1.list_namespaced_daemon_set(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = apps_v1.list_daemon_set_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_daemonset_list(api_response.items)
                
                elif resource_type == "statefulset" or resource_type == "statefulsets" or resource_type == "sts":
                    if namespace:
                        api_response = apps_v1.list_namespaced_stateful_set(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = apps_v1.list_stateful_set_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_statefulset_list(api_response.items)
                
                elif resource_type == "job" or resource_type == "jobs":
                    if namespace:
                        api_response = batch_v1.list_namespaced_job(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = batch_v1.list_job_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_job_list(api_response.items)
                
                elif resource_type == "cronjob" or resource_type == "cronjobs" or resource_type == "cj":
                    if namespace:
                        api_response = batch_v1.list_namespaced_cron_job(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = batch_v1.list_cron_job_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_cronjob_list(api_response.items)
                
                elif resource_type == "persistentvolume" or resource_type == "persistentvolumes" or resource_type == "pv":
                    api_response = core_v1.list_persistent_volume(
                        label_selector=label_selector, 
                        field_selector=field_selector,
                        limit=limit if limit > 0 else None
                    )
                    resources = self._extract_pv_list(api_response.items)
                
                elif resource_type == "persistentvolumeclaim" or resource_type == "persistentvolumeclaims" or resource_type == "pvc":
                    if namespace:
                        api_response = core_v1.list_namespaced_persistent_volume_claim(
                            namespace=namespace, 
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    else:
                        api_response = core_v1.list_persistent_volume_claim_for_all_namespaces(
                            label_selector=label_selector, 
                            field_selector=field_selector,
                            limit=limit if limit > 0 else None
                        )
                    resources = self._extract_pvc_list(api_response.items)
                
                else:
                    raise InvokeServerUnavailableError(f"不支持的资源类型: {resource_type}")
                    
            except ApiException as e:
                if e.status == 404:
                    yield self.create_text_message(f"未找到资源: {resource_type}")
                    yield self.create_json_message({
                        "resource_type": resource_type,
                        "resources": [],
                        "count": 0
                    })
                    return
                else:
                    # 其他API错误
                    raise InvokeServerUnavailableError(f"获取资源列表失败: {str(e)}")
            
            # 构建响应
            response = {
                "resource_type": resource_type,
                "resources": resources,
                "count": len(resources),
                "namespace": namespace if namespace else "all"
            }
            
            # 格式化输出文本
            text_message = self._format_resource_list(resource_type, resources, namespace)
            
            # 输出
            yield self.create_text_message(text_message)
            yield self.create_json_message(response)
            
        except Exception as e:
            traceback.print_exc()
            raise InvokeServerUnavailableError(f"获取资源列表失败: {str(e)}")
    
    def _extract_pod_list(self, pods):
        """提取Pod列表信息"""
        resources = []
        for pod in pods:
            resources.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "node": pod.spec.node_name if pod.spec.node_name else "",
                "ip": pod.status.pod_ip,
                "age": pod.metadata.creation_timestamp,
                "containers": len(pod.spec.containers),
                "ready_containers": sum(1 for status in (pod.status.container_statuses or []) if status.ready),
                "restarts": sum(status.restart_count for status in (pod.status.container_statuses or []))
            })
        return resources
    
    def _extract_deployment_list(self, deployments):
        """提取Deployment列表信息"""
        resources = []
        for dep in deployments:
            resources.append({
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "replicas": f"{dep.status.ready_replicas or 0}/{dep.spec.replicas}",
                "available": dep.status.available_replicas or 0,
                "age": dep.metadata.creation_timestamp,
                "containers": len(dep.spec.template.spec.containers) if dep.spec.template and dep.spec.template.spec else 0,
                "images": [container.image for container in dep.spec.template.spec.containers] if dep.spec.template and dep.spec.template.spec else []
            })
        return resources
    
    def _extract_service_list(self, services):
        """提取Service列表信息"""
        resources = []
        for svc in services:
            cluster_ip = svc.spec.cluster_ip
            external_ips = []
            if svc.spec.type == "LoadBalancer" and hasattr(svc.status, "load_balancer") and hasattr(svc.status.load_balancer, "ingress") and svc.status.load_balancer.ingress:
                external_ips = [ingress.ip for ingress in svc.status.load_balancer.ingress if hasattr(ingress, "ip") and ingress.ip]
            
            ports = []
            if svc.spec.ports:
                for port in svc.spec.ports:
                    port_str = f"{port.port}/{port.protocol}"
                    if hasattr(port, "node_port") and port.node_port:
                        port_str += f":{port.node_port}"
                    ports.append(port_str)
            
            resources.append({
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type,
                "cluster_ip": cluster_ip,
                "external_ips": external_ips,
                "ports": ports,
                "age": svc.metadata.creation_timestamp,
                "selector": svc.spec.selector
            })
        return resources
    
    def _extract_node_list(self, nodes):
        """提取Node列表信息"""
        resources = []
        for node in nodes:
            conditions = {}
            for condition in node.status.conditions:
                conditions[condition.type] = condition.status
            
            # 获取节点角色
            roles = []
            for label in node.metadata.labels:
                if label.startswith("node-role.kubernetes.io/"):
                    roles.append(label.split("/")[1])
            
            # 获取资源使用情况
            capacity = {
                "cpu": node.status.capacity.get("cpu"),
                "memory": node.status.capacity.get("memory"),
                "pods": node.status.capacity.get("pods")
            }
            
            resources.append({
                "name": node.metadata.name,
                "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                "roles": roles,
                "age": node.metadata.creation_timestamp,
                "version": node.status.node_info.kubelet_version,
                "internal_ip": next((addr.address for addr in node.status.addresses if addr.type == "InternalIP"), ""),
                "external_ip": next((addr.address for addr in node.status.addresses if addr.type == "ExternalIP"), ""),
                "os": node.status.node_info.os_image,
                "kernel": node.status.node_info.kernel_version,
                "capacity": capacity
            })
        return resources
    
    def _extract_namespace_list(self, namespaces):
        """提取Namespace列表信息"""
        resources = []
        for ns in namespaces:
            resources.append({
                "name": ns.metadata.name,
                "status": ns.status.phase,
                "age": ns.metadata.creation_timestamp,
                "labels": ns.metadata.labels
            })
        return resources
    
    def _extract_configmap_list(self, configmaps):
        """提取ConfigMap列表信息"""
        resources = []
        for cm in configmaps:
            resources.append({
                "name": cm.metadata.name,
                "namespace": cm.metadata.namespace,
                "data_count": len(cm.data or {}),
                "age": cm.metadata.creation_timestamp
            })
        return resources
    
    def _extract_secret_list(self, secrets):
        """提取Secret列表信息"""
        resources = []
        for secret in secrets:
            resources.append({
                "name": secret.metadata.name,
                "namespace": secret.metadata.namespace,
                "type": secret.type,
                "data_count": len(secret.data or {}),
                "age": secret.metadata.creation_timestamp
            })
        return resources
    
    def _extract_ingress_list(self, ingresses):
        """提取Ingress列表信息"""
        resources = []
        for ing in ingresses:
            # 收集所有主机
            hosts = set()
            if ing.spec.rules:
                for rule in ing.spec.rules:
                    if rule.host:
                        hosts.add(rule.host)
            
            resources.append({
                "name": ing.metadata.name,
                "namespace": ing.metadata.namespace,
                "class": ing.spec.ingress_class_name,
                "hosts": list(hosts),
                "tls": len(ing.spec.tls or []),
                "age": ing.metadata.creation_timestamp
            })
        return resources
    
    def _extract_daemonset_list(self, daemonsets):
        """提取DaemonSet列表信息"""
        resources = []
        for ds in daemonsets:
            resources.append({
                "name": ds.metadata.name,
                "namespace": ds.metadata.namespace,
                "status": f"{ds.status.number_ready or 0}/{ds.status.desired_number_scheduled or 0}",
                "age": ds.metadata.creation_timestamp,
                "containers": len(ds.spec.template.spec.containers) if ds.spec.template and ds.spec.template.spec else 0,
                "images": [container.image for container in ds.spec.template.spec.containers] if ds.spec.template and ds.spec.template.spec else []
            })
        return resources
    
    def _extract_statefulset_list(self, statefulsets):
        """提取StatefulSet列表信息"""
        resources = []
        for sts in statefulsets:
            resources.append({
                "name": sts.metadata.name,
                "namespace": sts.metadata.namespace,
                "replicas": f"{sts.status.ready_replicas or 0}/{sts.spec.replicas}",
                "age": sts.metadata.creation_timestamp,
                "containers": len(sts.spec.template.spec.containers) if sts.spec.template and sts.spec.template.spec else 0,
                "images": [container.image for container in sts.spec.template.spec.containers] if sts.spec.template and sts.spec.template.spec else []
            })
        return resources
    
    def _extract_job_list(self, jobs):
        """提取Job列表信息"""
        resources = []
        for job in jobs:
            # 计算完成率
            completions = job.spec.completions or 1
            succeeded = job.status.succeeded or 0
            completion_rate = f"{succeeded}/{completions}"
            
            # 确定状态
            status = "Unknown"
            if job.status.succeeded == job.spec.completions:
                status = "Complete"
            elif job.status.failed and job.status.failed > 0:
                status = "Failed"
            elif job.status.active and job.status.active > 0:
                status = "Active"
            
            resources.append({
                "name": job.metadata.name,
                "namespace": job.metadata.namespace,
                "completion": completion_rate,
                "status": status,
                "age": job.metadata.creation_timestamp,
                "duration": None if not job.status.start_time else (
                    job.status.completion_time - job.status.start_time if job.status.completion_time 
                    else "Running"
                )
            })
        return resources
    
    def _extract_cronjob_list(self, cronjobs):
        """提取CronJob列表信息"""
        resources = []
        for cj in cronjobs:
            # 确定状态
            suspended = "Suspended" if cj.spec.suspend else "Active"
            
            resources.append({
                "name": cj.metadata.name,
                "namespace": cj.metadata.namespace,
                "schedule": cj.spec.schedule,
                "status": suspended,
                "last_schedule": cj.status.last_schedule_time if hasattr(cj.status, "last_schedule_time") else None,
                "age": cj.metadata.creation_timestamp
            })
        return resources
    
    def _extract_pv_list(self, pvs):
        """提取PersistentVolume列表信息"""
        resources = []
        for pv in pvs:
            resources.append({
                "name": pv.metadata.name,
                "capacity": pv.spec.capacity.get("storage"),
                "access_modes": pv.spec.access_modes,
                "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
                "status": pv.status.phase,
                "claim": f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}" if pv.spec.claim_ref else None,
                "storage_class": pv.spec.storage_class_name,
                "age": pv.metadata.creation_timestamp
            })
        return resources
    
    def _extract_pvc_list(self, pvcs):
        """提取PersistentVolumeClaim列表信息"""
        resources = []
        for pvc in pvcs:
            resources.append({
                "name": pvc.metadata.name,
                "namespace": pvc.metadata.namespace,
                "status": pvc.status.phase,
                "volume": pvc.spec.volume_name,
                "capacity": pvc.status.capacity.get("storage") if hasattr(pvc.status, "capacity") else "未绑定",
                "access_modes": pvc.spec.access_modes,
                "storage_class": pvc.spec.storage_class_name,
                "age": pvc.metadata.creation_timestamp
            })
        return resources
    
    def _format_resource_list(self, resource_type, resources, namespace=None):
        """格式化资源列表为可读文本"""
        if not resources:
            return f"未找到{resource_type}资源" + (f" (命名空间: {namespace})" if namespace else "")
        
        lines = []
        # 添加标题行
        if namespace:
            lines.append(f"{resource_type}资源列表 (命名空间: {namespace})")
        else:
            lines.append(f"{resource_type}资源列表 (所有命名空间)")
        
        # 根据资源类型设置表格头部
        headers = []
        if resource_type in ["pod", "pods"]:
            if not namespace:
                headers = ["名称", "命名空间", "状态", "IP地址", "节点", "就绪", "重启次数", "创建时间"]
            else:
                headers = ["名称", "状态", "IP地址", "节点", "就绪", "重启次数", "创建时间"]
        
        elif resource_type in ["deployment", "deployments"]:
            if not namespace:
                headers = ["名称", "命名空间", "副本", "可用", "创建时间"]
            else:
                headers = ["名称", "副本", "可用", "创建时间"]
        
        elif resource_type in ["service", "services", "svc"]:
            if not namespace:
                headers = ["名称", "命名空间", "类型", "集群IP", "外部IP", "端口", "创建时间"]
            else:
                headers = ["名称", "类型", "集群IP", "外部IP", "端口", "创建时间"]
        
        elif resource_type in ["node", "nodes"]:
            headers = ["名称", "状态", "角色", "版本", "内部IP", "CPU", "内存", "创建时间"]
        
        elif resource_type in ["namespace", "namespaces", "ns"]:
            headers = ["名称", "状态", "创建时间"]
        
        else:
            # 通用表头
            if resource_type not in ["node", "nodes", "namespace", "namespaces", "ns", "persistentvolume", "persistentvolumes", "pv"]:
                headers = ["名称", "命名空间", "创建时间"]
            else:
                headers = ["名称", "创建时间"]
        
        # 添加表格头部
        lines.append(" | ".join(headers))
        lines.append("-" * (sum(len(h) for h in headers) + (len(headers) - 1) * 3))
        
        # 添加数据行
        for resource in resources:
            row = []
            
            if resource_type in ["pod", "pods"]:
                row.append(resource["name"])
                if not namespace:
                    row.append(resource["namespace"])
                row.append(resource["status"])
                row.append(resource["ip"] or "无")
                row.append(resource["node"] or "无")
                row.append(f"{resource['ready_containers']}/{resource['containers']}")
                row.append(str(resource["restarts"]))
                row.append(self._format_timestamp(resource["age"]))
            
            elif resource_type in ["deployment", "deployments"]:
                row.append(resource["name"])
                if not namespace:
                    row.append(resource["namespace"])
                row.append(resource["replicas"])
                row.append(str(resource["available"]))
                row.append(self._format_timestamp(resource["age"]))
            
            elif resource_type in ["service", "services", "svc"]:
                row.append(resource["name"])
                if not namespace:
                    row.append(resource["namespace"])
                row.append(resource["type"])
                row.append(resource["cluster_ip"] or "None")
                row.append(", ".join(resource["external_ips"]) or "无")
                row.append(", ".join(resource["ports"]) or "无")
                row.append(self._format_timestamp(resource["age"]))
            
            elif resource_type in ["node", "nodes"]:
                row.append(resource["name"])
                row.append(resource["status"])
                row.append(", ".join(resource["roles"]) or "无")
                row.append(resource["version"])
                row.append(resource["internal_ip"] or "无")
                row.append(resource["capacity"]["cpu"])
                row.append(resource["capacity"]["memory"])
                row.append(self._format_timestamp(resource["age"]))
            
            elif resource_type in ["namespace", "namespaces", "ns"]:
                row.append(resource["name"])
                row.append(resource["status"])
                row.append(self._format_timestamp(resource["age"]))
            
            else:
                # 通用格式
                row.append(resource["name"])
                if "namespace" in resource and resource_type not in ["node", "nodes", "namespace", "namespaces", "ns", "persistentvolume", "persistentvolumes", "pv"]:
                    row.append(resource["namespace"])
                if "age" in resource:
                    row.append(self._format_timestamp(resource["age"]))
            
            lines.append(" | ".join(row))
        
        lines.append(f"\n资源总数: {len(resources)}")
        return "\n".join(lines)

    def _format_timestamp(self, timestamp):
        """格式化时间戳为人类可读格式"""
        import datetime
        if not timestamp:
            return "未知"
        
        if isinstance(timestamp, str):
            try:
                # 如果是ISO格式的字符串，转为datetime对象
                timestamp = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return timestamp
        
        # 计算与当前时间的差异
        now = datetime.datetime.now(timestamp.tzinfo)
        diff = now - timestamp
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years}y"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months}m"
        elif diff.days > 0:
            return f"{diff.days}d"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m"
        else:
            return f"{diff.seconds}s" 