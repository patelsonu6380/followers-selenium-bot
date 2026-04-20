# ============================================================
# AUTO FOLLOWER SENDER SCRIPT (DISTRIBUTED TARGETS VERSION)
# Logic: 1 Site = 1 Target (Round Robin), 4 Cycles per Account
# ============================================================

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time, random, sys, re
from accounts import register_login_fail, register_login_success


# ============================================================
# 1. CONFIGURATION
# ============================================================

from accounts import LOGIN_ACCOUNTS
from targets import TARGET_USERS
from websites import WEBSITES

FOLLOWERS_TOOL_PATH = "/tools/send-follower"
TOTAL_CYCLES_PER_ACCOUNT = 4  # Kitni baar websites ka loop chalana hai ek account se
TARGET_DELAY_RANGE = (10, 10) # Delay between websites

# ============================================================
# 2. DRIVER SETUP
# ============================================================

options = webdriver.ChromeOptions()

# 🔴 REQUIRED for GitHub Actions / Linux
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

# normal options
options.add_argument("--disable-notifications")
options.add_argument("--disable-blink-features=AutomationControlled")

options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)


driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
wait = WebDriverWait(driver, 15)
SITE_TABS = {}

# ============================================================
# 3. HELPER FUNCTIONS
# ============================================================

def log(msg):
    print(msg)
    sys.stdout.flush()

def get_root(url):
    return "/".join(url.split("/")[:3])

def close_popups():
    selectors = [
        "//button[contains(text(),'×')]",
        "//button[@class='close']",
        "//div[@class='modal-footer']//button",
        "//a[@class='close']"
    ]
    for xp in selectors:
        try:
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)
        except:
            pass

# ============================================================
# 4. TAB & COOKIE MANAGEMENT
# ============================================================

def open_all_tabs():
    log("🚀 Opening all website tabs...")
    first = True
    for site in WEBSITES:
        if first:
            driver.get(site["login_url"])
            first = False
        else:
            driver.execute_script(f"window.open('{site['login_url']}','_blank');")
            time.sleep(1.0)
        
        SITE_TABS[site["name"]] = driver.window_handles[-1]
        log(f"🧩 Tab opened -> {site['name']}")

def clear_cookies_and_reload():
    log("\n🧹 Cleaning up: Clearing cookies on all tabs...")
    for site in WEBSITES:
        try:
            handle = SITE_TABS.get(site["name"])
            if not handle: continue
            
            driver.switch_to.window(handle)
            driver.delete_all_cookies()
            time.sleep(0.5)
            driver.get(site["login_url"])
            time.sleep(1)
            log(f"🍪 Reset -> {site['name']}")
        except Exception as e:
            log(f"⚠️ Reset error {site['name']}: {e}")

# ============================================================
# 5. CORE LOGIC
# ============================================================

def is_login_really_success(root):
    try:
        if len(driver.find_elements(By.ID, "username")) > 0:
            return False
    except:
        pass

    indicators = [
        "//a[contains(@href, 'logout')]",
        "//span[contains(@id, 'Kredi')]",
        "//div[contains(@class, 'user')]"
    ]
    for xp in indicators:
        if len(driver.find_elements(By.XPATH, xp)) > 0:
            return True
    return False


def has_zero_credit():
    try:
        credit_el = driver.find_element(By.ID, "takipKrediCount")
        credit_text = credit_el.text.strip()
        if not credit_text:
            return True
        
        credit = int(re.sub(r"\D", "", credit_text))
        log(f"💰 Current Credit: {credit}")
        
        return credit <= 0
    except:
        log("⚠️ Credit element not found. Assuming 0 to skip.")
        return True


