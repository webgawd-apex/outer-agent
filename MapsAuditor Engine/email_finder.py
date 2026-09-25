"""
email_finder.py
======================================================
Fast website email scraper using Playwright / requests & regex.
Scans:
  1. Main landing page (HTML, text, mailto: links)
  2. Subpages (/contact, /contact-us, /about, /about-us, /get-in-touch)
  3. Decodes obfuscated emails (e.g. user [at] domain [dot] com)
"""

import re
import urllib.parse
from bs4 import BeautifulSoup
import requests

EMAIL_REGEX = re.compile(
    r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
)

# Common generic/asset extensions or dummy emails to ignore
IGNORE_EMAILS = {
    "sentry.io", "wixpress.com", "example.com", "domain.com", 
    "email.com", "yourname@domain.com", "info@yourdomain.com",
    "wordpress.org", "wix.com", "squarespace.com", "google.com"
}

IGNORE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".woff", ".woff2"
}

CONTACT_PATHS = [
    "",
    "/contact",
    "/contact-us",
    "/contact_us",
    "/about",
    "/about-us",
    "/get-in-touch",
    "/reach-us"
]

def clean_email(email_str: str) -> str:
    """Clean and normalize email string."""
    if not email_str:
        return ""
    email = email_str.strip().lower()
    # Remove trailing punctuation often captured by regex
    email = re.sub(r'[.,;:\'")>\]]+$', '', email)
    
    # Check domain
    if "@" in email:
        domain = email.split("@")[-1]
        if any(ignored in domain for ignored in IGNORE_EMAILS):
            return ""
        if any(email.endswith(ext) for ext in IGNORE_EXTENSIONS):
            return ""
        if len(email) > 80 or len(email) < 6:
            return ""
        return email
    return ""

def extract_emails_from_text(text: str) -> set:
    """Extract and validate all email candidates from text."""
    if not text:
        return set()
    
    found = set()
    # 1. Standard regex
    raw_matches = EMAIL_REGEX.findall(text)
    for match in raw_matches:
        cleaned = clean_email(match)
        if cleaned:
            found.add(cleaned)
            
    # 2. Obfuscated emails: e.g. name [at] domain.com or name(at)domain(dot)com
    obf_matches = re.findall(r'([a-zA-Z0-9_.+-]+)\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([a-zA-Z0-9-]+)\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*([a-zA-Z0-9-.]+)', text, re.IGNORECASE)
    for part1, part2, part3 in obf_matches:
        cand = f"{part1}@{part2}.{part3}"
        cleaned = clean_email(cand)
        if cleaned:
            found.add(cleaned)
            
    return found

def extract_emails_from_html(html: str, base_url: str = "") -> set:
    """Extract mailto: links and visible emails from HTML."""
    if not html:
        return set()
        
    found = set()
    soup = BeautifulSoup(html, "html.parser")
    
    # Check all mailto links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            raw_email = href.replace("mailto:", "").split("?")[0]
            cleaned = clean_email(urllib.parse.unquote(raw_email))
            if cleaned:
                found.add(cleaned)
                
    # Check body text
    body_text = soup.get_text(separator=" ")
    found.update(extract_emails_from_text(body_text))
    return found

def find_email_for_website(website_url: str, timeout: int = 8) -> str:
    """
    Attempt to fetch homepage and contact pages via HTTP requests to find business email.
    Returns the best email found or None.
    """
    if not website_url or not website_url.startswith("http"):
        return None

    parsed = urllib.parse.urlparse(website_url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    all_emails = set()
    
    for path in CONTACT_PATHS:
        target_url = urllib.parse.urljoin(base_origin, path)
        try:
            r = requests.get(target_url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
            if r.status_code == 200:
                emails = extract_emails_from_html(r.text, base_origin)
                all_emails.update(emails)
                if all_emails:
                    # Found at least one email, we can pick the highest priority (e.g. info@, contact@, sales@, or owner)
                    break
        except Exception:
            continue
            
    if not all_emails:
        return None

    # Priority sorting: info@, contact@, office@, quotes@, or direct names
    priority_prefixes = ["info@", "contact@", "office@", "quotes@", "support@", "admin@", "sales@"]
    for prefix in priority_prefixes:
        for email in all_emails:
            if email.startswith(prefix):
                return email
                
    # Return first valid email
    return sorted(list(all_emails))[0]
