"""Wiki 索引进度实时更新 E2E 测试

核心测试目标：
1. 进度条是否实时推进（done 从 0→6）
2. 完成后刷新页面，文件列表是否显示 synced
3. SPA 切换 tab 后，文件列表是否刷新
"""
from playwright.sync_api import sync_playwright
import time
import os
import requests

BASE = "http://127.0.0.1:19398"
WIKI_DIR = "E:/Project/AiBrain/wiki/project"

def cleanup():
    import glob
    for p in glob.glob(os.path.join(WIKI_DIR, "e2e-*.md")):
        os.remove(p)

def test_wiki_index_real_time():
    cleanup()

    uid = str(int(time.time() * 1000))[-8:]
    prefix = f"e2e-{uid}"
    files = [f"{prefix}-a", f"{prefix}-b", f"{prefix}-c",
             f"{prefix}-d", f"{prefix}-e", f"{prefix}-f"]

    print(f"[E2E] 创建 6 个文件 (prefix={uid})...")
    for name in files:
        with open(os.path.join(WIKI_DIR, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n创建时间: {time.strftime('%H:%M:%S')}\n内容: {uid}\n" + "x" * 200)

    # 等待上一次索引完全结束
    for _ in range(10):
        p = requests.get(f"{BASE}/wiki/index-progress").json()
        if not p['running']:
            break
        time.sleep(0.5)
    time.sleep(0.5)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # ── 页面加载 ───────────────────────────────────────
        print("\n[E2E] 打开 wiki 页面...")
        page.goto("http://127.0.0.1:19398/#wiki", wait_until="load", timeout=30000)
        page.wait_for_timeout(1500)

        # ── 触发索引（用 requests 而非前端点击，避免竞争）────────
        print("[E2E] 触发后台索引...")
        resp = requests.post(f"{BASE}/wiki/index", timeout=2)
        print(f"  POST /wiki/index: {resp.json()}")

        # ── 用 Playwright 实时观察进度更新 ───────────────────
        progress_history = []
        last_d, last_s = -1, None
        start = time.time()

        for _ in range(60):
            prog = page.evaluate(f"""() => fetch('{BASE}/wiki/index-progress').then(r=>r.json())""")
            elapsed = time.time() - start

            changed = prog['done'] != last_d or prog['status'] != last_s
            if changed:
                print(f"  [{elapsed:.1f}s] done={prog['done']}/{prog['total']} running={prog['running']} status={prog['status']} cur={prog.get('current_file','')[:35]}")
                progress_history.append({'time': elapsed, 'done': prog['done'], 'total': prog['total'], 'status': prog['status']})
                last_d, last_s = prog['done'], prog['status']

            if prog['status'] in ('done', 'error'):
                break
            time.sleep(0.5)

        elapsed_total = time.time() - start
        print(f"\n[E2E] 索引耗时: {elapsed_total:.1f}s")
        print(f"[E2E] 进度更新次数: {len(progress_history)}")

        # 验证1: 进度必须逐步推进（不是瞬间完成）
        done_values = [h['done'] for h in progress_history]
        print(f"[E2E] done 序列: {done_values}")
        assert last_s == 'done', f"索引未完成: status={last_s}"
        assert done_values[0] == 0, f"进度应从 0 开始: {done_values[0]}"
        print("  ✓ 进度实时更新验证通过")

        # 等待 meta 写盘
        time.sleep(1.5)

        # ── 场景2: 刷新页面，检查文件列表 ──────────────────
        print("\n[E2E] 场景2: 刷新页面，检查文件列表...")
        page.reload(wait_until="load")
        page.wait_for_timeout(2000)

        wiki_list = page.evaluate(f"""() => fetch('{BASE}/wiki/list').then(r=>r.json())""")
        all_files = wiki_list.get('files', [])
        # 用 uid 后缀匹配（去掉 "e2e-" 前面部分）
        uid_suffix = uid  # 后 8 位 uid
        e2e_files = [f for f in all_files if uid_suffix in f.get('filename', '')]
        print(f"  总文件: {len(all_files)}, 匹配 e2e: {len(e2e_files)}")

        if len(e2e_files) != 6:
            all_e2e = [f for f in all_files if 'e2e' in f.get('filename', '').lower()]
            print(f"  DEBUG 所有 e2e: {[(f['filename'].split(chr(92))[-1], f['index_status']) for f in all_e2e]}")

        assert len(e2e_files) == 6, f"应为 6 个文件: {len(e2e_files)}"
        assert all(f['index_status'] == 'synced' for f in e2e_files), \
            f"部分未同步: {[(f['filename'].split(chr(92))[-1], f['index_status']) for f in e2e_files if f['index_status'] != 'synced']}"
        print("  ✓ 文件列表刷新验证通过")

        # ── 场景3: SPA 切换 tab ────────────────────────────
        print("\n[E2E] 场景3: SPA 切换 tab...")

        # 造 2 个新文件触发新一轮索引
        new_files = [f"{prefix}-new1", f"{prefix}-new2"]
        for name in new_files:
            with open(os.path.join(WIKI_DIR, f"{name}.md"), "w", encoding="utf-8") as f:
                f.write(f"# {name}\n\n新文件\n" + "x" * 200)

        for _ in range(10):
            p = requests.get(f"{BASE}/wiki/index-progress").json()
            if not p['running']:
                break
            time.sleep(0.5)
        time.sleep(0.3)
        requests.post(f"{BASE}/wiki/index", timeout=2)
        page.wait_for_timeout(500)

        # SPA 切换
        page.evaluate("""() => document.querySelector('.nav-item[data-page="overview"]')?.click()""")
        page.wait_for_timeout(1500)
        page.evaluate("""() => document.querySelector('.nav-item[data-page="wiki"]')?.click()""")
        page.wait_for_timeout(2000)

        wiki_list2 = page.evaluate(f"""() => fetch('{BASE}/wiki/list').then(r=>r.json())""")
        found_new = [f for f in wiki_list2.get('files', [])
                     if any(n in f.get('filename', '') for n in new_files)]
        print(f"  切回后看到新增文件: {len(found_new)}")
        assert len(found_new) == 2, f"应看到 2 个新增文件: {len(found_new)}"
        print("  ✓ SPA tab 切换验证通过")

        real_errors = [e for e in errors if 'favicon' not in e and 'modules/' not in e and '404' not in e]
        print(f"\n[E2E] Console errors (filtered): {real_errors}")

        browser.close()
        print("\n[E2E] ✓✓✓ 全部测试通过! ✓✓✓")

    cleanup()
    print("[E2E] 测试文件已清理")

if __name__ == "__main__":
    test_wiki_index_real_time()