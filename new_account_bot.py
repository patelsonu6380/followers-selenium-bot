import time

import firebase_init
from firebase_admin import db
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from gmail_accounts import get_refresh_token_by_email
from otp_reader import fetch_otp

PROCESS_LIMIT = 1


def log(msg):
    print(msg, flush=True)


def now():
    return int(time.time())


def _claim_one_pending_account():
    queue = db.reference("new_accounts").get() or {}
    if not queue:
        return None

    ordered = sorted(queue.items(), key=lambda item: int((item[1] or {}).get("addedAt", 0)))

    for acc_id, data in ordered:
        if not isinstance(data, dict):
            continue

        status = str(data.get("status", "pending")).lower().strip()
        if status not in {"pending", "created", ""}:
            continue

        ref = db.reference(f"new_accounts/{acc_id}")

        def txn(current):
            if not current:
                return None

            current_status = str(current.get("status", "pending")).lower().strip()
            if current_status not in {"pending", "created", ""}:
                return None

            current["status"] = "processing"
            current["processingAt"] = now()
            return current

        claimed = ref.transaction(txn)
        if claimed and str(claimed.get("status", "")).lower() == "processing":
            claimed["_id"] = acc_id
            return claimed

    return None


def _mark_failed(acc_id, reason):
    db.reference(f"new_accounts/{acc_id}").update(
        {
            "status": "failed",
            "lastError": str(reason)[:500],
            "lastTriedAt": now(),
        }
    )


def _move_to_active(acc_id, account):
    active_payload = {
        "username": account["username"],
        "password": account["password"],
        "failCount": 0,
        "lockedUntil": 0,
        "permanentBlocked": False,
        "addedAt": now(),
        "source": "new_accounts",
        "email": account.get("email", ""),
    }

    active_ref = db.reference("accounts").push(active_payload)
    db.reference(f"new_accounts/{acc_id}").remove()
    return active_ref.key


def _load_login_url():
    websites = db.reference("websites").get() or {}
    for site in websites.values():
        if isinstance(site, dict) and site.get("login_url"):
            return str(site["login_url"]).strip()
    raise RuntimeError("No login_url found in websites")


def _try_find(driver, by, value):
    items = driver.find_elements(by, value)
    return items[0] if items else None


def _is_login_success(driver):
    url = driver.current_url.lower()
    if any(token in url for token in ["challenge", "checkpoint"]):
        return False

    visible_user_inputs = [
        el
        for el in driver.find_elements(By.NAME, "username")
        if el.is_displayed() and el.is_enabled()
    ]
    if visible_user_inputs:
        return False

    indicators = [
        "//a[contains(@href, 'logout')]",
        "//span[contains(@id, 'Kredi')]",
        "//div[contains(@class, 'user')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'logout')]",
    ]
    for xp in indicators:
        if driver.find_elements(By.XPATH, xp):
            return True

    return "login" not in url


def _is_security_screen(driver):
    url = driver.current_url.lower()
    if any(token in url for token in ["challenge", "checkpoint"]):
        return True

    if _try_find(driver, By.ID, "kod_onayla_input"):
        return True
    if _try_find(driver, By.CLASS_NAME, "onay_kodu_ekrani"):
        return True
    if _try_find(driver, By.NAME, "security_code"):
        return True
    return False


def _click_first(driver, xpaths):
    for xp in xpaths:
        els = driver.find_elements(By.XPATH, xp)
        for el in els:
            if el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
                return True
    return False


