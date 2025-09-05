# wake.py - abre o app e clica no botão "wake up" se estiver dormindo
import os, time
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL")
if not APP_URL:
    raise SystemExit("APP_URL não definido")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(APP_URL, wait_until="domcontentloaded", timeout=120_000)

    # Se houver página de hibernação, o botão costuma ter esse texto:
    # "Yes, get this app back up!"
    try:
        btn = page.get_by_role("button", name="Yes, get this app back up!")
        if btn.is_visible():
            btn.click()
            # aguarda o app bootar
            page.wait_for_selector('div[data-testid="stAppViewContainer"]', timeout=120_000)
    except Exception:
        # Se não achou, provavelmente já estava acordado
        pass

    # Toca mais um elemento comum pra registrar atividade
    page.wait_for_load_state("networkidle", timeout=60_000)
    time.sleep(2)
    browser.close()
