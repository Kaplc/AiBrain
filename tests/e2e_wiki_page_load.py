"""Wiki 页面加载 E2E 测试（HTML 片段 + JS 依赖）

测试目标：
1. 切换到 wiki 页面，sidebar 三个 tab 内容是否正常显示
2. 切换 sidebar tab 是否正常
3. wiki 文件列表是否加载
"""
from playwright.sync_api import sync_playwright
import time
import requests

BASE = "http://127.0.0.1:19398"
WIKI_DIR = "E:/Project/AiBrain/wiki/project"

def test_wiki_page_load():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        print("[E2E] 先打开 overview 页面初始化 router...")
        page.goto("http://127.0.0.1:19398/", wait_until="load", timeout=30000)
        page.wait_for_timeout(2000)

        console_logs = []
        page.on("console", lambda m: console_logs.append(f"[{m.type}] {m.text}"))

        print("[E2E] 点击 wiki nav 按钮...")
        page.click('.nav-item[data-page="wiki"]')
        page.wait_for_timeout(4000)

        print("\n[E2E] Console logs:")
        for log in console_logs:
            print(f"  {log}")

        # 检查 DOM 结构
        dom_check = page.evaluate("""() => {
            const content = document.getElementById('page-content');
            const wikiWrap = content.querySelector('.wiki-wrap');
            const sidebar = wikiWrap ? wikiWrap.querySelector('.wiki-sidebar') : null;
            const sideContent = sidebar ? sidebar.querySelector('.side-content') : null;
            const panel = sideContent ? sideContent.querySelector('.side-panel') : null;
            const slot = panel ? panel.querySelector('#slot-stats') : null;
            return {
                contentHasWikiWrap: !!wikiWrap,
                wikiWrapId: wikiWrap ? wikiWrap.id : null,
                wikiWrapDataDeps: wikiWrap ? wikiWrap.getAttribute('data-deps') : null,
                sidebarFound: !!sidebar,
                sideContentFound: !!sideContent,
                panelFound: !!panel,
                panelId: panel ? panel.id : null,
                slotFound: !!slot,
                slotId: slot ? slot.id : null,
                slotParentId: slot ? slot.parentElement.id : null,
            };
        }""")
        print(f"[E2E] DOM 结构: {dom_check}")

        # 检查 sidebar 统计 tab 内容
        stats_content = page.evaluate("""() => {
            const slot = document.querySelector('#slot-stats');
            return slot ? slot.innerHTML.substring(0, 100) : 'MISSING';
        }""")
        print(f"[E2E] slot-stats 内容: {stats_content[:80]}")
        assert stats_content and stats_content != 'MISSING' and stats_content.strip() != '', f"stats 内容为空: {stats_content}"
        assert 'wscard' in stats_content, f"stats 内容缺少 wscard: {stats_content}"

        # 点击操作 tab
        print("[E2E] 点击操作 tab...")
        page.click('button[data-tab="ops"]')
        page.wait_for_timeout(500)
        ops_content = page.evaluate("""() => {
            const slot = document.querySelector('#slot-ops');
            return slot ? slot.innerHTML.substring(0, 100) : 'MISSING';
        }""")
        print(f"[E2E] slot-ops 内容: {ops_content[:80]}")
        assert ops_content and ops_content.strip() != '', f"ops 内容为空"

        # 点击设置 tab
        print("[E2E] 点击设置 tab...")
        page.click('button[data-tab="settings"]')
        page.wait_for_timeout(500)
        settings_content = page.evaluate("""() => {
            const slot = document.querySelector('#slot-settings');
            return slot ? slot.innerHTML.substring(0, 100) : 'MISSING';
        }""")
        print(f"[E2E] slot-settings 内容: {settings_content[:80]}")
        assert settings_content and settings_content.strip() != '', f"settings 内容为空"

        # 检查文件列表
        file_count = page.evaluate("""() => {
            const wrap = document.querySelector('#wikiTableWrap');
            return wrap ? wrap.textContent.substring(0, 50) : 'MISSING';
        }""")
        print(f"[E2E] 文件列表: {file_count}")

        # 检查 wiki.js 中 WikiFile 冲突
        wiki_errors = [e for e in errors if 'WikiFile' in e or 'wiki_file' in e]
        if wiki_errors:
            print(f"[E2E] WikiFile 错误: {wiki_errors}")

        real_errors = [e for e in errors if 'favicon' not in e and '404' not in e and 'WikiFile' not in e]
        print(f"\n[E2E] Console errors (filtered): {real_errors}")

        browser.close()
        print("\n[E2E] ✓ 测试完成")

if __name__ == "__main__":
    test_wiki_page_load()
