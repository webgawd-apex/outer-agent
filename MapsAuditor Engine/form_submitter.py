"""
form_submitter.py
======================================================
Autonomous Contact Form Submitter using Playwright.
Features:
  - Smart contact page navigation ("Contact", "Get Quote", "Free Estimate")
  - Intelligent input detection (Name, Email, Phone, Message, Subject)
  - CAPTCHA detection (reCAPTCHA, hCaptcha, Turnstile, Arkose)
  - Screenshot capture upon CAPTCHA for Discord alert
  - Form submission verification (Thank You messages, redirects)
"""

import os
import time
import json
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "captcha_screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def detect_captcha(page: Page) -> bool:
    """Check if CAPTCHA elements or iframes exist on the page."""
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='challenges.cloudflare.com']",
        "div.g-recaptcha",
        "div.h-captcha",
        "div.cf-turnstile",
        "#turnstile-wrapper",
        "#g-recaptcha-response",
        "#h-captcha-response"
    ]
    for sel in captcha_selectors:
        try:
            if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible(timeout=1000):
                return True
        except Exception:
            pass
            
    # Check page text for captcha mentions
    try:
        content = page.content().lower()
        if "recaptcha" in content or "cf-turnstile" in content or "hcaptcha" in content:
            # Verify if it's rendered
            for frame in page.frames:
                if any(x in frame.url for x in ["recaptcha", "hcaptcha", "turnstile", "cloudflare"]):
                    return True
    except Exception:
        pass

    return False

def navigate_to_contact_form(page: Page) -> bool:
    """Find and click 'Contact', 'Get a Quote', or 'Estimate' link if not already on form page."""
    # Check if a form is already present on the landing page
    if page.locator("form").count() > 0:
        # Check if form has message or textarea
        if page.locator("form textarea, form input[type='email']").count() > 0:
            return True

    # Try finding link to contact page
    contact_keywords = [
        "contact us", "contact", "get a quote", "free estimate", 
        "request a quote", "get in touch", "book an estimate", "request service"
    ]

    for kw in contact_keywords:
        try:
            link = page.get_by_role("link", name=kw, exact=False).first
            if link.is_visible(timeout=1000):
                link.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=7000)
                time.sleep(2)
                return True
        except Exception:
            pass

    # Try CSS selector fallback
    for kw in ["contact", "quote", "estimate"]:
        try:
            link = page.locator(f"a[href*='{kw}']").first
            if link.is_visible(timeout=1000):
                link.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=7000)
                time.sleep(2)
                return True
        except Exception:
            pass

    return False

def find_best_input(page: Page, keywords: list, input_types: list = None):
    """Search for input elements matching name, placeholder, aria-label, id, or type."""
    if input_types is None:
        input_types = ["text", "email", "tel", "textarea"]

    # 1. Look by specific placeholder or label text
    for kw in keywords:
        try:
            el = page.get_by_placeholder(kw, exact=False).first
            if el.is_visible(timeout=500):
                return el
        except Exception:
            pass
        try:
            el = page.get_by_label(kw, exact=False).first
            if el.is_visible(timeout=500):
                return el
        except Exception:
            pass

    # 2. Look by attribute selectors
    for kw in keywords:
        for attr in ["name", "id", "class", "aria-label"]:
            sel = f"input[{attr}*='{kw}' i], textarea[{attr}*='{kw}' i]"
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=500):
                    return el
            except Exception:
                pass

    return None

