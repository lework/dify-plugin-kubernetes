from typing import Any
import tempfile
import os
import yaml
import base64

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from kubernetes import client, config

# 导入Tool类
from tools.list_resources import ListResourcesTool


class DifyPluginKubernetesProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # 验证必要的凭证字段是否存在
            required_fields = ['kubeconfig']
            for field in required_fields:
                if field not in credentials or not credentials[field]:
                    raise ValueError(f"缺少必要的凭证字段: {field}")
            
            # 获取kubeconfig字符串
            kubeconfig_str = credentials['kubeconfig']

            # 尝试进行base64解码，处理填充问题
            try:
                missing_padding = len(kubeconfig_str) % 4
                if missing_padding != 0:
                    kubeconfig_str += '='* (4 - missing_padding)
                    
                # 解码base64字符串
                kubeconfig_str = base64.b64decode(kubeconfig_str).decode('utf-8')
            
                if not kubeconfig_str:
                    raise ValueError("kubeconfig不能为空")
            
                kubeconfig_dict = yaml.safe_load(kubeconfig_str)
                config.load_kube_config_from_dict(kubeconfig_dict)
            except Exception as yaml_error:
                raise ValueError(f"无法解析kubeconfig: {str(yaml_error)}")
            
            # 尝试获取API版本，验证连接是否正常
            v1 = client.CoreV1Api()
            v1.get_api_resources()
            
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"无法连接到Kubernetes集群: {str(e)}")