def _complete_otp_flow(driver, wait, refresh_token):
    try:
        choice_select = _try_find(driver, By.ID, "choice_select")
        if choice_select:
            driver.execute_script(
                "arguments[0].value='1'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                choice_select,
            )
    except Exception:
        pass

    sent = _click_first(
        driver,
        [
            "//button[contains(text(),'Guvenlik Kodu')]",
            "//button[contains(text(),'venlik Kodu')]",
            "//button[contains(text(),'Send Code')]",
            "//button[contains(text(),'Security Code')]",
        ],
    )
    if not sent:
        raise RuntimeError("OTP send button not found")

    log("OTP code requested, waiting in Gmail...")
    otp = fetch_otp(refresh_token=refresh_token, timeout=300)
    if not otp:
        raise RuntimeError("OTP not received")

    otp_input = (
        _try_find(driver, By.ID, "kod_onayla_input")
        or _try_find(driver, By.NAME, "security_code")
        or _try_find(driver, By.NAME, "verificationCode")
    )
    if not otp_input:
        raise RuntimeError("OTP input field not found")

    driver.execute_script(
        """
        const input = arguments[0];
        const value = arguments[1];
        input.focus();
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        otp_input,
        otp,
    )

    # Some sites don't react to programmatic value set. Fallback to typing if needed.
    try:
        current = otp_input.get_attribute("value") or ""
        if str(current).strip() != str(otp).strip():
            otp_input.clear()
            otp_input.send_keys(otp)
    except Exception:
        pass

    verified = _click_first(
        driver,
        [
            "//button[contains(text(),'Onayla')]",
            "//button[contains(text(),'Submit')]",
            "//button[contains(text(),'Verify')]",
            "//*[@class='kod_onayla']",
        ],
    )
    if not verified:
        raise RuntimeError("OTP verify button not found")

    wait.until(lambda d: _is_login_success(d))


def _login_and_verify(account, login_url, refresh_token):
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 25)

    try:
        driver.get(login_url)
        log(f"Login check started for: {account['username']}")

        user_input = (
            _try_find(driver, By.NAME, "username")
            or _try_find(driver, By.XPATH, "//input[@type='text' or @type='email']")
        )
        pass_input = _try_find(driver, By.NAME, "password") or _try_find(
            driver, By.XPATH, "//input[@type='password']"
        )
        if not user_input or not pass_input:
            raise RuntimeError("Username/password fields not found")

        user_input.clear()
        user_input.send_keys(account["username"])
        pass_input.clear()
        pass_input.send_keys(account["password"])

        clicked = _click_first(
            driver,
            [
                "//button[@type='submit']",
                "//*[@id='login_insta']",
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
                "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
            ],
        )
        if not clicked:
            raise RuntimeError("Login button not found")

        time.sleep(6)

        if _is_security_screen(driver):
            log("Security screen detected, starting OTP flow")
            _complete_otp_flow(driver, wait, refresh_token)
            log("OTP verification completed")
        else:
            wait.until(lambda d: _is_login_success(d))

        # Base success evaluation
        base_success = _is_login_success(driver)

        # Special-case: for birtakipci ensure final tools page is reached
        try:
            if base_success and "birtakipci" in (login_url or "").lower():
                tools_wait = WebDriverWait(driver, 60)
                tools_wait.until(lambda d: "tools" in (d.current_url or "").lower())
        except Exception:
            # If we couldn't reach the tools page, consider it not a full success
            base_success = False

        return base_success
    finally:
        driver.quit()


def process_pending_accounts(limit=PROCESS_LIMIT):
    login_url = _load_login_url()
    processed = 0

    while processed < limit:
        account = _claim_one_pending_account()
        if not account:
            break

        acc_id = account["_id"]
        username = str(account.get("username", "")).strip()
        password = str(account.get("password", "")).strip()
        email = str(account.get("email", "")).strip()

        if not username or not password or not email:
            _mark_failed(acc_id, "Missing username/password/email in new_accounts")
            continue

        try:
            refresh_token = get_refresh_token_by_email(email)
            success = _login_and_verify(
                {"username": username, "password": password},
                login_url=login_url,
                refresh_token=refresh_token,
            )

            if not success:
                raise RuntimeError("Login not confirmed")

            active_id = _move_to_active(acc_id, account)
            log(f"Activated: {username} -> accounts/{active_id}")
            processed += 1
        except Exception as err:
            _mark_failed(acc_id, err)
            log(f"Failed: {username} | {err}")

    return processed


if __name__ == "__main__":
    count = process_pending_accounts(limit=PROCESS_LIMIT)
    log(f"Done. Activated accounts: {count}")
