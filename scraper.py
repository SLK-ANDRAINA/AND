from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time, random, sqlite3, os, csv
from datetime import datetime

# ================= UTIL =================
def human_pause(a=0.5, b=1.5):
    time.sleep(random.uniform(a, b))

# ================= BASE DE DONNÉES =================
conn = sqlite3.connect("ebay.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT UNIQUE,
    seller TEXT,
    title TEXT,
    oem_reference TEXT,
    price TEXT,
    currency TEXT,
    url TEXT,
    listing_start_date TEXT,
    status TEXT,
    end_date TEXT
)
""")
conn.commit()

def save_or_update_item(data):
    cursor.execute("SELECT status FROM listings WHERE item_id = ?", (data["item_id"],))
    row = cursor.fetchone()

    if row:
        if row[0] == "ENDED":
            return
        cursor.execute("""
            UPDATE listings SET
                title = ?,
                oem_reference = ?,
                price = ?,
                currency = ?,
                url = ?
            WHERE item_id = ?
        """, (
            data["title"],
            data["oem_reference"],
            data["price"],
            data["currency"],
            data["url"],
            data["item_id"]
        ))
        print(f"🔄 UPDATE : {data['item_id']}")
    else:
        cursor.execute("""
            INSERT INTO listings (
                item_id, seller, title, oem_reference,
                price, currency, url, listing_start_date, status, end_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["item_id"],
            data["seller"],
            data["title"],
            data["oem_reference"],
            data["price"],
            data["currency"],
            data["url"],
            datetime.now().isoformat(),
            "ACTIVE",
            None
        ))
        print(f"✅ INSERT : {data['item_id']}")

def mark_ended(scraped_ids, seller):
    cursor.execute("SELECT item_id FROM listings WHERE seller=? AND status='ACTIVE'", (seller,))
    db_ids = {row[0] for row in cursor.fetchall()}

    ended = db_ids - scraped_ids
    for item_id in ended:
        cursor.execute("""
            UPDATE listings
            SET status='ENDED', end_date=?
            WHERE item_id=?
        """, (datetime.now().isoformat(), item_id))
        print(f"⛔ ENDED : {item_id}")
    conn.commit()

def export_db_to_csv(db_path="ebay.db", csv_path="ebay_export.csv"):
    cursor.execute("SELECT * FROM listings")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"✅ Base exportée : {csv_path}")

# ================= SELENIUM CONFIG =================
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
wait = WebDriverWait(driver, 20)

# ================= INPUT =================
url = "https://www.ebay.com/str/tiresnation"
driver.get(url)
human_pause(2, 4)

# ================= GET SELLER =================
about_tab = wait.until(EC.presence_of_element_located(
    (By.XPATH, "//div[@role='tab' and contains(., 'About')]")
))
driver.execute_script("arguments[0].click();", about_tab)
human_pause(1, 2)

seller_section = wait.until(EC.presence_of_element_located(
    (By.CSS_SELECTOR, "section.str-about-description__seller-info")
))

seller_id = None
for line in seller_section.text.split("\n"):
    if "Seller:" in line:
        seller_id = line.replace("Seller:", "").strip()
print("✅ Seller ID :", seller_id)

driver.get(url)
human_pause(2, 4)

# ================= FILTRE USED =================
condition_button = wait.until(EC.element_to_be_clickable(
    (By.XPATH, "//span[contains(text(),'Condition')]")
))
driver.execute_script("arguments[0].click();", condition_button)
human_pause(0.5, 1.5)

for item in driver.find_elements(By.CLASS_NAME, "filter-menu-button__item"):
    if "Used" in item.text:
        driver.execute_script("arguments[0].click();", item)
        break
human_pause(2, 4)

# ================= SCRAPING =================
scraped_item_ids = set()

def process_cards():
    cards = driver.find_elements(By.CSS_SELECTOR, "div.str-item-card__header-container")
    print(f"🔎 {len(cards)} cartes trouvées")

    for card in cards:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        human_pause(0.5, 1)

        try:
            driver.execute_script("arguments[0].click();", card)
        except:
            continue

        human_pause(1, 2)
        driver.switch_to.window(driver.window_handles[-1])

        item_url = driver.current_url
        item_id = item_url.split("/itm/")[-1].split("?")[0]

        try:
            title = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "h1.x-item-title__mainTitle span")
            )).text
        except:
            title = None

        try:
            oem = driver.find_element(By.CSS_SELECTOR,
                "dl.ux-labels-values--manufacturerPartNumber dd span").text
        except:
            oem = None

        try:
            price_text = driver.find_element(By.CSS_SELECTOR, "div.x-price-primary span").text
            currency = price_text.split(" ")[0]
            price = price_text.replace(currency, "").strip()
        except:
            currency = price = None

        data = {
            "item_id": item_id,
            "title": title,
            "oem_reference": oem,
            "price": price,
            "currency": currency,
            "url": item_url,
            "seller": seller_id
        }

        scraped_item_ids.add(item_id)
        save_or_update_item(data)

        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        human_pause(0.5, 1.5)

    # Commit par lot à la fin de la page
    conn.commit()

# ================= PAGINATION =================
while True:
    process_cards()
    try:
        next_btn = driver.find_element(By.CSS_SELECTOR, "a.pagination__next")
        driver.execute_script("arguments[0].click();", next_btn)
        human_pause(2, 4)
    except:
        break

# ================= FINAL ENDED UPDATE =================
mark_ended(scraped_item_ids, seller_id)

# ================= EXPORT =================
export_db_to_csv()

driver.quit()
conn.close()

print("\n🎯 SCRAPING + SYNCHRONISATION TERMINÉE")
print("📁 Base de données : ebay.db")