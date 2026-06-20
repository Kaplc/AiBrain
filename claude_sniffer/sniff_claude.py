"""
Claude Code 请求拦截记录工具 (Python版)

拦截 Claude Code 的请求，记录完整请求体到日志文件，返回模拟响应。

使用方式：
  1. python claude_sniffer/sniff_claude.py
  2. 在 Claude Code 的 settings.json 中设置：
     "ANTHROPIC_BASE_URL": "http://127.0.0.1:9999"
  3. 重启 Claude Code
"""

import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests
import subprocess
import sys

PROXY_PORT = 9999
FORWARD_URL = "https://opencode.ai/zen/go/v1/messages"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

if os.path.isfile(LOG_DIR):
    os.remove(LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)

LOG_TXT_FILE = os.path.join(LOG_DIR, "sniff.log")
LOG_JSONL_FILE = os.path.join(LOG_DIR, "sniff_log.jsonl")
RESPONSE_LOG_FILE = os.path.join(LOG_DIR, "response.log")

def kill_existing_instance():
    """检查并杀掉占用端口的旧实例"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            encoding='gbk'
        )
        for line in result.stdout.split('\n'):
            if f':{PROXY_PORT}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"发现旧实例 PID={pid}，正在清理...")
                        subprocess.run(['taskkill', '/F', '/PID', pid], 
                                      capture_output=True)
                        import time
                        time.sleep(1)
                        print("旧实例已清理")
    except Exception as e:
        print(f"检查旧实例时出错: {e}")

logger = logging.getLogger('claude_sniffer')
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(message)s'))

logger.addHandler(console_handler)


class ClaudeSniffer(BaseHTTPRequestHandler):
    req_count = 0

    def log_request(self, code='-', size='-'):
        pass

    def _handle(self):
        ClaudeSniffer.req_count += 1
        req_id = ClaudeSniffer.req_count
        timestamp = datetime.now().isoformat()

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ''

        parsed_body = None
        try:
            parsed_body = json.loads(body) if body else None
        except json.JSONDecodeError:
            pass

        lines = []
        lines.append(f"\n{'═' * 60}")
        lines.append(f"[#{req_id}] {timestamp}")
        lines.append(f"{self.command} {self.path}")
        lines.append('─' * 60)

        headers_dict = dict(self.headers.items())
        safe_headers = {}
        for k, v in headers_dict.items():
            if k in ['authorization', 'x-api-key', 'cookie']:
                safe_headers[k] = v[:15] + '***'
            else:
                safe_headers[k] = v
        lines.append(f"Headers: {json.dumps(safe_headers, ensure_ascii=False, indent=2)}")

        if parsed_body:
            lines.append(f"\n📦 Body ({len(body)} bytes):")
            lines.append(f"  model: {parsed_body.get('model', '(无)')}")
            lines.append(f"  stream: {parsed_body.get('stream')}")
            lines.append(f"  max_tokens: {parsed_body.get('max_tokens')}")

            if 'system' in parsed_body:
                system = parsed_body['system']
                sys_str = system if isinstance(system, str) else json.dumps(system, ensure_ascii=False)
                lines.append(f"  system: {sys_str[:300]}{'...' if len(sys_str) > 300 else ''}")

            if 'messages' in parsed_body:
                messages = parsed_body['messages']
                lines.append(f"  messages: {len(messages)} 条")
                for i, msg in enumerate(messages):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    lines.append(f"    [{i}] {role}: {content_str[:200]}{'...' if len(content_str) > 200 else ''}")

            if 'tools' in parsed_body:
                tools = parsed_body['tools']
                lines.append(f"  tools: {len(tools)} 个")
                for i, tool in enumerate(tools):
                    lines.append(f"    [{i}] {tool.get('name', '?')}: {tool.get('description', '')[:80]}")

            lines.append(f"\n📋 完整请求体:")
            lines.append(json.dumps(parsed_body, ensure_ascii=False, indent=2))
        else:
            lines.append(f"Body (raw): {body[:3000]}")

        lines.append(f"{'═' * 60}")

        output = '\n'.join(lines)
        logger.info(output)

        with open(LOG_TXT_FILE, 'w', encoding='utf-8') as f:
            f.write(output + '\n')

        log_entry = {
            'id': req_id,
            'timestamp': timestamp,
            'method': self.command,
            'url': self.path,
            'headers': {k: v for k, v in headers_dict.items() if k not in ['authorization', 'x-api-key', 'cookie']},
            'body': parsed_body if parsed_body else body
        }
        with open(LOG_JSONL_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        try:
            forward_headers = {k: v for k, v in headers_dict.items() 
                             if k.lower() not in ['host', 'content-length', 'transfer-encoding', 'authorization']}
            
            auth = headers_dict.get('Authorization', '')
            if auth.startswith('Bearer '):
                forward_headers['x-api-key'] = auth[7:]
            
            forward_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            forward_headers['Accept'] = 'application/json'
            forward_headers['Accept-Language'] = 'en-US,en;q=0.9'
            forward_headers['Origin'] = 'https://opencode.ai'
            forward_headers['Referer'] = 'https://opencode.ai/'
            
            response = requests.post(
                FORWARD_URL,
                headers=forward_headers,
                data=body.encode('utf-8') if body else None,
                timeout=120,
                verify=False
            )
            
            response_body = response.content
            response_text = response.text
            
            logger.info(f"[#{req_id}] 📥 响应: {response.status_code} ({len(response_body)} bytes)")
            
            res_lines = []
            res_lines.append(f"\n{'═' * 60}")
            res_lines.append(f"[#{req_id}] {datetime.now().isoformat()}")
            res_lines.append(f"响应状态: {response.status_code}")
            res_lines.append(f"响应大小: {len(response_body)} bytes")
            res_lines.append('─' * 60)
            
            try:
                res_json = response.json()
                res_lines.append(json.dumps(res_json, ensure_ascii=False, indent=2))
                if 'content' in res_json:
                    content_str = json.dumps(res_json['content'], ensure_ascii=False)
                    logger.info(f"[#{req_id}] 回复: {content_str[:500]}")
                if 'usage' in res_json:
                    usage = res_json['usage']
                    logger.info(f"[#{req_id}] tokens: in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")
            except:
                res_lines.append(response_text)
            
            res_lines.append(f"{'═' * 60}")
            
            with open(RESPONSE_LOG_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(res_lines) + '\n')
            
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in ['transfer-encoding', 'connection']:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body)
                    
        except Exception as e:
            error_msg = f"[#{req_id}] ❌ 转发失败: {e}"
            logger.error(error_msg)
            
            with open(RESPONSE_LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(f"\n{'═' * 60}\n")
                f.write(f"[#{req_id}] {datetime.now().isoformat()}\n")
                f.write(f"转发失败: {e}\n")
                f.write(f"{'═' * 60}\n")
            
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_body = json.dumps({'error': str(e)}).encode('utf-8')
            self.wfile.write(error_body)

    def do_POST(self):
        self._handle()

    def do_GET(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()


def main():
    kill_existing_instance()
    server = HTTPServer(('127.0.0.1', PROXY_PORT), ClaudeSniffer)

    logger.info(f"""
╔════════════════════════════════════════════════════════════════╗
║              🔍 Claude Code 请求拦截记录工具                    ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  监听端口: {PROXY_PORT}                                                ║
║  日志文件: {LOG_TXT_FILE}                              ║
║  JSON日志: {LOG_JSONL_FILE}                            ║
║                                                                ║
║  使用步骤:                                                     ║
║    1. 打开 Claude Code settings.json                           ║
║    2. 添加: "ANTHROPIC_BASE_URL": "http://127.0.0.1:{PROXY_PORT}"    ║
║    3. 重启 Claude Code                                         ║
║                                                                ║
║  所有请求会被拦截记录到日志，不转发到真实API                     ║
║  Ctrl+C 停止                                                   ║
╚════════════════════════════════════════════════════════════════╝
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\n正在关闭...")
        server.shutdown()


if __name__ == '__main__':
    main()