def submit_contact_form(page: Page, business_name: str = "Business") -> dict:
    """
    Attempts to fill and submit the contact form on the given page.
    Returns dict: {'status': 'submitted' | 'captcha' | 'no_form' | 'error', 'details': ..., 'screenshot': ...}
    """
    settings = load_settings()
    sender_name = settings.get("form_fields", {}).get("name_field_value") or settings.get("sender", {}).get("name", "Daniel Joshua")
    sender_email = settings.get("form_fields", {}).get("email_field_value") or settings.get("sender", {}).get("email", "daniel@example.com")
    sender_phone = settings.get("form_fields", {}).get("phone_field_value") or settings.get("sender", {}).get("phone", "480-555-0199")
    subject_text = settings.get("form_fields", {}).get("subject_field_value", "Quick question about your old leads")
    message_text = settings.get("outreach_message", "Hi! Quick question, do you ever go back through old quotes or leads that never closed? I help contractors turn those into new jobs. It's free to look into, and I only get paid if it works. Happy to explain more if useful.")

    try:
        # Step 1: Ensure we are on the form page
        navigate_to_contact_form(page)
        time.sleep(1.5)

        # Step 2: Check for CAPTCHA prior to submission
        if detect_captcha(page):
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"captcha_{int(time.time())}.png")
            page.screenshot(path=screenshot_path)
            return {"status": "captcha", "screenshot": screenshot_path, "url": page.url}

        # Step 3: Match form fields
        name_input = find_best_input(page, ["name", "full_name", "first_name", "fname", "contact_name", "your-name"])
        first_name_input = find_best_input(page, ["first_name", "fname", "firstname"])
        last_name_input = find_best_input(page, ["last_name", "lname", "lastname"])
        email_input = page.locator("input[type='email']").first
        if not email_input or not email_input.is_visible(timeout=500):
            email_input = find_best_input(page, ["email", "e-mail", "your-email", "mail"], ["email", "text"])

        phone_input = page.locator("input[type='tel']").first
        if not phone_input or not phone_input.is_visible(timeout=500):
            phone_input = find_best_input(page, ["phone", "tel", "cell", "mobile", "number"], ["tel", "text"])

        subject_input = find_best_input(page, ["subject", "topic", "regarding", "service_needed"])
        
        message_input = page.locator("textarea").first
        if not message_input or not message_input.is_visible(timeout=500):
            message_input = find_best_input(page, ["message", "comment", "details", "description", "note", "question", "how can we help"])

        # Validate that we found at least email and message or name
        if not message_input and not email_input:
            return {"status": "no_form", "details": "No standard contact form fields found"}

        # Step 4: Fill fields
        if first_name_input and last_name_input:
            parts = sender_name.split(" ", 1)
            first_name_input.fill(parts[0])
            last_name_input.fill(parts[1] if len(parts) > 1 else parts[0])
        elif name_input:
            name_input.fill(sender_name)

        if email_input:
            email_input.fill(sender_email)

        if phone_input and sender_phone:
            phone_input.fill(sender_phone)

        if subject_input:
            subject_input.fill(subject_text)

        if message_input:
            message_input.fill(message_text)

        # Check for CAPTCHA once more after filling
        if detect_captcha(page):
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"captcha_{int(time.time())}.png")
            page.screenshot(path=screenshot_path)
            return {"status": "captcha", "screenshot": screenshot_path, "url": page.url}

        # Step 5: Locate submit button
        submit_btn = None
        for text in ["Submit", "Send Message", "Send", "Request Quote", "Get Quote", "Get Estimate", "Contact Us", "Submit Message"]:
            try:
                btn = page.get_by_role("button", name=text, exact=False).first
                if btn.is_visible(timeout=500):
                    submit_btn = btn
                    break
            except Exception:
                pass

        if not submit_btn:
            submit_btn = page.locator("form button[type='submit'], form input[type='submit'], button:has-text('Send'), button:has-text('Submit')").first

        if not submit_btn or not submit_btn.is_visible(timeout=1000):
            return {"status": "error", "details": "Could not find form submit button"}

        # Step 6: Click submit
        submit_btn.click(timeout=5000)
        time.sleep(3)

        # Step 7: Check post-submit state (captcha or success)
        if detect_captcha(page):
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"captcha_{int(time.time())}.png")
            page.screenshot(path=screenshot_path)
            return {"status": "captcha", "screenshot": screenshot_path, "url": page.url}

        # Verify success indicators
        success_indicators = [
            "thank you", "thanks", "message has been sent", "we have received your", 
            "successfully submitted", "we'll be in touch", "quote request received"
        ]
        page_text = page.content().lower()
        is_success = any(ind in page_text for ind in success_indicators)

        return {
            "status": "submitted",
            "verified": is_success,
            "url": page.url
        }

    except Exception as e:
        return {"status": "error", "details": str(e)}