def login_with_account(account, root):
    close_popups()
    
    # already logged in
    if is_login_really_success(root):
        return True

    try:
        user_input = wait.until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        pass_input = wait.until(
            EC.presence_of_element_located((By.NAME, "password"))
        )
        
        try:
            btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        except:
            btn = driver.find_element(By.ID, "login_insta")

        user_input.clear()
        user_input.send_keys(account["user"])
        pass_input.clear()
        pass_input.send_keys(account["pass"])
        
        time.sleep(1)
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(8)

        # 🔍 LOGIN RESULT
        if is_login_really_success(root):
            log(f"✅ LOGIN SUCCESS: {account['user']}")

            # ✅ reset fail counter
            if "_id" in account:
                register_login_success(account["_id"])

            return True
        else:
            log(f"❌ LOGIN FAILED: {account['user']}")

            # 🔥 increase fail counter
            if "_id" in account:
                register_login_fail(account["_id"])

            return False

    except Exception as e:
        log(f"❌ Login Error: {e}")

        # 🔥 count exception as login fail
        if "_id" in account:
            register_login_fail(account["_id"])

        return False


def send_followers_single_target(root, target):
    try:
        driver.get(root + FOLLOWERS_TOOL_PATH)
    except:
        return False
        
    time.sleep(3)
    close_popups()

    # CREDIT CHECK
    if has_zero_credit():
        log("🚫 Credit is 0.")
        return "NO_CREDIT"

    try:
        box = wait.until(
            EC.element_to_be_clickable((By.NAME, "username"))
        )
        box.clear()
        box.send_keys(target)
        
        find_btn = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(text(),'User') or contains(text(),'Bul') or contains(text(),'Find')]"
            ))
        )
        driver.execute_script("arguments[0].click();", find_btn)
        
        time.sleep(3)

        start_btn = wait.until(
            EC.element_to_be_clickable((By.ID, "formTakipSubmitButton"))
        )
        driver.execute_script("arguments[0].click();", start_btn)
        
        log(f"⚡ Sent Request -> {target}")
        return True
        
    except Exception as e:
        log(f"⚠️ Failed to send to {target}: {e}")
        return False

# ============================================================
# 6. MAIN EXECUTION LOOP (FIXED VERSION)
# ============================================================

if __name__ == "__main__":

    open_all_tabs()

    try:
        for account in LOGIN_ACCOUNTS:
            log(f"\n==========================================")
            log(f"👤 LOGGING IN ACCOUNT: {account['user']}")
            log(f"==========================================")

            target_counter = 0
            SKIP_WEBSITES = set()   # ✅ RESET FOR EACH ACCOUNT

            for cycle in range(1, TOTAL_CYCLES_PER_ACCOUNT + 1):
                log(f"\n🔄 STARTING CYCLE {cycle}/{TOTAL_CYCLES_PER_ACCOUNT}")
                log("------------------------------------------")

                for site in WEBSITES:
                    # 🚫 Skip if credit was 0 earlier
                    if site["name"] in SKIP_WEBSITES:
                        log(f"⏭️ Skipped {site['name']} (No Credit earlier)")
                        continue

                    driver.switch_to.window(SITE_TABS[site["name"]])
                    root = get_root(site["login_url"])

                    # Login
                    if not login_with_account(account, root):
                        continue

                    current_target = TARGET_USERS[target_counter % len(TARGET_USERS)]
                    log(f"\n🌍 Site: {site['name']} --> 🎯 Target: {current_target}")

                    success = False

                    while not success:
                        result = send_followers_single_target(root, current_target)

                        # 🚫 Credit 0 → skip this site for remaining cycles
                        if result == "NO_CREDIT":
                            SKIP_WEBSITES.add(site["name"])
                            log(f"🚫 {site['name']} marked SKIP for remaining cycles")
                            break

                        # 🔁 Retry same target if failed
                        if result is False:
                            log(f"🔁 Retry same target: {current_target}")
                            time.sleep(5)
                            continue

                        # ✅ Success → next target
                        if result is True:
                            success = True
                            target_counter += 1

                    # Delay only after success or skip
                    delay = random.uniform(*TARGET_DELAY_RANGE)
                    log(f"⏳ Waiting {delay:.1f}s...")
                    time.sleep(delay)

            log(f"\n✅ Finished 4 Cycles for {account['user']}")
            clear_cookies_and_reload()
            time.sleep(5)

    except KeyboardInterrupt:
        log("\n🛑 Script stopped by user.")
    finally:
        log("👋 Exiting...")
        driver.quit()
