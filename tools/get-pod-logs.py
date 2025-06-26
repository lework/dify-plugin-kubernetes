from collections.abc import Generator
from typing import Any
import yaml
import re
import base64
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from dify_plugin.errors.model import InvokeServerUnavailableError

class GetPodLogsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 获取参数
            namespace = tool_parameters.get("namespace", "default").strip().lower()
            pod_name = tool_parameters.get("pod_name", "").strip()
            container_name = tool_parameters.get("container_name", "").strip()
            tail_lines = tool_parameters.get("tail_lines", 20)
            kubeconfig = tool_parameters.get("kubeconfig", "").strip()
            previous_logs = tool_parameters.get("previous_logs", False)

            if not pod_name:
                raise InvokeServerUnavailableError("未配置Pod名称")

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
            v1 = client.CoreV1Api()
            
            try:
                # 获取Pod日志
                logs = v1.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container=container_name,
                    tail_lines=int(tail_lines),
                    pretty=False,
                    previous=previous_logs
                )
                
                # 过滤ANSI颜色代码
                # 匹配类似\u001b[32m的ANSI颜色控制序列
                logs = re.sub(r'\x1b\[[0-9;]*[mK]', '', logs)

                # 输出text
                yield self.create_text_message(f"{logs}")
                
                # 输出json
                yield self.create_json_message({
                    "logs": logs,
                    "pod": pod_name,
                    "namespace": namespace,
                    "container": container_name or "默认容器"
                })
            
            except ApiException as e:
                if e.status == 404:
                    # Pod或容器不存在
                    error_message = ""
                    if "pods" in str(e) and "not found" in str(e).lower():
                        error_message = f"未找到Pod: {pod_name} (命名空间: {namespace})"
                    elif "container" in str(e) and "not found" in str(e).lower():
                        error_message = f"在Pod {pod_name} 中未找到容器: {container_name} (命名空间: {namespace})"
                    else:
                        error_message = f"资源不存在: {str(e)}"
                    
                    # 输出text
                    yield self.create_text_message(error_message)
                    
                    # 输出json
                    yield self.create_json_message({
                        "logs": "",
                        "pod": pod_name,
                        "namespace": namespace,
                        "container": container_name or "默认容器",
                        "status": "NotFound",
                        "message": error_message
                    })
                else:
                    # 其他API错误
                    raise InvokeServerUnavailableError(f"获取Pod日志失败: {str(e)}")
            
        except Exception as e:
            traceback.print_exc()
            raise InvokeServerUnavailableError(f"获取Pod日志失败: {str(e)}") 