import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

download_dir = Path("data/scraped/basel_pdfs")
download_dir.mkdir(parents=True, exist_ok=True)

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()), options=options
)
driver.get("https://www.bis.org/bcbs/publications.htm")

print("Waiting for page to load...")
time.sleep(10)  # Give time for React to render

# Scroll to trigger lazy loading
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(5)

pdf_links = driver.find_elements(By.CSS_SELECTOR, 'a[href$=".pdf"]')

print(f"\nFound {len(pdf_links)} PDF links")

for i, link in enumerate(pdf_links[:10], 1):  # Test with first 10 links
    pdf_url = link.get_attribute("href")
    title = link.text.strip() or f"Basel_Document_{i}"

    print(f"{i}. Downloading: {title}")

    try:
        r = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            filepath = download_dir / pdf_url.split("/")[-1]
            filepath.write_bytes(r.content)
            print(f"   ✅ Saved: {filepath.name}")
        else:
            print(f"   ❌ Failed (status {r.status_code})")
    except Exception as e:
        print(f"   ❌ Error: {e}")

driver.quit()
print("\nDone.")
