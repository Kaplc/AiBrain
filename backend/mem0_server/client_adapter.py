"""
Mem0HttpClient — mem0 服务的 HTTP 客户端适配器

接口与 mem0 Memory 客户端完全一致（add/search/delete/update/get_all/get），
调用方无感知切换。通过 HTTP 调用 mem0 独立服务进程。

优雅降级：服务不可用时返回空结果，不阻塞主流程。
"""
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger('mem0_adapter')

# 默认超时（秒）
_TIMEOUT = 30


class Mem0HttpClient:
    """通过 HTTP 调用 mem0 独立服务，接口与 mem0.Memory 兼容"""

    def __init__(self, host='127.0.0.1', port=19401):
        self._base = f'http://{host}:{port}'

    # ── 内部 HTTP 工具 ──────────────────────────────────

    def _post(self, path, body=None):
        """发送 POST 请求，返回解析后的 JSON"""
        url = f'{self._base}{path}'
        data = json.dumps(body or {}).encode('utf-8') if body else b'{}'
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            logger.warning(f"[mem0_http] service unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"[mem0_http] request failed: {e}")
            raise

    def _get(self, path):
        """发送 GET 请求，返回解析后的 JSON"""
        url = f'{self._base}{path}'
        req = urllib.request.Request(url, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            logger.warning(f"[mem0_http] service unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"[mem0_http] request failed: {e}")
            raise

    # ── mem0 兼容接口 ──────────────────────────────────

    def add(self, text, **kwargs):
        """存储记忆（对应 mem0.add）"""
        body = {'text': text}
        body.update(kwargs)
        return self._post('/memory/add', body)

    def search(self, query, **kwargs):
        """搜索记忆（对应 mem0.search）"""
        body = {'query': query}
        body.update(kwargs)
        return self._post('/memory/search', body)

    def get_all(self, **kwargs):
        """列出记忆（对应 mem0.get_all）"""
        return self._post('/memory/list', kwargs)

    def get(self, memory_id):
        """获取单条记忆（对应 mem0.get）"""
        return self._post('/memory/get', {'id': memory_id})

    def delete(self, memory_id):
        """删除记忆（对应 mem0.delete）"""
        return self._post('/memory/delete', {'id': memory_id})

    def update(self, memory_id, new_text):
        """更新记忆（对应 mem0.update）"""
        return self._post('/memory/update', {'id': memory_id, 'text': new_text})

    def health(self):
        """健康检查"""
        return self._get('/health')

    def __repr__(self):
        return f'<Mem0HttpClient {self._base}>'
