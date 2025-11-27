# scraper_multi_fixed.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time, random, sqlite3, csv, os, urllib.parse
from datetime import datetime
from selenium.common.exceptions import TimeoutException


# ------------------ CONFIG / UTIL ------------------
def human_pause(a=0.3, b=1.0):
    time.sleep(random.uniform(a, b))

DB_PATH = "ebay.db"
EXPORT_CSV = "ebay_export.csv"

# ------------------ DATABASE SETUP ------------------
conn = sqlite3.connect(DB_PATH, timeout=30)
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
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sellers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id TEXT UNIQUE,
    shop_url TEXT,
    last_scan TEXT
);
""")
conn.commit()

def add_seller(seller_id, shop_url):
    cursor.execute("INSERT OR IGNORE INTO sellers (seller_id, shop_url, last_scan) VALUES (?, ?, ?)",
                   (seller_id, shop_url, None))
    conn.commit()
    print(f"✅ Seller ajouté (ou déjà existant): {seller_id}")

def get_all_sellers():
    cursor.execute("SELECT seller_id, shop_url FROM sellers")
    return cursor.fetchall()

# ------------------ DB OPERATIONS FOR LISTINGS ------------------
def save_or_update_item(data):
    cursor.execute("SELECT status FROM listings WHERE item_id = ?", (data["item_id"],))
    row = cursor.fetchone()

    if row:
        if row[0] == "ENDED":
            return
        cursor.execute("""
            UPDATE listings SET
                seller = ?, title = ?, oem_reference = ?, price = ?, currency = ?, url = ?
            WHERE item_id = ?
        """, (data["seller"], data["title"], data["oem_reference"], data["price"], data["currency"], data["url"], data["item_id"]))
        print(f"🔄 UPDATE : {data['item_id']}")
    else:
        cursor.execute("""
            INSERT INTO listings (item_id, seller, title, oem_reference, price, currency, url, listing_start_date, status, end_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data["item_id"], data["seller"], data["title"], data["oem_reference"], data["price"], data["currency"], data["url"], datetime.now().isoformat(), "ACTIVE", None))
        print(f"✅ INSERT : {data['item_id']}")
    conn.commit()

def mark_ended(scraped_ids, seller):
    cursor.execute("SELECT item_id FROM listings WHERE seller=? AND status='ACTIVE'", (seller,))
    db_ids = {row[0] for row in cursor.fetchall()}
    ended = db_ids - scraped_ids
    for item_id in ended:
        cursor.execute("UPDATE listings SET status='ENDED', end_date=? WHERE item_id=?", (datetime.now().isoformat(), item_id))
        print(f"⛔ ENDED : {item_id}")
    conn.commit()

def export_db_to_csv(csv_path=EXPORT_CSV):
    cursor.execute("SELECT * FROM listings")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"✅ Base exportée : {csv_path}")

# ------------------ SELENIUM SETUP ------------------
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
wait = WebDriverWait(driver, 20)

