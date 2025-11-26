from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
from datetime import datetime
import pandas as pd
import os



def human_pause(a=2, b=5):
    time.sleep(random.uniform(a, b))


options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

wait = WebDriverWait(driver, 20)

url = input("Colle le lien de la boutique eBay : ")
driver.get(url)
human_pause(5, 8)


# ================= SELLER ID =================

about_tab = wait.until(EC.presence_of_element_located(
    (By.XPATH, "//div[@role='tab' and contains(., 'About')]")
))
driver.execute_script("arguments[0].click();", about_tab)
human_pause(3, 5)

seller_section = wait.until(EC.presence_of_element_located(
    (By.CSS_SELECTOR, "section.str-about-description__seller-info")
))

seller_id = None
for line in seller_section.text.split("\n"):
    if "Seller:" in line:
        seller_id = line.replace("Seller:", "").strip()

print("✅ Seller ID :", seller_id)

# Retour boutique
driver.get(url)
human_pause(5, 8)


# ================= FILTRE USED =================

condition_button = wait.until(EC.element_to_be_clickable(
    (By.XPATH, "//span[contains(text(),'Condition')]")
))
driver.execute_script("arguments[0].click();", condition_button)
human_pause()

for item in driver.find_elements(By.CLASS_NAME, "filter-menu-button__item"):
    if "Used" in item.text:
        driver.execute_script("arguments[0].click();", item)
        break

human_pause(5, 8)
results = []


# ================= SCRAPING =================

def process_cards():
    cards = driver.find_elements(By.CSS_SELECTOR, "div.str-item-card__header-container")
    print(f"🔎 {len(cards)} cartes trouvées sur cette page")

    for card in cards:
        # Scroll jusqu'à la carte
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        human_pause(1, 2)

        # Cliquer sur la carte
        try:
            driver.execute_script("arguments[0].click();", card)
        except:
            print("⚠️ Impossible de cliquer sur cette carte")
            continue

        human_pause(4, 6)
        driver.switch_to.window(driver.window_handles[-1])  # Aller sur l'onglet de l'annonce

        # URL et ID de l'annonce
        item_url = driver.current_url
        item_id = item_url.split("/itm/")[-1].split("?")[0]

        # Titre
        try:
            title = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "h1.x-item-title__mainTitle span")
            )).text
        except:
            title = None

        # OEM
        try:
            oem = driver.find_element(By.CSS_SELECTOR,
                "dl.ux-labels-values--manufacturerPartNumber dd span").text
        except:
            oem = None

        # Prix
        price_text = None
        try:
            # Prix normal
            price_elem = driver.find_element(By.CSS_SELECTOR, "div.x-price-primary span")
            price_text = price_elem.text
        except:
            # Prix barré ou Best Offer
            try:
                price_elem = driver.find_element(By.CSS_SELECTOR, "div.x-additional-info span.ux-textspans--STRIKETHROUGH")
                price_text = price_elem.text
            except:
                # Cas "See price on checkout"
                price_text = None

        if price_text:
            if " " in price_text:
                currency = price_text.split(" ")[0]
                price = price_text.replace(currency, "").strip()
            else:
                currency = None
                price = price_text
        else:
            currency = price = None

        # Affichage des infos
        data = {
            "item_id": item_id,
            "title": title,
            "oem_reference": oem,
            "price": price,
            "currency": currency,
            "url": item_url,
            "seller": seller_id,
            "listing_start_date": datetime.now(),
            "status": "ACTIVE"
        }

        results.append(data)

        print("\n==============================")
        for k, v in data.items():
            print(f"{k} : {v}")


        # Fermer l'onglet et revenir à la page principale
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        human_pause(2, 4)




# ================= PAGINATION =================

while True:
    process_cards()

    try:
        next_button = driver.find_element(By.CSS_SELECTOR, "a.pagination__next")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_button)
        human_pause(2, 4)
        next_button.click()
        human_pause(5, 8)
    except:
        print("\n✅ Toutes les annonces traitées.")
        break

print("\n🎯 SCRAPING TERMINÉ AVEC SUCCÈS")

if results:
    os.makedirs("exports", exist_ok=True)
    df = pd.DataFrame(results)

    filename = f"exports/ebay_listings_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    df.to_excel(filename, index=False)

    print(f"\n📁 Fichier Excel généré : {filename}")
else:
    print("⚠️ Aucune donnée à exporter.")
