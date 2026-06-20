import urllib.request
import json

url = 'http://127.0.0.1:9999/v1/messages'
data = json.dumps({
    'model': 'claude-3',
    'max_tokens': 100,
    'messages': [{'role': 'user', 'content': 'Hi'}]
}).encode()
headers = {'Content-Type': 'application/json'}

req = urllib.request.Request(url, data=data, headers=headers)
try:
    resp = urllib.request.urlopen(req)
    print("Response:", resp.read().decode())
except Exception as e:
    print("Error:", e)