# ------------------ HELPERS ------------------
def safe_click(element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        human_pause(0.2, 0.6)
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            print("⚠️ safe_click failed:", e)
            return False

def extract_seller_id_from_page():
    # try seller section
    try:
        seller_section = driver.find_element(By.CSS_SELECTOR, "section.str-about-description__seller-info")
        for line in seller_section.text.split("\n"):
            if "Seller:" in line:
                return line.replace("Seller:", "").strip()
    except Exception:
        pass
    # fallback: parse current url
    try:
        u = driver.current_url
        if "/str/" in u:
            return u.split("/str/")[-1].split("?")[0].strip("/")
        parsed = urllib.parse.urlparse(u)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        if "_ssn" in params:
            return params["_ssn"]
    except Exception:
        pass
    return None

# ------------------ SCRAPE LOGIC FOR ONE SELLER ------------------
def scrape_seller(shop_url, seller_id_param=None):
    print(f"\n--- Scraping seller: {seller_id_param or shop_url} ---")
    driver.get(shop_url)
    human_pause(1.0, 2.0)

    seller_id = seller_id_param or None
    # try About tab if present
    try:
        about_tab = driver.find_element(By.XPATH, "//div[@role='tab' and contains(., 'About')]")
        safe_click(about_tab)
        human_pause(0.4, 0.9)
        extracted = extract_seller_id_from_page()
        if extracted:
            seller_id = extracted
    except Exception:
        # fallback to url parsing
        if not seller_id:
            if "/str/" in shop_url:
                seller_id = shop_url.split("/str/")[-1].split("?")[0].strip("/")
            else:
                parsed = urllib.parse.urlparse(shop_url)
                params = dict(urllib.parse.parse_qsl(parsed.query))
                seller_id = params.get("_ssn") or shop_url

    if not seller_id:
        print("⚠️ Impossible de détecter seller_id, on utilise l'URL comme identifiant.")
        seller_id = shop_url

    print("Seller ID:", seller_id)

    # ensure shop main page loaded
    driver.get(shop_url)
    human_pause(0.6, 1.2)

    # apply Condition filter -> Used
    used_clicked = False
    try:
        condition_button = driver.find_element(By.XPATH, "//span[contains(text(),'Condition')]")
        if safe_click(condition_button):
            human_pause(0.3, 0.7)
            for item in driver.find_elements(By.CLASS_NAME, "filter-menu-button__item"):
                if "Used" in item.text:
                    if safe_click(item):
                        used_clicked = True
                        break
    except Exception:
        pass

    if not used_clicked:
        print("❌ Pas d'article d'occasion détecté (ou filtre non trouvé). On arrête ce vendeur.")
        return set()

    human_pause(0.6, 1.4)

    scraped_ids = set()
    page = 1
    while True:
        human_pause(0.6, 1.0)
        cards_xpath = (
            "//div[contains(@class,'str-marginals') and contains(@class,'__header')]"  # header
            "/following-sibling::*"                                                   # tous les siblings suivants
            "//div[contains(@class,'str-item-card__header-container')]"              # cards dans ces siblings
        )
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, cards_xpath)))
        except TimeoutException:
            # Pas de cards trouvées rapidement — on essaie quand même une recherche globale en fallback
            pass
        cards = driver.find_elements(By.XPATH, cards_xpath)
        if not cards:
            cards = driver.find_elements(By.CSS_SELECTOR, "div.str-item-card__header-container")
        print(f"Page {page} - {len(cards)} cartes trouvées")
        for card in cards:
            if not safe_click(card):
                print("⚠️ impossible de cliquer sur une card => on l'ignore")
                continue

            human_pause(0.8, 1.4)
            # switch to new window if opened
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])

            human_pause(0.5, 1.0)
            item_url = driver.current_url
            item_id = None
            try:
                if "/itm/" in item_url:
                    item_id = item_url.split("/itm/")[-1].split("?")[0]
                else:
                    try:
                        meta = driver.find_element(By.CSS_SELECTOR, "meta[property='og:url']")
                        murl = meta.get_attribute("content")
                        if "/itm/" in murl:
                            item_id = murl.split("/itm/")[-1].split("?")[0]
                    except Exception:
                        pass
            except Exception:
                item_id = None

            try:
                title_elem = driver.find_element(By.CSS_SELECTOR, "h1.x-item-title__mainTitle span")
                title = title_elem.text
            except Exception:
                title = None

            # OEM
            oem = None
            try:
                oem = driver.find_element(By.CSS_SELECTOR, "dl.ux-labels-values--manufacturerPartNumber dd span").text
            except Exception:
                try:
                    elems = driver.find_elements(By.XPATH, "//dt[contains(., 'Manufacturer Part Number')]/following-sibling::dd[1]//span")
                    if elems:
                        oem = elems[0].text
                except Exception:
                    oem = None

            try:
                price_text = driver.find_element(By.CSS_SELECTOR, "div.x-price-primary span").text
                currency = price_text.split(" ")[0] if " " in price_text else None
                price = price_text.replace(currency, "").strip() if currency else price_text
            except Exception:
                price = currency = None

            if not item_id:
                item_id = f"unknown-{abs(hash(item_url or title))}-{int(time.time())}"

            data = {
                "item_id": item_id,
                "title": title,
                "oem_reference": oem,
                "price": price,
                "currency": currency,
                "url": item_url,
                "seller": seller_id
            }

            save_or_update_item(data)
            scraped_ids.add(item_id)

            # close/support navigation back
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    try:
                        driver.back()
                    except Exception:
                        pass
            except Exception:
                handles = driver.window_handles
                if handles:
                    driver.switch_to.window(handles[0])

            human_pause(0.3, 0.8)

        conn.commit()

        # NEXT PAGE
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "a.pagination__next")
            if not next_btn.is_displayed():
                break
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            human_pause(0.3, 0.7)
            if not safe_click(next_btn):
                # fallback click
                try:
                    next_btn.click()
                except Exception:
                    break
            page += 1
            human_pause(0.8, 1.6)
        except Exception:
            break

    # update seller last_scan and mark ended
    cursor.execute("UPDATE sellers SET last_scan=? WHERE seller_id=?", (datetime.now().isoformat(), seller_id))
    conn.commit()
    mark_ended(scraped_ids, seller_id)
    return scraped_ids

# ------------------ MAIN FLOW ------------------
def main():
    print("=== eBay Multi-seller Scraper ===")
    # if no sellers, force the user to add at least one
    sellers = get_all_sellers()
    if not sellers:
        print("📌 Aucun vendeur enregistré. Ajout obligatoire.")
        while True:
            url = input("Colle le lien de la boutique eBay : ").strip()
            if not url:
                print("❌ Lien invalide, recommence.")
                continue
            # deduce seller id
            sid = None
            if "/str/" in url:
                sid = url.split("/str/")[-1].split("?")[0].strip("/")
            else:
                parsed = urllib.parse.urlparse(url)
                params = dict(urllib.parse.parse_qsl(parsed.query))
                sid = params.get("_ssn") or url
            add_seller(sid, url)
            more = input("Ajouter un autre vendeur ? (y/n) ").strip().lower()
            if more != "y":
                break

    # give user option to add extra sellers before running
    while True:
        extra = input("Voulez-vous ajouter un vendeur supplémentaire avant de lancer ? (y/n) ").strip().lower()
        if extra == "y":
            sid = input("Seller ID (optionnel) : ").strip() or None
            url = input("Shop URL : ").strip()
            if not sid:
                if "/str/" in url:
                    sid = url.split("/str/")[-1].split("?")[0].strip("/")
                else:
                    parsed = urllib.parse.urlparse(url)
                    params = dict(urllib.parse.parse_qsl(parsed.query))
                    sid = params.get("_ssn") or url
            add_seller(sid, url)
            continue
        break

    sellers = get_all_sellers()
    if not sellers:
        print("Aucun vendeur trouvé en base. Fin.")
        return

    for seller_id, shop_url in sellers:
        try:
            scrape_seller(shop_url, seller_id)
        except Exception as e:
            print(f"❌ Erreur pendant le scraping de {seller_id}: {e}")

    export_db_to_csv(EXPORT_CSV)
    print("\n✅ Tous les vendeurs traités.")

if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            driver.quit()
        except:
            pass
        conn.close()
