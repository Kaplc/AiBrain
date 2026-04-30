"""
Wiki 重启 Flask E2E 测试
"""
import subprocess, time, sys

# 先确认 Flask 端口
port_file = "E:/Project/AiBrain/.port_config"
with open(port_file) as f:
    port = f.read().strip().split(',')[0]

BASE = f"http://127.0.0.1:{port}"


def test_flask_restart():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 1. 加载 overview 页面
        page.goto(f"{BASE}/", timeout=15000)
        print(f"[PASS] 页面加载成功: {page.title()}")

        # 2. 确认能访问 health
        resp = page.request.get(f"{BASE}/health")
        assert resp.ok, f"health 返回 {resp.status}"
        print("[PASS] /health 正常")

        # 3. 点重启 Flask
        page.click("#btnRestartFlask", timeout=5000)
        print("[PASS] 点击了重启Flask")

        # 4. 等待 5 秒让 PM 重启
        time.sleep(5)

        # 5. 确认 Flask 已恢复
        for attempt in range(10):
            try:
                resp = page.request.get(f"{BASE}/health", timeout=5000)
                if resp.ok:
                    print(f"[PASS] Flask 重启成功 (尝试 {attempt + 1}/10)")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise AssertionError("Flask 重启超时")

        browser.close()
        print("\n[所有测试通过]")


if __name__ == "__main__":
    try:
        test_flask_restart()
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)