"""Playwright script to test AI Agent Platform frontend pages."""
from playwright.sync_api import sync_playwright
import sys

BASE = "http://localhost:3000"
RESULTS = []

def t(name, ok, detail=""):
    icon = "OK" if ok else "FAIL"
    msg = f"  [{icon}] {name}"
    if detail and not ok:
        msg += f" - {detail}"
    print(msg)
    RESULTS.append((name, ok, detail))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # ========== 1. Login Page ==========
    print("\n=== Login Page ===")
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
        page.screenshot(path="/tmp/frontend_login.png")
        t("Login page loads", "登录" in page.content())
        t("Login form visible", page.locator("input").count() >= 2)
        t("Role selector visible", page.locator("select, .ant-select").count() >= 1 or "角色" in page.content())

        # Fill login form
        page.fill('input[id="user_id"]', "admin")
        role_selector = page.locator(".ant-select-selector").first
        role_selector.click()
        page.locator(".ant-select-item-option").filter(has_text="admin").first.click()
        page.locator("button[type='submit']").click()
        page.wait_for_load_state("networkidle", timeout=10000)
        page.screenshot(path="/tmp/frontend_after_login.png")
        t("Login redirects", page.url != f"{BASE}/login", f"URL: {page.url}")
    except Exception as e:
        t("Login page", False, str(e))

    # ========== 2. Chat Page ==========
    print("\n=== Chat Page ===")
    try:
        page.goto(f"{BASE}/chat", wait_until="networkidle", timeout=15000)
        page.screenshot(path="/tmp/frontend_chat.png")
        content = page.content()
        t("Chat page loads", "对话" in content or "chat" in content.lower() or "会话" in content)
        t("Layout header visible", page.locator("header").count() >= 1 or "AI Agent" in content)
        t("Input area visible", page.locator("textarea, input[type='text']").count() >= 1 or "发送" in content or "输入" in content)
    except Exception as e:
        t("Chat page", False, str(e))

    # ========== 3. Agent Market ==========
    print("\n=== Agent Market ===")
    try:
        page.goto(f"{BASE}/agents", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/frontend_agents.png")
        content = page.content()
        agent_count = content.count("display_name") or content.count("专家") or content.count("巡检")
        t("Agent Market loads", "智能体" in content or "agent" in content.lower() or agent_count > 0)
        t("Agent cards visible", page.locator(".ant-card").count() >= 1 or agent_count >= 3, f"cards: {page.locator('.ant-card').count()}")
    except Exception as e:
        t("Agent Market", False, str(e))

    # ========== 4. Admin Panel ==========
    print("\n=== Admin Panel ===")
    try:
        page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/frontend_admin.png")
        content = page.content()
        t("Admin panel loads", "管理" in content or "admin" in content.lower() or "审批" in content)
        t("Tabs visible", page.locator(".ant-tabs-tab").count() >= 2, f"tabs: {page.locator('.ant-tabs-tab').count()}")
    except Exception as e:
        t("Admin panel", False, str(e))

    # ========== 5. Vite Proxy Integration ==========
    print("\n=== Vite Proxy Integration ===")
    try:
        page.goto(f"{BASE}/api/agents", wait_until="networkidle", timeout=10000)
        content = page.content()
        t("/api/agents proxy", "equipment_monitor" in content or "agents" in content, content[:100])
    except Exception as e:
        t("/api/agents proxy", False, str(e))
    try:
        page.goto(f"{BASE}/health", wait_until="networkidle", timeout=10000)
        content = page.content()
        t("/health proxy", "ok" in content, content[:100])
    except Exception as e:
        t("/health proxy", False, str(e))

    browser.close()

# Summary
print("\n" + "=" * 50)
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print(f"Frontend Test Summary: {passed}/{total} passed")
for name, ok, detail in RESULTS:
    status = "PASS" if ok else "FAIL"
    d = f" ({detail})" if detail else ""
    print(f"  [{status}] {name}{d}")

sys.exit(0 if passed == total else 1)
