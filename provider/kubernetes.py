from typing import Any
import yaml
import base64

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from kubernetes import client, config


class DifyPluginKubernetesProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # 验证必要的凭证字段是否存在
            required_fields = ['kubeconfig']
            for field in required_fields:
                if field not in credentials or not credentials[field]:
                    raise ValueError(f"missing required credential field: {field}")
            
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
                    raise ValueError("kubeconfig is empty")
            
                kubeconfig_dict = yaml.safe_load(kubeconfig_str)
                config.load_kube_config_from_dict(kubeconfig_dict)
            except Exception as yaml_error:
                raise ValueError(f"failed to parse kubeconfig: {str(yaml_error)}")
            
            # 尝试获取API版本，验证连接是否正常
            v1 = client.CoreV1Api()
            v1.get_api_resources()
            
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"failed to connect to Kubernetes cluster: {str(e)}")
