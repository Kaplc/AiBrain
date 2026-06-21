import requests
import json
import re

# 读取原始请求日志
with open('claude_sniffer/logs/sniff copy.log', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取 headers
headers_match = re.search(r'Headers: (\{.*?\})\n\n', content, re.DOTALL)
headers = json.loads(headers_match.group(1)) if headers_match else {}

# 提取完整请求体
body_match = re.search(r'📋 完整请求体:\n(\{.*?\})\n═', content, re.DOTALL)
body = body_match.group(1) if body_match else '{}'

# 修改 Host 到目标地址
headers['Host'] = 'opencode.ai'

# 只替换 User-Agent，其他保持不变
headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# 转换 Authorization 到 x-api-key
if 'Authorization' in headers:
    auth = headers['Authorization']
    if auth.startswith('Bearer '):
        headers['x-api-key'] = auth[7:]
    del headers['Authorization']

# 直接转发原始请求
print("转发原始请求到 opencode.ai...")
print(f"Model: {json.loads(body).get('model', 'unknown')}")
print(f"Body size: {len(body)} bytes")

response = requests.post(
    'https://opencode.ai/zen/go/v1/messages',
    headers=headers,
    data=body.encode('utf-8'),
    timeout=120,
    verify=False
)

print(f"\n响应状态: {response.status_code}")
print(f"响应大小: {len(response.content)} bytes")
print(f"\n响应内容:\n{response.text[:2000]}")
