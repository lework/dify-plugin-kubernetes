from collections.abc import Generator
from typing import Any
import yaml
import base64
import traceback
from datetime import datetime, timezone

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from dify_plugin.errors.model import InvokeServerUnavailableError

class DescribeResourceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 获取参数
            namespace = tool_parameters.get("namespace", "default").strip().lower()
            resource_type = tool_parameters.get("resource_type", "").strip().lower()
            resource_name = tool_parameters.get("resource_name", "").strip()
            kubeconfig = tool_parameters.get("kubeconfig", "").strip()

            # 验证必要参数
            if not resource_type:
                raise InvokeServerUnavailableError("未配置资源类型")
            if not resource_name:
                raise InvokeServerUnavailableError("未配置资源名称")

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

            # 根据资源类型获取详细信息
            resource_info = {}
            
            try:
                if resource_type == "pod":
                    resource = core_v1.read_namespaced_pod(name=resource_name, namespace=namespace)
                    resource_info = self._extract_pod_info(resource)
                    # 获取Pod相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Pod", resource_name)
                elif resource_type == "deployment":
                    resource = apps_v1.read_namespaced_deployment(name=resource_name, namespace=namespace)
                    resource_info = self._extract_deployment_info(resource)
                    # 获取Deployment相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Deployment", resource_name)
                    # 获取相关ReplicaSet的事件
                    rs_list = apps_v1.list_namespaced_replica_set(
                        namespace=namespace, 
                        label_selector=','.join([f"{k}={v}" for k, v in resource.spec.selector.match_labels.items()])
                    )
                    for rs in rs_list.items:
                        if resource_name in rs.metadata.name:
                            rs_events = self._get_resource_events(core_v1, namespace, "ReplicaSet", rs.metadata.name)
                            if rs_events:
                                resource_info["events"].extend(rs_events)
                elif resource_type == "daemonset":
                    resource = apps_v1.read_namespaced_daemon_set(name=resource_name, namespace=namespace)
                    resource_info = self._extract_daemonset_info(resource)
                    # 获取DaemonSet相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "DaemonSet", resource_name)
                elif resource_type == "statefulset":
                    resource = apps_v1.read_namespaced_stateful_set(name=resource_name, namespace=namespace)
                    resource_info = self._extract_statefulset_info(resource)
                    # 获取StatefulSet相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "StatefulSet", resource_name)
                    # 获取与之关联的PVC事件
                    try:
                        pvc_template = resource.spec.volume_claim_templates
                        if pvc_template:
                            for i, vol_template in enumerate(pvc_template):
                                for j in range(resource.status.replicas or 0):
                                    pvc_name = f"{vol_template.metadata.name}-{resource_name}-{j}"
                                    pvc_events = self._get_resource_events(core_v1, namespace, "PersistentVolumeClaim", pvc_name)
                                    if pvc_events:
                                        resource_info["events"].extend(pvc_events)
                    except Exception:
                        # 如果获取PVC事件失败，不影响主流程
                        pass
                elif resource_type == "service":
                    resource = core_v1.read_namespaced_service(name=resource_name, namespace=namespace)
                    resource_info = self._extract_service_info(resource)
                    # 获取Service相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Service", resource_name)
                elif resource_type == "ingress":
                    resource = networking_v1.read_namespaced_ingress(name=resource_name, namespace=namespace)
                    resource_info = self._extract_ingress_info(resource)
                    # 获取Ingress相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Ingress", resource_name)
                elif resource_type == "configmap":
                    resource = core_v1.read_namespaced_config_map(name=resource_name, namespace=namespace)
                    resource_info = self._extract_configmap_info(resource)
                    # 获取ConfigMap相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "ConfigMap", resource_name)
                elif resource_type== "secret":
                    resource = core_v1.read_namespaced_secret(name=resource_name, namespace=namespace)
                    resource_info = self._extract_secret_info(resource)
                    # 获取Secret相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Secret", resource_name)
                elif resource_type == "job":
                    resource = batch_v1.read_namespaced_job(name=resource_name, namespace=namespace)
                    resource_info = self._extract_job_info(resource)
                    # 获取Job相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "Job", resource_name)
                elif resource_type == "cronjob":
                    resource = batch_v1.read_namespaced_cron_job(name=resource_name, namespace=namespace)
                    resource_info = self._extract_cronjob_info(resource)
                    # 获取CronJob相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "CronJob", resource_name)
                    # 尝试获取由CronJob创建的Job的事件
                    jobs = batch_v1.list_namespaced_job(namespace=namespace)
                    for job in jobs.items:
                        if job.metadata.owner_references:
                            for owner_ref in job.metadata.owner_references:
                                if owner_ref.kind == "CronJob" and owner_ref.name == resource_name:
                                    job_events = self._get_resource_events(core_v1, namespace, "Job", job.metadata.name)
                                    if job_events:
                                        resource_info["events"].extend(job_events)
                elif resource_type == "node":
                    resource = core_v1.read_node(name=resource_name)
                    resource_info = self._extract_node_info(resource)
                    # 获取Node相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, "", "Node", resource_name)
                elif resource_type == "namespace" or resource_type == "ns":
                    resource = core_v1.read_namespace(name=resource_name)
                    resource_info = self._extract_namespace_info(resource)
                    # 获取Namespace相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, "", "Namespace", resource_name)
                elif resource_type == "pv":
                    resource = core_v1.read_persistent_volume(name=resource_name)
                    resource_info = self._extract_pv_info(resource)
                    # 获取PV相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, "", "PersistentVolume", resource_name)
                elif resource_type == "pvc":
                    resource = core_v1.read_namespaced_persistent_volume_claim(name=resource_name, namespace=namespace)
                    resource_info = self._extract_pvc_info(resource)
                    # 获取PVC相关的事件
                    resource_info["events"] = self._get_resource_events(core_v1, namespace, "PersistentVolumeClaim", resource_name)
                else:
                    raise InvokeServerUnavailableError(f"不支持的资源类型: {resource_type}")
            except ApiException as e:
                if e.status == 404:
                    # 资源不存在，返回空数据
                    resource_info = {
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "namespace": namespace if resource_type not in ["node", "pv", "namespace", "ns"] else "",
                        "status": "NotFound",
                        "message": f"资源 {resource_name} 不存在"
                    }
                    
                    # 输出text
                    message = f"未找到资源: {resource_type}/{resource_name}"
                    if resource_type not in ["node", "pv", "namespace", "ns"]:
                        message += f" (命名空间: {namespace})"
                    
                    yield self.create_text_message(message)
                    yield self.create_json_message(resource_info)
                    return
                else:
                    # 其他API错误
                    raise InvokeServerUnavailableError(f"获取资源信息失败: {str(e)}")

            # 格式化输出文本
            text_message = self._format_resource_info(resource_type, resource_name, namespace, resource_info)
            
            # 输出text
            yield self.create_text_message(text_message)
            
            # 输出json
            resource_info["resource_type"] = resource_type
            resource_info["resource_name"] = resource_name
            resource_info["namespace"] = namespace
            
            yield self.create_json_message(resource_info)
            
        except Exception as e:
            traceback.print_exc()
            raise InvokeServerUnavailableError(f"获取资源信息失败: {str(e)}")

    def _get_resource_events(self, api, namespace, kind, name):
        """获取资源相关的事件"""
        try:
            field_selector = f"involvedObject.kind={kind},involvedObject.name={name}"
            
            # 集群级资源和命名空间级资源的事件查询方式不同
            if namespace:
                events = api.list_namespaced_event(namespace=namespace, field_selector=field_selector)
            else:
                events = api.list_event_for_all_namespaces(field_selector=field_selector)
            
            event_list = []
            for event in events.items:
                event_info = {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "first_timestamp": event.first_timestamp,
                    "last_timestamp": event.last_timestamp,
                    "source": f"{event.source.component or '未知'}{f'/{event.source.host}' if event.source.host else ''}",
                }
                event_list.append(event_info)
            
            # 按最后发生时间排序，最近的事件排在前面
            event_list.sort(key=lambda x: x["last_timestamp"] if x["last_timestamp"] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            return event_list
        except ApiException as e:
            if e.status == 404:
                # 命名空间或事件资源不存在，返回空列表
                return []
            # 其他API错误，记录错误信息但继续执行主流程
            return []
        except Exception as e:
            # 如果获取事件失败，返回空列表并不影响主要信息的展示
            return []

    def _extract_daemonset_info(self, daemonset):
        """提取DaemonSet详细信息"""
        info = {
            "name": daemonset.metadata.name,
            "namespace": daemonset.metadata.namespace,
            "selector": daemonset.spec.selector.match_labels,
            "update_strategy": daemonset.spec.update_strategy.type,
            "status": {
                "current_number_scheduled": daemonset.status.current_number_scheduled,
                "desired_number_scheduled": daemonset.status.desired_number_scheduled,
                "number_available": daemonset.status.number_available,
                "number_misscheduled": daemonset.status.number_misscheduled,
                "number_ready": daemonset.status.number_ready,
                "number_unavailable": daemonset.status.number_unavailable if hasattr(daemonset.status, "number_unavailable") else 0
            },
            "containers": [],
            "conditions": [
                {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                    "last_transition_time": condition.last_transition_time
                } for condition in daemonset.status.conditions
            ] if daemonset.status.conditions else []
        }
        
        # 提取Pod模板中的容器资源配置
        if daemonset.spec.template and daemonset.spec.template.spec and daemonset.spec.template.spec.containers:
            for container in daemonset.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image
                }
                
                # 提取容器资源请求和限制信息
                if container.resources:
                    container_info["resources"] = {
                        "requests": {},
                        "limits": {}
                    }
                    
                    # 资源请求
                    if container.resources.requests:
                        if "cpu" in container.resources.requests:
                            container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                        if "memory" in container.resources.requests:
                            container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                    
                    # 资源限制
                    if container.resources.limits:
                        if "cpu" in container.resources.limits:
                            container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                        if "memory" in container.resources.limits:
                            container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
                
                info["containers"].append(container_info)
        
        return info
    
    def _extract_statefulset_info(self, statefulset):
        """提取StatefulSet详细信息"""
        info = {
            "name": statefulset.metadata.name,
            "namespace": statefulset.metadata.namespace,
            "replicas": {
                "desired": statefulset.spec.replicas,
                "current": statefulset.status.current_replicas if hasattr(statefulset.status, "current_replicas") else 0,
                "ready": statefulset.status.ready_replicas if hasattr(statefulset.status, "ready_replicas") else 0,
                "updated": statefulset.status.updated_replicas if hasattr(statefulset.status, "updated_replicas") else 0
            },
            "selector": statefulset.spec.selector.match_labels,
            "service_name": statefulset.spec.service_name,
            "update_strategy": statefulset.spec.update_strategy.type,
            "pod_management_policy": statefulset.spec.pod_management_policy,
            "volume_claim_templates": [],
            "containers": [],
            "conditions": [
                {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                    "last_transition_time": condition.last_transition_time
                } for condition in statefulset.status.conditions
            ] if statefulset.status.conditions else []
        }
        
        # 提取卷声明模板
        if statefulset.spec.volume_claim_templates:
            for template in statefulset.spec.volume_claim_templates:
                template_info = {
                    "name": template.metadata.name,
                    "access_modes": template.spec.access_modes,
                    "storage": template.spec.resources.requests.get("storage") if template.spec.resources.requests else None,
                    "storage_class": template.spec.storage_class_name
                }
                info["volume_claim_templates"].append(template_info)
        
        # 提取Pod模板中的容器资源配置
        if statefulset.spec.template and statefulset.spec.template.spec and statefulset.spec.template.spec.containers:
            for container in statefulset.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image
                }
                
                # 提取容器资源请求和限制信息
                if container.resources:
                    container_info["resources"] = {
                        "requests": {},
                        "limits": {}
                    }
                    
                    # 资源请求
                    if container.resources.requests:
                        if "cpu" in container.resources.requests:
                            container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                        if "memory" in container.resources.requests:
                            container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                    
                    # 资源限制
                    if container.resources.limits:
                        if "cpu" in container.resources.limits:
                            container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                        if "memory" in container.resources.limits:
                            container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
                
                info["containers"].append(container_info)
        
        return info

    def _extract_pod_info(self, pod):
        """提取Pod详细信息"""
        info = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "ip": pod.status.pod_ip,
            "node": pod.spec.node_name,
            "start_time": pod.status.start_time,
            "containers": []
        }
        
        for container in pod.spec.containers:
            container_info = {
                "name": container.name,
                "image": container.image,
                "ports": [{"container_port": p.container_port, "protocol": p.protocol} for p in (container.ports or [])]
            }
            
            # 提取容器资源请求和限制信息
            if container.resources:
                container_info["resources"] = {
                    "requests": {},
                    "limits": {}
                }
                
                # 资源请求
                if container.resources.requests:
                    if "cpu" in container.resources.requests:
                        container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                    if "memory" in container.resources.requests:
                        container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                
                # 资源限制
                if container.resources.limits:
                    if "cpu" in container.resources.limits:
                        container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                    if "memory" in container.resources.limits:
                        container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
            
            # 获取容器状态
            if pod.status.container_statuses:
                for status in pod.status.container_statuses:
                    if status.name == container.name:
                        container_info["ready"] = status.ready
                        container_info["restart_count"] = status.restart_count
                        if status.state.running:
                            container_info["state"] = "Running"
                            container_info["started_at"] = status.state.running.started_at
                        elif status.state.waiting:
                            container_info["state"] = f"Waiting: {status.state.waiting.reason}"
                            if status.state.waiting.message:
                                container_info["message"] = status.state.waiting.message
                        elif status.state.terminated:
                            container_info["state"] = f"Terminated: {status.state.terminated.reason}"
                            if status.state.terminated.message:
                                container_info["message"] = status.state.terminated.message
            
            info["containers"].append(container_info)
        
        # 获取事件
        if pod.status.conditions:
            info["conditions"] = []
            for condition in pod.status.conditions:
                info["conditions"].append({
                    "type": condition.type,
                    "status": condition.status,
                    "last_transition_time": condition.last_transition_time,
                    "reason": condition.reason,
                    "message": condition.message
                })
        
        return info

    def _extract_deployment_info(self, deployment):
        """提取Deployment详细信息"""
        info = {
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "replicas": {
                "desired": deployment.spec.replicas,
                "current": deployment.status.replicas,
                "available": deployment.status.available_replicas,
                "unavailable": deployment.status.unavailable_replicas
            },
            "selector": deployment.spec.selector.match_labels,
            "strategy": {
                "type": deployment.spec.strategy.type,
                "max_surge": deployment.spec.strategy.rolling_update.max_surge if deployment.spec.strategy.rolling_update else None,
                "max_unavailable": deployment.spec.strategy.rolling_update.max_unavailable if deployment.spec.strategy.rolling_update else None
            },
            "containers": [],
            "conditions": [
                {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message
                } for condition in deployment.status.conditions
            ] if deployment.status.conditions else []
        }
        
        # 提取Pod模板中的容器资源配置
        if deployment.spec.template and deployment.spec.template.spec and deployment.spec.template.spec.containers:
            for container in deployment.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image
                }
                
                # 提取容器资源请求和限制信息
                if container.resources:
                    container_info["resources"] = {
                        "requests": {},
                        "limits": {}
                    }
                    
                    # 资源请求
                    if container.resources.requests:
                        if "cpu" in container.resources.requests:
                            container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                        if "memory" in container.resources.requests:
                            container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                    
                    # 资源限制
                    if container.resources.limits:
                        if "cpu" in container.resources.limits:
                            container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                        if "memory" in container.resources.limits:
                            container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
                
                info["containers"].append(container_info)
        
        return info

    def _extract_service_info(self, service):
        """提取Service详细信息"""
        info = {
            "name": service.metadata.name,
            "namespace": service.metadata.namespace,
            "type": service.spec.type,
            "cluster_ip": service.spec.cluster_ip,
            "selector": service.spec.selector,
            "ports": []
        }
        
        if service.spec.ports:
            for port in service.spec.ports:
                port_info = {
                    "name": port.name,
                    "port": port.port,
                    "target_port": port.target_port,
                    "protocol": port.protocol
                }
                if service.spec.type == "NodePort":
                    port_info["node_port"] = port.node_port
                info["ports"].append(port_info)
                
        # 如果是LoadBalancer类型，添加external IP
        if service.spec.type == "LoadBalancer" and hasattr(service.status, "load_balancer") and \
           hasattr(service.status.load_balancer, "ingress") and service.status.load_balancer.ingress:
            info["external_ips"] = [ingress.ip for ingress in service.status.load_balancer.ingress if hasattr(ingress, "ip")]
            
        return info

    def _extract_ingress_info(self, ingress):
        """提取Ingress详细信息"""
        rules = []
        if ingress.spec.rules:
            for rule in ingress.spec.rules:
                rule_info = {"host": rule.host, "paths": []}
                if rule.http and rule.http.paths:
                    for path in rule.http.paths:
                        rule_info["paths"].append({
                            "path": path.path,
                            "path_type": path.path_type,
                            "service_name": path.backend.service.name if path.backend.service else None,
                            "service_port": path.backend.service.port.number if path.backend.service and path.backend.service.port else None
                        })
                rules.append(rule_info)
        
        return {
            "name": ingress.metadata.name,
            "namespace": ingress.metadata.namespace,
            "class": ingress.spec.ingress_class_name,
            "tls": [{"hosts": tls.hosts, "secret_name": tls.secret_name} for tls in ingress.spec.tls] if ingress.spec.tls else [],
            "rules": rules
        }

    def _extract_configmap_info(self, configmap):
        """提取ConfigMap详细信息"""
        return {
            "name": configmap.metadata.name,
            "namespace": configmap.metadata.namespace,
            "data": configmap.data,
            "binary_data": configmap.binary_data
        }

    def _extract_secret_info(self, secret):
        """提取Secret详细信息"""
        # 不显示实际的secret值，只显示键名
        data = {}
        if secret.data:
            data = {key: "[SECRET]" for key in secret.data.keys()}
        
        return {
            "name": secret.metadata.name,
            "namespace": secret.metadata.namespace,
            "type": secret.type,
            "data_keys": list(data.keys())
        }

    def _extract_job_info(self, job):
        """提取Job详细信息"""
        info = {
            "name": job.metadata.name,
            "namespace": job.metadata.namespace,
            "completions": job.spec.completions,
            "parallelism": job.spec.parallelism,
            "status": {
                "active": job.status.active,
                "succeeded": job.status.succeeded,
                "failed": job.status.failed
            },
            "start_time": job.status.start_time,
            "completion_time": job.status.completion_time,
            "containers": []
        }
        
        # 提取Pod模板中的容器资源配置
        if job.spec.template and job.spec.template.spec and job.spec.template.spec.containers:
            for container in job.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image
                }
                
                # 提取容器资源请求和限制信息
                if container.resources:
                    container_info["resources"] = {
                        "requests": {},
                        "limits": {}
                    }
                    
                    # 资源请求
                    if container.resources.requests:
                        if "cpu" in container.resources.requests:
                            container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                        if "memory" in container.resources.requests:
                            container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                    
                    # 资源限制
                    if container.resources.limits:
                        if "cpu" in container.resources.limits:
                            container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                        if "memory" in container.resources.limits:
                            container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
                
                info["containers"].append(container_info)
        
        return info

    def _extract_cronjob_info(self, cronjob):
        """提取CronJob详细信息"""
        info = {
            "name": cronjob.metadata.name,
            "namespace": cronjob.metadata.namespace,
            "schedule": cronjob.spec.schedule,
            "suspend": cronjob.spec.suspend,
            "concurrency_policy": cronjob.spec.concurrency_policy,
            "last_schedule_time": cronjob.status.last_schedule_time if hasattr(cronjob.status, "last_schedule_time") else None,
            "active_jobs": len(cronjob.status.active) if hasattr(cronjob.status, "active") and cronjob.status.active else 0,
            "containers": []
        }
        
        # 提取Job模板中的Pod模板中的容器资源配置
        if (cronjob.spec.job_template and cronjob.spec.job_template.spec and 
            cronjob.spec.job_template.spec.template and cronjob.spec.job_template.spec.template.spec and 
            cronjob.spec.job_template.spec.template.spec.containers):
            
            for container in cronjob.spec.job_template.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image
                }
                
                # 提取容器资源请求和限制信息
                if container.resources:
                    container_info["resources"] = {
                        "requests": {},
                        "limits": {}
                    }
                    
                    # 资源请求
                    if container.resources.requests:
                        if "cpu" in container.resources.requests:
                            container_info["resources"]["requests"]["cpu"] = container.resources.requests["cpu"]
                        if "memory" in container.resources.requests:
                            container_info["resources"]["requests"]["memory"] = container.resources.requests["memory"]
                    
                    # 资源限制
                    if container.resources.limits:
                        if "cpu" in container.resources.limits:
                            container_info["resources"]["limits"]["cpu"] = container.resources.limits["cpu"]
                        if "memory" in container.resources.limits:
                            container_info["resources"]["limits"]["memory"] = container.resources.limits["memory"]
                
                info["containers"].append(container_info)
        
        return info

    def _extract_node_info(self, node):
        """提取Node详细信息"""
        node_info = {
            "name": node.metadata.name,
            "status": "Ready" if any(condition.type == "Ready" and condition.status == "True" for condition in node.status.conditions) else "NotReady",
            "roles": [],
            "architecture": node.status.node_info.architecture,
            "kernel_version": node.status.node_info.kernel_version,
            "os_image": node.status.node_info.os_image,
            "kubelet_version": node.status.node_info.kubelet_version,
            "capacity": {
                "cpu": node.status.capacity.get("cpu"),
                "memory": node.status.capacity.get("memory"),
                "pods": node.status.capacity.get("pods")
            },
            "allocatable": {
                "cpu": node.status.allocatable.get("cpu"),
                "memory": node.status.allocatable.get("memory"),
                "pods": node.status.allocatable.get("pods")
            },
            "conditions": []
        }
        
        # 获取节点角色
        for label in node.metadata.labels:
            if label.startswith("node-role.kubernetes.io/"):
                node_info["roles"].append(label.split("/")[1])
        
        # 提取节点状态条件
        for condition in node.status.conditions:
            node_info["conditions"].append({
                "type": condition.type,
                "status": condition.status,
                "last_transition_time": condition.last_transition_time,
                "reason": condition.reason,
                "message": condition.message
            })
        
        return node_info

    def _extract_namespace_info(self, namespace):
        """提取Namespace详细信息"""
        return {
            "name": namespace.metadata.name,
            "status": namespace.status.phase,
            "created_at": namespace.metadata.creation_timestamp,
            "labels": namespace.metadata.labels,
            "annotations": namespace.metadata.annotations
        }

    def _extract_pv_info(self, pv):
        """提取PersistentVolume详细信息"""
        return {
            "name": pv.metadata.name,
            "capacity": pv.spec.capacity.get("storage"),
            "access_modes": pv.spec.access_modes,
            "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
            "status": pv.status.phase,
            "claim": f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}" if pv.spec.claim_ref else None,
            "storage_class": pv.spec.storage_class_name
        }

    def _extract_pvc_info(self, pvc):
        """提取PersistentVolumeClaim详细信息"""
        return {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,
            "volume": pvc.spec.volume_name,
            "capacity": pvc.status.capacity.get("storage") if hasattr(pvc.status, "capacity") else None,
            "access_modes": pvc.spec.access_modes,
            "storage_class": pvc.spec.storage_class_name
        }

    def _format_resource_info(self, resource_type, resource_name, namespace, info):
        """格式化资源信息为可读文本"""
        lines = []
        lines.append(f"名称: {resource_name}")
        lines.append(f"类型: {resource_type}")
        
        if resource_type != "node" and resource_type != "namespace" and resource_type != "pv":
            lines.append(f"命名空间: {namespace}")
        
        # 根据资源类型添加不同格式的详细信息
        if resource_type == "pod":
            lines.append(f"状态: {info['status']}")
            lines.append(f"Pod IP: {info['ip'] or '无'}")
            lines.append(f"节点: {info['node'] or '无'}")
            lines.append(f"启动时间: {info['start_time']}")
            
            lines.append("\n容器:")
            for container in info["containers"]:
                lines.append(f"  - 名称: {container['name']}")
                lines.append(f"    镜像: {container['image']}")
                
                # 添加资源请求和限制信息显示
                if "resources" in container:
                    resources = container["resources"]
                    
                    # 显示资源请求
                    if resources.get("requests"):
                        requests = []
                        if "cpu" in resources["requests"]:
                            requests.append(f"CPU: {resources['requests']['cpu']}")
                        if "memory" in resources["requests"]:
                            requests.append(f"内存: {resources['requests']['memory']}")
                        
                        if requests:
                            lines.append(f"    资源请求: {', '.join(requests)}")
                    
                    # 显示资源限制
                    if resources.get("limits"):
                        limits = []
                        if "cpu" in resources["limits"]:
                            limits.append(f"CPU: {resources['limits']['cpu']}")
                        if "memory" in resources["limits"]:
                            limits.append(f"内存: {resources['limits']['memory']}")
                        
                        if limits:
                            lines.append(f"    资源限制: {', '.join(limits)}")
                
                if "state" in container:
                    lines.append(f"    状态: {container['state']}")
                if "message" in container:
                    lines.append(f"    消息: {container['message']}")
                if "ready" in container:
                    lines.append(f"    就绪: {container['ready']}")
                if "restart_count" in container:
                    lines.append(f"    重启次数: {container['restart_count']}")
                
                if container.get("ports"):
                    port_strs = []
                    for port in container['ports']:
                        port_strs.append(f"{port['container_port']}/{port['protocol']}")
                    lines.append(f"    端口: {', '.join(port_strs)}")
            
            if "conditions" in info and info["conditions"]:
                lines.append("\n状态条件:")
                for condition in info["conditions"]:
                    lines.append(f"  - 类型: {condition['type']}")
                    lines.append(f"    状态: {condition['status']}")
                    lines.append(f"    原因: {condition['reason'] or '无'}")
                    if condition.get("message"):
                        lines.append(f"    消息: {condition['message']}")
        
        elif resource_type == "deployment":
            lines.append(f"副本状态:")
            lines.append(f"  期望副本数: {info['replicas']['desired']}")
            lines.append(f"  当前副本数: {info['replicas']['current']}")
            lines.append(f"  可用副本数: {info['replicas']['available'] or 0}")
            lines.append(f"  不可用副本数: {info['replicas']['unavailable'] or 0}")
            
            lines.append(f"\n选择器:")
            for key, value in info['selector'].items():
                lines.append(f"  {key}: {value}")
            
            lines.append(f"\n部署策略: {info['strategy']['type']}")
            if info['strategy']['type'] == 'RollingUpdate':
                lines.append(f"  最大增量: {info['strategy']['max_surge']}")
                lines.append(f"  最大不可用: {info['strategy']['max_unavailable']}")
            
            # 添加容器配置信息
            if info.get("containers"):
                lines.append("\n容器配置:")
                for container in info["containers"]:
                    lines.append(f"  - 名称: {container['name']}")
                    lines.append(f"    镜像: {container['image']}")
                    
                    # 添加资源请求和限制信息显示
                    if "resources" in container:
                        resources = container["resources"]
                        
                        # 显示资源请求
                        if resources.get("requests"):
                            requests = []
                            if "cpu" in resources["requests"]:
                                requests.append(f"CPU: {resources['requests']['cpu']}")
                            if "memory" in resources["requests"]:
                                requests.append(f"内存: {resources['requests']['memory']}")
                            
                            if requests:
                                lines.append(f"    资源请求: {', '.join(requests)}")
                        
                        # 显示资源限制
                        if resources.get("limits"):
                            limits = []
                            if "cpu" in resources["limits"]:
                                limits.append(f"CPU: {resources['limits']['cpu']}")
                            if "memory" in resources["limits"]:
                                limits.append(f"内存: {resources['limits']['memory']}")
                            
                            if limits:
                                lines.append(f"    资源限制: {', '.join(limits)}")
            
            if info['conditions']:
                lines.append("\n状态条件:")
                for condition in info['conditions']:
                    lines.append(f"  - 类型: {condition['type']}")
                    lines.append(f"    状态: {condition['status']}")
                    lines.append(f"    原因: {condition['reason']}")
                    lines.append(f"    消息: {condition['message']}")

        elif resource_type == "daemonset":
            lines.append(f"状态:")
            lines.append(f"  期望数量: {info['status']['desired_number_scheduled']}")
            lines.append(f"  当前数量: {info['status']['current_number_scheduled']}")
            lines.append(f"  就绪数量: {info['status']['number_ready']}")
            lines.append(f"  可用数量: {info['status']['number_available']}")
            lines.append(f"  错误调度数量: {info['status']['number_misscheduled']}")
            lines.append(f"  不可用数量: {info['status']['number_unavailable']}")
            
            lines.append(f"\n选择器:")
            for key, value in info['selector'].items():
                lines.append(f"  {key}: {value}")
            
            lines.append(f"\n更新策略: {info['update_strategy']}")
            
            # 添加容器配置信息
            if info.get("containers"):
                lines.append("\n容器配置:")
                for container in info["containers"]:
                    lines.append(f"  - 名称: {container['name']}")
                    lines.append(f"    镜像: {container['image']}")
                    
                    # 添加资源请求和限制信息显示
                    if "resources" in container:
                        resources = container["resources"]
                        
                        # 显示资源请求
                        if resources.get("requests"):
                            requests = []
                            if "cpu" in resources["requests"]:
                                requests.append(f"CPU: {resources['requests']['cpu']}")
                            if "memory" in resources["requests"]:
                                requests.append(f"内存: {resources['requests']['memory']}")
                            
                            if requests:
                                lines.append(f"    资源请求: {', '.join(requests)}")
                        
                        # 显示资源限制
                        if resources.get("limits"):
                            limits = []
                            if "cpu" in resources["limits"]:
                                limits.append(f"CPU: {resources['limits']['cpu']}")
                            if "memory" in resources["limits"]:
                                limits.append(f"内存: {resources['limits']['memory']}")
                            
                            if limits:
                                lines.append(f"    资源限制: {', '.join(limits)}")
            
            if info['conditions']:
                lines.append("\n状态条件:")
                for condition in info['conditions']:
                    lines.append(f"  - 类型: {condition['type']}")
                    lines.append(f"    状态: {condition['status']}")
                    lines.append(f"    原因: {condition['reason']}")
                    lines.append(f"    消息: {condition['message']}")
        
        elif resource_type == "statefulset":
            lines.append(f"副本状态:")
            lines.append(f"  期望副本数: {info['replicas']['desired']}")
            lines.append(f"  当前副本数: {info['replicas']['current']}")
            lines.append(f"  就绪副本数: {info['replicas']['ready']}")
            lines.append(f"  已更新副本数: {info['replicas']['updated']}")
            
            lines.append(f"\n选择器:")
            for key, value in info['selector'].items():
                lines.append(f"  {key}: {value}")
            
            lines.append(f"\n服务名称: {info['service_name']}")
            lines.append(f"更新策略: {info['update_strategy']}")
            lines.append(f"Pod管理策略: {info['pod_management_policy']}")
            
            # 添加容器配置信息
            if info.get("containers"):
                lines.append("\n容器配置:")
                for container in info["containers"]:
                    lines.append(f"  - 名称: {container['name']}")
                    lines.append(f"    镜像: {container['image']}")
                    
                    # 添加资源请求和限制信息显示
                    if "resources" in container:
                        resources = container["resources"]
                        
                        # 显示资源请求
                        if resources.get("requests"):
                            requests = []
                            if "cpu" in resources["requests"]:
                                requests.append(f"CPU: {resources['requests']['cpu']}")
                            if "memory" in resources["requests"]:
                                requests.append(f"内存: {resources['requests']['memory']}")
                            
                            if requests:
                                lines.append(f"    资源请求: {', '.join(requests)}")
                        
                        # 显示资源限制
                        if resources.get("limits"):
                            limits = []
                            if "cpu" in resources["limits"]:
                                limits.append(f"CPU: {resources['limits']['cpu']}")
                            if "memory" in resources["limits"]:
                                limits.append(f"内存: {resources['limits']['memory']}")
                            
                            if limits:
                                lines.append(f"    资源限制: {', '.join(limits)}")
            
            if info['volume_claim_templates']:
                lines.append("\n卷声明模板:")
                for template in info['volume_claim_templates']:
                    lines.append(f"  - 名称: {template['name']}")
                    lines.append(f"    存储: {template['storage']}")
                    lines.append(f"    访问模式: {', '.join(template['access_modes'])}")
                    lines.append(f"    存储类: {template['storage_class'] or '默认'}")
            
            if info['conditions']:
                lines.append("\n状态条件:")
                for condition in info['conditions']:
                    lines.append(f"  - 类型: {condition['type']}")
                    lines.append(f"    状态: {condition['status']}")
                    lines.append(f"    原因: {condition['reason']}")
                    lines.append(f"    消息: {condition['message']}")
        
        elif resource_type == "service":
            lines.append(f"类型: {info['type']}")
            lines.append(f"集群IP: {info['cluster_ip']}")
            
            if info.get("external_ips"):
                lines.append(f"外部IP: {', '.join(info['external_ips'])}")
            
            lines.append("\n端口:")
            for port in info["ports"]:
                port_line = f"  - {port['port']} -> {port['target_port']} ({port['protocol']})"
                if "node_port" in port:
                    port_line += f", NodePort: {port['node_port']}"
                lines.append(port_line)
            
            if info.get("selector"):
                lines.append("\n选择器:")
                for key, value in info["selector"].items():
                    lines.append(f"  {key}: {value}")
        
        elif resource_type == "ingress":
            lines.append(f"Ingress类: {info.get('class', '默认')}")
            
            if info.get("tls"):
                lines.append("\nTLS配置:")
                for tls in info["tls"]:
                    lines.append(f"  - 密钥: {tls['secret_name']}")
                    lines.append(f"    主机: {', '.join(tls['hosts'])}")
            
            lines.append("\n规则:")
            for rule in info["rules"]:
                lines.append(f"  - 主机: {rule['host'] or '*'}")
                for path in rule["paths"]:
                    lines.append(f"    路径: {path['path']} ({path['path_type']})")
                    lines.append(f"    后端: {path['service_name']}:{path['service_port']}")
                    
        elif resource_type == "configmap":
            data_count = len(info.get("data", {}))
            binary_data_count = len(info.get("binary_data", {}))
            
            lines.append(f"数据条目数: {data_count}")
            lines.append(f"二进制数据条目数: {binary_data_count}")
            
            if data_count > 0:
                lines.append("\n数据键:")
                for key in info["data"].keys():
                    lines.append(f"  - {key}")
            
            if binary_data_count > 0:
                lines.append("\n二进制数据键:")
                for key in info["binary_data"].keys():
                    lines.append(f"  - {key}")
        
        elif resource_type == "secret":
            lines.append(f"类型: {info['type']}")
            
            if info.get("data_keys"):
                lines.append("\n数据键:")
                for key in info["data_keys"]:
                    lines.append(f"  - {key}")
        
        elif resource_type == "job":
            lines.append(f"完成数: {info['completions']}")
            lines.append(f"并行度: {info['parallelism']}")
            lines.append(f"开始时间: {info['start_time'] or '未开始'}")
            lines.append(f"完成时间: {info['completion_time'] or '未完成'}")
            
            lines.append(f"\n状态:")
            lines.append(f"  活动: {info['status']['active'] or 0}")
            lines.append(f"  成功: {info['status']['succeeded'] or 0}")
            lines.append(f"  失败: {info['status']['failed'] or 0}")
            
            # 添加容器配置信息
            if info.get("containers"):
                lines.append("\n容器配置:")
                for container in info["containers"]:
                    lines.append(f"  - 名称: {container['name']}")
                    lines.append(f"    镜像: {container['image']}")
                    
                    # 添加资源请求和限制信息显示
                    if "resources" in container:
                        resources = container["resources"]
                        
                        # 显示资源请求
                        if resources.get("requests"):
                            requests = []
                            if "cpu" in resources["requests"]:
                                requests.append(f"CPU: {resources['requests']['cpu']}")
                            if "memory" in resources["requests"]:
                                requests.append(f"内存: {resources['requests']['memory']}")
                            
                            if requests:
                                lines.append(f"    资源请求: {', '.join(requests)}")
                        
                        # 显示资源限制
                        if resources.get("limits"):
                            limits = []
                            if "cpu" in resources["limits"]:
                                limits.append(f"CPU: {resources['limits']['cpu']}")
                            if "memory" in resources["limits"]:
                                limits.append(f"内存: {resources['limits']['memory']}")
                            
                            if limits:
                                lines.append(f"    资源限制: {', '.join(limits)}")
        
        elif resource_type == "cronjob":
            lines.append(f"调度: {info['schedule']}")
            lines.append(f"暂停: {'是' if info['suspend'] else '否'}")
            lines.append(f"并发策略: {info['concurrency_policy']}")
            lines.append(f"最后调度时间: {info['last_schedule_time'] or '未调度'}")
            lines.append(f"活动任务数: {info['active_jobs']}")
            
            # 添加容器配置信息
            if info.get("containers"):
                lines.append("\n容器配置:")
                for container in info["containers"]:
                    lines.append(f"  - 名称: {container['name']}")
                    lines.append(f"    镜像: {container['image']}")
                    
                    # 添加资源请求和限制信息显示
                    if "resources" in container:
                        resources = container["resources"]
                        
                        # 显示资源请求
                        if resources.get("requests"):
                            requests = []
                            if "cpu" in resources["requests"]:
                                requests.append(f"CPU: {resources['requests']['cpu']}")
                            if "memory" in resources["requests"]:
                                requests.append(f"内存: {resources['requests']['memory']}")
                            
                            if requests:
                                lines.append(f"    资源请求: {', '.join(requests)}")
                        
                        # 显示资源限制
                        if resources.get("limits"):
                            limits = []
                            if "cpu" in resources["limits"]:
                                limits.append(f"CPU: {resources['limits']['cpu']}")
                            if "memory" in resources["limits"]:
                                limits.append(f"内存: {resources['limits']['memory']}")
                            
                            if limits:
                                lines.append(f"    资源限制: {', '.join(limits)}")
        
        elif resource_type == "node":
            lines.append(f"状态: {info['status']}")
            
            if info["roles"]:
                lines.append(f"角色: {', '.join(info['roles'])}")
            
            lines.append(f"\n系统信息:")
            lines.append(f"  架构: {info['architecture']}")
            lines.append(f"  操作系统: {info['os_image']}")
            lines.append(f"  内核版本: {info['kernel_version']}")
            lines.append(f"  Kubelet版本: {info['kubelet_version']}")
            
            lines.append(f"\n容量:")
            lines.append(f"  CPU: {info['capacity']['cpu']}")
            lines.append(f"  内存: {info['capacity']['memory']}")
            lines.append(f"  Pod数: {info['capacity']['pods']}")
            
            lines.append(f"\n可分配资源:")
            lines.append(f"  CPU: {info['allocatable']['cpu']}")
            lines.append(f"  内存: {info['allocatable']['memory']}")
            lines.append(f"  Pod数: {info['allocatable']['pods']}")
            
            lines.append(f"\n状态条件:")
            for condition in info["conditions"]:
                lines.append(f"  - {condition['type']}: {condition['status']}")
                if condition.get("reason"):
                    lines.append(f"    原因: {condition['reason']}")
                if condition.get("message"):
                    lines.append(f"    消息: {condition['message']}")
        
        elif resource_type == "namespace" or resource_type == "ns":
            lines.append(f"状态: {info['status']}")
            lines.append(f"创建时间: {info['created_at']}")
            
            if info.get("labels"):
                lines.append("\n标签:")
                for key, value in info["labels"].items():
                    lines.append(f"  {key}: {value}")
        
        elif resource_type == "pv":
            lines.append(f"状态: {info['status']}")
            lines.append(f"容量: {info['capacity']}")
            lines.append(f"访问模式: {', '.join(info['access_modes'])}")
            lines.append(f"回收策略: {info['reclaim_policy']}")
            lines.append(f"存储类: {info['storage_class'] or '无'}")
            
            if info["claim"]:
                lines.append(f"绑定的PVC: {info['claim']}")
        
        elif resource_type == "pvc":
            lines.append(f"状态: {info['status']}")
            lines.append(f"容量: {info['capacity'] or '未设置'}")
            lines.append(f"访问模式: {', '.join(info['access_modes'])}")
            lines.append(f"存储类: {info['storage_class'] or '无'}")
            lines.append(f"绑定的PV: {info['volume'] or '无'}")
        
        # 添加事件信息部分
        if "events" in info and info["events"]:
            lines.append("\n事件:")
            for event in info["events"]:
                event_line = f"  - 类型: {event['type']} 原因: {event['reason']} ({event['count']}次)"
                timestamp_info = ""
                if event.get("last_timestamp"):
                    timestamp_info = f"最近: {event['last_timestamp']}"
                lines.append(event_line)
                lines.append(f"    消息: {event['message']}")
                lines.append(f"    来源: {event['source']}")
                if timestamp_info:
                    lines.append(f"    {timestamp_info}")
        elif "events" in info and not info["events"]:
            lines.append("\n事件: 无")
        
        return "\n".join(lines) 