import requests
import json
import os

# 找到 JSONL 日志文件
log_dir = 'logs'
jsonl_path = os.path.join(log_dir, 'sniff_log.jsonl')

if not os.path.exists(jsonl_path):
    print("没有找到 sniff_log.jsonl 文件")
    exit(1)

print(f"读取日志文件: {jsonl_path}")

# 读取最后一个请求
last_entry = None
with open(jsonl_path, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            try:
                last_entry = json.loads(line)
            except json.JSONDecodeError:
                continue

if not last_entry:
    print("没有找到请求记录")
    exit(1)

print(f"请求 ID: {last_entry.get('id', 'unknown')}")
print(f"时间: {last_entry.get('timestamp', 'unknown')}")
print(f"方法: {last_entry.get('method', 'unknown')}")
print(f"URL: {last_entry.get('url', 'unknown')}")

# 提取 headers 和 body
headers = last_entry.get('headers', {})
body_json = last_entry.get('body', {})

print(f"Model: {body_json.get('model', 'unknown')}")
print(f"Messages: {len(body_json.get('messages', []))}")

# 替换 User-Agent
headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# 转换 Authorization 到 x-api-key
if 'Authorization' in headers:
    auth = headers['Authorization']
    if auth.startswith('Bearer '):
        headers['x-api-key'] = auth[7:]
    del headers['Authorization']

# 移除可能导致问题的 headers
for key in ['Content-Length', 'Accept-Encoding', 'Host', 'Connection']:
    if key in headers:
        del headers[key]

print(f"\nNew User-Agent: {headers.get('User-Agent')}")
print(f"Has x-api-key: {'x-api-key' in headers}")

# 转发请求到代理
body_str = json.dumps(body_json, ensure_ascii=False)
response = requests.post(
    'http://127.0.0.1:9999/v1/messages',
    headers=headers,
    data=body_str.encode('utf-8'),
    timeout=120,
    verify=False
)

print(f"\n响应状态: {response.status_code}")
print(f"响应大小: {len(response.content)} bytes")
print(f"\n响应内容:\n{response.text[:2000]}")
