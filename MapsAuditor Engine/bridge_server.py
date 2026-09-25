# ============================================================
# SSL BYPASS - FORCES ALL SSL CONNECTIONS TO WORK
# MUST BE AT THE VERY TOP BEFORE ANY IMPORTS
# ============================================================
import os
import sys
import warnings
warnings.filterwarnings("ignore")

# Option 1: Environment variables
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['SSL_CERT_FILE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# Option 2: SSL Context override
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
    print("✅ SSL verification disabled via context")
except:
    pass

# Option 3: Disable urllib3 warnings
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("✅ SSL warnings disabled")
except:
    pass

# Option 4: Monkey patch requests if available
try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    
    # Patch post
    old_post = requests.post
    def patched_post(url, *args, **kwargs):
        kwargs['verify'] = False
        kwargs.setdefault('timeout', 30)
        return old_post(url, *args, **kwargs)
    requests.post = patched_post
    
    # Patch get
    old_get = requests.get
    def patched_get(url, *args, **kwargs):
        kwargs['verify'] = False
        kwargs.setdefault('timeout', 30)
        return old_get(url, *args, **kwargs)
    requests.get = patched_get
    
    print("✅ Requests patched with SSL bypass")
except:
    pass

print("=" * 50)
print("SSL BYPASS ACTIVATED")
print("All SSL verification is disabled for this session")
print("=" * 50)

# ============================================================
# NOW THE REST OF THE IMPORTS
# ============================================================
import re
import sys
import json
import time
import base64
import queue
import threading
import subprocess
import datetime
import urllib.parse
import glob
import shutil
from pathlib import Path

# ============================================================
# DEPENDENCY CHECK
# ============================================================
try:
    from flask import Flask, request, jsonify, make_response
    from flask_cors import CORS
except ImportError as e:
    print(f"ERROR: Missing Flask. Run: pip install flask flask-cors")
    sys.exit(1)

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError as e:
    print(f"ERROR: Missing openpyxl. Run: pip install openpyxl")
    sys.exit(1)

try:
    import phonenumbers
    from phonenumbers import carrier, geocoder, number_type
    HAS_PHONENUMBERS = True
except:
    HAS_PHONENUMBERS = False
    print("WARNING: Phonenumbers not installed.")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
    print("✅ Playwright is available")
except:
    HAS_PLAYWRIGHT = False
    print("❌ Playwright not installed. Run: pip install playwright")

# ============================================================
# CONFIGURATION
# ============================================================
# --- API Keys ---
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
PAGESPEED_API_KEY = "YOUR_PAGESPEED_API_KEY_HERE"

# --- Gemini Model ---
GEMINI_MODEL = "gemini-3.5-flash"

# --- Your Info ---
YOUR_NAME = "Daniel Joshua"
YOUR_WEBSITE = "https://yourwebsite.com"

# --- Timeouts ---
PAGE_LOAD_TIMEOUT = 15
SCREENSHOT_TIMEOUT = 20
GEMINI_TIMEOUT = 60
PAGESPEED_TIMEOUT = 30
AUDIT_TOTAL_TIMEOUT = 180

# --- Load Time Thresholds (Option B) ---
LOAD_FAST = 20
LOAD_AVERAGE = 25
LOAD_SLOW = 45
LOAD_VERY_SLOW = 70
LOAD_CRITICAL = 120

# --- Screenshot Settings ---
VIEWPORT_HEIGHT = 800
MAX_SCREENSHOTS = 10
SCREENSHOT_OVERLAP = 100

# --- Revisit Settings ---
REVISIT_INTERVAL = 20
MAX_REVISIT_ATTEMPTS = 3

# --- Retry Settings ---
MAX_RETRIES = 2
RETRY_DELAY = 3
NUM_WORKERS = 3
NUM_REVISIT_WORKERS = 1

# --- Rate Limiting ---
PAGESPEED_DELAY = 2

# --- File Paths ---
OUTPUT_EXCEL = f"footprint_audited_leads_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
DASHBOARD_FILE = "index.html"
SCREENSHOTS_DIR = "screenshots"
ERROR_LOG = "audit_errors.log"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================================
# QUEUES & THREADING
# ============================================================
save_queue = queue.Queue()
audit_queue = queue.Queue()
revisit_queue = queue.Queue()

all_leads_cache = []
processed_names = set()
revisit_lead_count = 0
excel_lock = threading.Lock()
dashboard_lock = threading.Lock()
revisit_lock = threading.Lock()

_pagespeed_last_call = 0
_pagespeed_lock = threading.Lock()

# ============================================================
# BUSINESS CONTEXT MAPPING
# ============================================================
BUSINESS_CONTEXT_MAP = {
    "plumber": {
        "target_customer": "Homeowners and businesses needing plumbing services",
        "primary_conversion": "Call for Emergency Service",
        "secondary_conversion": "Request a Quote"
    },
    "plumbing": {
        "target_customer": "Homeowners and businesses needing plumbing services",
        "primary_conversion": "Call for Emergency Service",
        "secondary_conversion": "Request a Quote"
    },
    "roofer": {
        "target_customer": "Homeowners needing roof repair or replacement",
        "primary_conversion": "Request a Quote",
        "secondary_conversion": "Call for Emergency Repair"
    },
    "roofing": {
        "target_customer": "Homeowners needing roof repair or replacement",
        "primary_conversion": "Request a Quote",
        "secondary_conversion": "Call for Emergency Repair"
    },
    "hvac": {
        "target_customer": "Homeowners and businesses needing heating and cooling services",
        "primary_conversion": "Call for Service",
        "secondary_conversion": "Request a Quote"
    },
    "air conditioning": {
        "target_customer": "Homeowners and businesses needing air conditioning services",
        "primary_conversion": "Call for Service",
        "secondary_conversion": "Request a Quote"
    },
    "electrician": {
        "target_customer": "Homeowners and businesses needing electrical services",
        "primary_conversion": "Call for Service",
        "secondary_conversion": "Request a Quote"
    },
    "contractor": {
        "target_customer": "Homeowners and businesses needing construction services",
        "primary_conversion": "Request a Quote",
        "secondary_conversion": "Call for Consultation"
    },
    "landscaping": {
        "target_customer": "Homeowners and businesses needing landscaping services",
        "primary_conversion": "Request a Quote",
        "secondary_conversion": "Call for Consultation"
    },
    "dentist": {
        "target_customer": "Patients needing dental care",
        "primary_conversion": "Book an Appointment",
        "secondary_conversion": "Call the Office"
    },
    "lawyer": {
        "target_customer": "Individuals and businesses needing legal services",
        "primary_conversion": "Schedule a Consultation",
        "secondary_conversion": "Call the Office"
    },
    "real estate": {
        "target_customer": "Home buyers and sellers",
        "primary_conversion": "Contact an Agent",
        "secondary_conversion": "Call the Office"
    },
    "restaurant": {
        "target_customer": "Diners looking for a meal",
        "primary_conversion": "Book a Table",
        "secondary_conversion": "Order Takeout"
    },
    "cleaning": {
        "target_customer": "Homeowners and businesses needing cleaning services",
        "primary_conversion": "Request a Quote",
        "secondary_conversion": "Book a Service"
    },
    "auto repair": {
        "target_customer": "Vehicle owners needing repair services",
        "primary_conversion": "Schedule a Repair",
        "secondary_conversion": "Call the Shop"
    },
    "salon": {
        "target_customer": "Clients needing beauty services",
        "primary_conversion": "Book an Appointment",
        "secondary_conversion": "Call the Salon"
    }
}

DEFAULT_CONTEXT = {
    "target_customer": "Customers needing services",
    "primary_conversion": "Contact the Business",
    "secondary_conversion": "Request Information"
}

# ============================================================
# CHROME PATH DETECTION
# ============================================================
def find_chrome_path():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        os.path.expanduser(r"~\AppData\Local\ms-playwright\chromium-*\chrome-win64\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    
    for path in paths:
        if "*" in path:
            matches = glob.glob(path)
            if matches:
                return matches[0]
        elif os.path.exists(path):
            return path
    
    try:
        result = subprocess.run(["where", "chrome"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            chrome_path = result.stdout.strip().split('\n')[0]
            if chrome_path and os.path.exists(chrome_path):
                return chrome_path
    except:
        pass
    
    return None

CHROME_PATH = find_chrome_path()
if CHROME_PATH:
    print(f"✅ Chrome found at: {CHROME_PATH}")
else:
    print("⚠️ Chrome not found.")

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def sanitize_string(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item).strip()
    return str(value).strip()

def validate_phone(raw_number):
    if not HAS_PHONENUMBERS or not raw_number:
        return {"valid_format": False, "line_type": "Unknown", "formatted": raw_number}
    try:
        parsed = phonenumbers.parse(raw_number, "US")
        valid = phonenumbers.is_valid_number(parsed)
        line_type_map = {0: "Fixed", 1: "Mobile", 2: "Fixed/Mobile", 3: "Toll-free", 4: "Premium", 6: "VOIP"}
        ntype = number_type(parsed)
        return {
            "valid_format": valid,
            "line_type": line_type_map.get(ntype, "Unknown"),
            "formatted": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL) if valid else raw_number,
        }
    except:
        return {"valid_format": False, "line_type": "Unknown", "formatted": raw_number}

def log_error(message):
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass

def parse_load_time(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace('s', '').replace('S', '').replace('~', '').replace('seconds', '').strip()
        try:
            return float(cleaned)
        except:
            return None
    return None

def calculate_visitor_loss(load_time_seconds):
    if load_time_seconds is None:
        return 30
    try:
        seconds = float(load_time_seconds)
        if seconds > 10:
            return 55
        elif seconds > 5:
            return 45
        elif seconds > 3:
            return 35
        else:
            return 20
    except:
        return 30

def get_load_category(load_time_seconds):
    if load_time_seconds is None:
        return "unknown"
    try:
        seconds = float(load_time_seconds)
        if seconds < LOAD_FAST:
            return "fast"
        elif seconds < LOAD_AVERAGE:
            return "average"
        elif seconds < LOAD_SLOW:
            return "slow"
        elif seconds < LOAD_VERY_SLOW:
            return "very_slow"
        else:
            return "critical"
    except:
        return "unknown"

def get_business_context(niche):
    if not niche:
        return DEFAULT_CONTEXT
    
    niche_lower = niche.lower()
    
    # Try exact match
    if niche_lower in BUSINESS_CONTEXT_MAP:
        return BUSINESS_CONTEXT_MAP[niche_lower]
    
    # Try partial match
    for key, context in BUSINESS_CONTEXT_MAP.items():
        if key in niche_lower:
            return context
    
    return DEFAULT_CONTEXT

# ============================================================
# EXCEL FUNCTIONS
# ============================================================
def init_excel():
    try:
        with excel_lock:
            if not os.path.exists(OUTPUT_EXCEL):
                wb = Workbook()
                ws = wb.active
                ws.title = "Leads"
                
                headers = [
                    "Business Name", "Phone", "Phone Valid?", "Line Type", "Website",
                    "Rating", "Review Count", "Last Review Date", 
                    "Performance", "SEO", "HTTPS?", "Mobile Friendly?",
                    "Load Time", "Load Category", "Conversion Score", 
                    "Design Score", "CTA Score", "Contact Score", "Trust Score", "Capture Score",
                    "Priority", "Friction", "Clarity", "Hierarchy",
                    "Recommendations", "Screenshot Count", "Opportunity Score", "Health Score",
                    "Email Subject", "Email Body", "WhatsApp Message", "Audit Status",
                    "Revisit Attempts"
                ]
                
                ws.append(headers)
                
                for col in range(1, len(headers) + 1):
                    cell = ws.cell(row=1, column=col)
                    cell.fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
                    cell.font = Font(color="FFFFFF", bold=True)
                
                wb.save(OUTPUT_EXCEL)
                print(f"✅ Created Excel: {OUTPUT_EXCEL}")
                return True
            return True
    except Exception as e:
        print(f"Excel init error: {e}")
        return False

def save_to_excel(record):
    try:
        with excel_lock:
            if not os.path.exists(OUTPUT_EXCEL):
                init_excel()
            
            wb = load_workbook(OUTPUT_EXCEL)
            ws = wb.active
            
            existing_row = None
            for row in range(2, ws.max_row + 1):
                if ws.cell(row=row, column=1).value == record.get("name"):
                    existing_row = row
                    break
            
            row_data = [
                record.get("name", "Unknown"),
                record.get("phone", ""),
                record.get("phone_valid", "No"),
                record.get("line_type", "Unknown"),
                record.get("website", ""),
                record.get("rating", "N/A"),
                record.get("review_count", 0),
                record.get("last_review_date", "N/A"),
                record.get("perf_score", "N/A"),
                record.get("seo_score", "N/A"),
                record.get("https", "N/A"),
                record.get("mobile_friendly", "N/A"),
                record.get("load_time", "N/A"),
                record.get("load_category", "unknown"),
                record.get("conversion_score", 50),
                record.get("design_score", 50),
                record.get("cta_score", 50),
                record.get("contact_score", 50),
                record.get("trust_score", 50),
                record.get("capture_score", 50),
                record.get("priority", "MEDIUM"),
                record.get("friction", ""),
                record.get("clarity", ""),
                record.get("hierarchy", ""),
                record.get("recommendations", ""),
                record.get("screenshot_count", 0),
                record.get("opportunity_score", 50),
                record.get("health_score", 50),
                record.get("email_subject", ""),
                record.get("email_body", ""),
                record.get("whatsapp_message", ""),
                record.get("audit_status", "Pending"),
                record.get("revisit_attempts", 0)
            ]
            
            if existing_row:
                for col, value in enumerate(row_data, start=1):
                    ws.cell(row=existing_row, column=col).value = value
            else:
                ws.append(row_data)
                existing_row = ws.max_row
            
            if record.get("opportunity_score", 0) >= 70:
                hot_fill = PatternFill(start_color="FDE68A", end_color="FDE68A", fill_type="solid")
                for col in range(1, 35):
                    ws.cell(row=existing_row, column=col).fill = hot_fill
            
            if record.get("audit_status") == "Critical":
                crit_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
                for col in range(1, 35):
                    ws.cell(row=existing_row, column=col).fill = crit_fill
            
            wb.save(OUTPUT_EXCEL)
            return True
            
    except Exception as e:
        print(f"Excel save error: {e}")
        return False

# ============================================================
# DASHBOARD FUNCTIONS
# ============================================================
def build_dashboard():
    try:
        with dashboard_lock:
            sorted_leads = sorted(all_leads_cache, key=lambda x: x.get('opportunity_score', 0), reverse=True)
            cards_html = ""
            
            for index, lead in enumerate(sorted_leads):
                encoded_wa = urllib.parse.quote(lead.get('whatsapp_message', ''))
                encoded_subject = urllib.parse.quote(lead.get('email_subject', ''))
                encoded_body = urllib.parse.quote(lead.get('email_body', ''))
                clean_phone = re.sub(r'[^0-9+]', '', lead.get('phone', ''))
                
                opp_score = lead.get('opportunity_score', 0)
                conv_score = lead.get('conversion_score', 50)
                health_score = lead.get('health_score', 50)
                audit_status = lead.get('audit_status', 'Pending')
                load_time = lead.get('load_time', 'N/A')
                load_category = lead.get('load_category', 'unknown')
                revisit_attempts = lead.get('revisit_attempts', 0)
                screenshot_count = lead.get('screenshot_count', 0)
                
                design_score = lead.get('design_score', 50)
                cta_score = lead.get('cta_score', 50)
                contact_score = lead.get('contact_score', 50)
                trust_score = lead.get('trust_score', 50)
                capture_score = lead.get('capture_score', 50)
                priority = lead.get('priority', 'MEDIUM')
                recommendations = lead.get('recommendations', '')
                friction = lead.get('friction', '')
                clarity = lead.get('clarity', '')
                hierarchy = lead.get('hierarchy', '')
                
                priority_badges = {
                    "CRITICAL": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800">🔴 CRITICAL</span>',
                    "HIGH": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-orange-100 text-orange-800">🟠 HIGH</span>',
                    "MEDIUM": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">🟡 MEDIUM</span>',
                    "LOW": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">🟢 LOW</span>'
                }
                priority_badge = priority_badges.get(priority, priority_badges["MEDIUM"])
                
                category_badges = {
                    "fast": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">⚡ Fast</span>',
                    "average": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">📊 Average</span>',
                    "slow": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">⚠️ Slow</span>',
                    "very_slow": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-orange-100 text-orange-800">⚠️ Very Slow</span>',
                    "critical": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800">🚨 Critical</span>',
                    "unknown": '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">⏳ Unknown</span>'
                }
                category_badge = category_badges.get(load_category, category_badges["unknown"])
                
                revisit_badge = ""
                if revisit_attempts > 0:
                    revisit_badge = f'<span class="px-2 py-1 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">🔄 Revisit {revisit_attempts}/{MAX_REVISIT_ATTEMPTS}</span>'
                
                screenshot_badge = ""
                if screenshot_count > 0:
                    screenshot_badge = f'<span class="px-2 py-1 text-xs font-semibold rounded-full bg-indigo-100 text-indigo-800">📷 {screenshot_count} images</span>'
                
                opp_color = "bg-amber-100 text-amber-800" if opp_score >= 70 else "bg-gray-100 text-gray-800"
                
                if conv_score >= 70:
                    conv_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">Good Conversion</span>'
                elif conv_score >= 50:
                    conv_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">Average Conversion</span>'
                else:
                    conv_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800">Poor Conversion</span>'
                
                if health_score >= 70:
                    health_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">Good Health</span>'
                elif health_score >= 50:
                    health_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">Average Health</span>'
                else:
                    health_badge = '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800">Poor Health</span>'
                
                status_color = {
                    "Audited": "bg-green-100 text-green-800",
                    "Pending": "bg-gray-100 text-gray-800",
                    "Failed": "bg-red-100 text-red-800",
                    "Critical": "bg-red-100 text-red-800 font-bold"
                }.get(audit_status, "bg-gray-100 text-gray-800")
                
                scores_summary = f"Design: {design_score} | CTA: {cta_score} | Contact: {contact_score} | Trust: {trust_score} | Capture: {capture_score}"
                
                analysis_parts = []
                if clarity and clarity != "Cannot determine from screenshot":
                    analysis_parts.append(f"Clarity: {clarity[:60]}")
                if friction and friction != "None visible":
                    analysis_parts.append(f"Friction: {friction[:60]}")
                if hierarchy and hierarchy != "Cannot determine from screenshot":
                    analysis_parts.append(f"Hierarchy: {hierarchy[:60]}")
                
                analysis_summary = " | ".join(analysis_parts) if analysis_parts else "Full analysis available"
                
                recommendations_summary = recommendations[:200] if recommendations else ""
                
                cards_html += f"""
                <div class="bg-white rounded-lg shadow p-6 border border-gray-200 hover:shadow-lg transition-shadow" id="card-{index}">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 flex-wrap">
                                <span class="px-2 py-1 text-xs font-semibold rounded-full {opp_color}">
                                    Opp: {opp_score}
                                </span>
                                {conv_badge}
                                {health_badge}
                                {priority_badge}
                                {category_badge}
                                {revisit_badge}
                                {screenshot_badge}
                                <span class="text-xs px-2 py-1 rounded-full {status_color}">{audit_status}</span>
                                <span class="text-sm text-gray-500">Phone: {lead.get('phone', 'N/A')}</span>
                            </div>
                            <h3 class="text-xl font-bold mt-2">{lead.get('name', 'Unknown')}</h3>
                            <div class="flex items-center gap-4 mt-1 text-sm text-gray-600">
                                <span>Rating: {lead.get('rating', 'N/A')} ({lead.get('review_count', 0)} reviews)</span>
                                <span>Last Review: {lead.get('last_review_date', 'N/A')}</span>
                            </div>
                            <div class="mt-2 text-sm">
                                <span class="font-semibold">Website:</span> {lead.get('website', 'No Website')}
                            </div>
                            <div class="mt-2 flex gap-4 text-sm flex-wrap">
                                <span>Performance: {lead.get('perf_score', 'N/A')}</span>
                                <span>SEO: {lead.get('seo_score', 'N/A')}</span>
                                <span>Load Time: {load_time}</span>
                                <span>Conversion: {conv_score}/100</span>
                            </div>
                            <div class="mt-1 text-sm text-gray-700 bg-gray-50 p-2 rounded">
                                <span class="font-semibold">Scores:</span> {scores_summary}
                            </div>
                            <div class="mt-1 text-sm text-gray-700 bg-gray-50 p-2 rounded">
                                <span class="font-semibold">Analysis:</span> {analysis_summary}
                            </div>
                            {f'<div class="mt-1 text-sm text-gray-700 bg-blue-50 p-2 rounded"><span class="font-semibold">Recommendation:</span> {recommendations_summary}</div>' if recommendations_summary else ''}
                            {f'<div class="mt-1 text-sm text-gray-700 bg-gray-50 p-2 rounded"><span class="font-semibold">Screenshots:</span> <a href="{SCREENSHOTS_DIR}/{re.sub(r"[^a-zA-Z0-9]", "_", lead.get("name", "Unknown"))}/" target="_blank" class="text-blue-500 hover:underline">View {screenshot_count} images</a></div>' if screenshot_count > 0 else ''}
                        </div>
                        <div class="flex flex-col gap-2 ml-4">
                            <a href="https://wa.me/{clean_phone}?text={encoded_wa}" target="_blank" 
                               class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition text-sm font-medium text-center">
                                WhatsApp
                            </a>
                            <a href="mailto:?subject={encoded_subject}&body={encoded_body}" 
                               class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition text-sm font-medium text-center">
                                Email
                            </a>
                        </div>
                    </div>
                </div>
                """
            
            total = len(sorted_leads)
            high_opp = len([l for l in sorted_leads if l.get('opportunity_score', 0) >= 70])
            audited = len([l for l in sorted_leads if l.get('audit_status') == 'Audited'])
            failed = len([l for l in sorted_leads if l.get('audit_status') == 'Failed'])
            critical = len([l for l in sorted_leads if l.get('audit_status') == 'Critical'])
            no_website = len([l for l in sorted_leads if not l.get('website')])
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Footprint Audit Dashboard</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <style>
                    body {{ background: #f3f4f6; }}
                    .refresh-btn {{
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        background: #3b82f6;
                        color: white;
                        padding: 12px 24px;
                        border-radius: 8px;
                        border: none;
                        cursor: pointer;
                        font-weight: bold;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    }}
                    .refresh-btn:hover {{ background: #2563eb; }}
                    .stats {{
                        background: white;
                        padding: 15px;
                        border-radius: 8px;
                        margin-bottom: 20px;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    }}
                </style>
            </head>
            <body>
                <div class="container mx-auto px-4 py-8 max-w-7xl">
                    <div class="flex justify-between items-center mb-6">
                        <div>
                            <h1 class="text-3xl font-bold text-gray-800">Footprint Audit Dashboard</h1>
                            <p class="text-sm text-gray-500 mt-1">Updated: {datetime.datetime.now().strftime('%H:%M:%S')}</p>
                        </div>
                        <span class="text-sm text-gray-500">{total} leads</span>
                    </div>
                    <div class="stats">
                        <div class="grid grid-cols-6 gap-4">
                            <div><strong>Total:</strong> {total}</div>
                            <div><strong>High Opp:</strong> {high_opp}</div>
                            <div><strong>Audited:</strong> {audited}</div>
                            <div><strong>Critical:</strong> {critical}</div>
                            <div><strong>Failed:</strong> {failed}</div>
                            <div><strong>No Website:</strong> {no_website}</div>
                        </div>
                    </div>
                    <div class="grid gap-6">
                        {cards_html or 'Waiting for leads... Run Chrome extension to start.'}
                    </div>
                </div>
                <button onclick="location.reload()" class="refresh-btn">Refresh</button>
                <script>
                    setInterval(() => {{ location.reload(); }}, 5000);
                </script>
            </body>
            </html>
            """
            
            with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            print(f"✅ Dashboard updated with {len(sorted_leads)} leads")
            return True
    except Exception as e:
        print(f"Dashboard error: {e}")
        return False

# ============================================================
# GEMINI ANALYSIS WITH SSL BYPASS
# ============================================================
def analyze_section_with_gemini(image_path, business_name, business_type, section_name, target_customer, primary_conversion, secondary_conversion):
    """
    Analyze a section screenshot with Gemini using SSL bypass
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return {
            "design": "Gemini not configured", "design_score": 50,
            "cta": "Gemini not configured", "cta_score": 50,
            "contact": "Gemini not configured", "contact_score": 50,
            "trust": "Gemini not configured", "trust_score": 50,
            "capture": "Gemini not configured", "capture_score": 50,
            "friction": "Cannot determine",
            "clarity": "Cannot determine",
            "hierarchy": "Cannot determine",
            "overall": "Gemini not configured",
            "score": 50,
            "priority": "MEDIUM",
            "recommendations": "Configure Gemini API key"
        }
    
    if not HAS_REQUESTS:
        return {
            "design": "Requests not installed", "design_score": 50,
            "cta": "Requests not installed", "cta_score": 50,
            "contact": "Requests not installed", "contact_score": 50,
            "trust": "Requests not installed", "trust_score": 50,
            "capture": "Requests not installed", "capture_score": 50,
            "friction": "Cannot determine",
            "clarity": "Cannot determine",
            "hierarchy": "Cannot determine",
            "overall": "Requests not installed",
            "score": 50,
            "priority": "MEDIUM",
            "recommendations": "Install requests package"
        }
    
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        
        # Simplified prompt
        user_prompt = f"""
You are a website conversion auditor. Analyze this screenshot of a {section_name} section for {business_name} ({business_type}).

Target customers: {target_customer}
Goal: {primary_conversion}

Rate these 5 elements from 0-100:
1. DESIGN: How professional and modern is the design?
2. CTA: How clear and prominent is the Call-to-Action?
3. CONTACT: How easy is it to find contact information?
4. TRUST: Are there trust signals (testimonials, certifications)?
5. CAPTURE: Are there forms or booking options?

Also give:
- FRICTION: The biggest conversion obstacle visible
- CLARITY: How clear is the message? (one sentence)
- HIERARCHY: Does visual flow guide to conversion? (one sentence)
- OVERALL: Summary of conversion effectiveness (one sentence)
- SCORE: Overall conversion score (0-100)
- PRIORITY: CRITICAL/HIGH/MEDIUM/LOW
- RECOMMENDATIONS: One specific actionable recommendation

Output exactly in this format:
DESIGN: [assessment] | SCORE: [0-100]
CTA: [assessment] | SCORE: [0-100]
CONTACT: [assessment] | SCORE: [0-100]
TRUST: [assessment] | SCORE: [0-100]
CAPTURE: [assessment] | SCORE: [0-100]
FRICTION: [assessment]
CLARITY: [assessment]
HIERARCHY: [assessment]
OVERALL: [assessment]
SCORE: [0-100]
PRIORITY: [CRITICAL/HIGH/MEDIUM/LOW]
RECOMMENDATIONS: [recommendation]
"""
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": user_prompt},
                    {"inline_data": {"mime_type": "image/png", "data": img_b64}}
                ]
            }]
        }
        
        # SSL bypass is already active via the patched requests
        resp = requests.post(endpoint, json=payload, timeout=GEMINI_TIMEOUT)
        
        if resp.status_code != 200:
            return {
                "design": f"API error: {resp.status_code}", "design_score": 50,
                "cta": "API error", "cta_score": 50,
                "contact": "API error", "contact_score": 50,
                "trust": "API error", "trust_score": 50,
                "capture": "API error", "capture_score": 50,
                "friction": "Cannot determine",
                "clarity": "Cannot determine",
                "hierarchy": "Cannot determine",
                "overall": f"API error: {resp.status_code}",
                "score": 50,
                "priority": "MEDIUM",
                "recommendations": "Check Gemini API key"
            }
        
        result = resp.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        
        # Log raw response for debugging
        print(f"      Gemini raw response: {text[:200]}...")
        
        # Parse response
        design = "Cannot determine"
        cta = "Cannot determine"
        contact = "Cannot determine"
        trust = "Cannot determine"
        capture = "Cannot determine"
        friction = "Cannot determine"
        clarity = "Cannot determine"
        hierarchy = "Cannot determine"
        overall = "Cannot determine"
        score = 50
        priority = "MEDIUM"
        recommendations = "No specific recommendation"
        design_score = 50
        cta_score = 50
        contact_score = 50
        trust_score = 50
        capture_score = 50
        
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('DESIGN:'):
                parts = line.replace('DESIGN:', '').strip().split('|')
                if len(parts) >= 2:
                    design = parts[0].strip()
                    score_match = re.search(r'(\d{1,3})', parts[1])
                    if score_match:
                        design_score = min(100, max(0, int(score_match.group(1))))
                else:
                    design = parts[0].strip()
            elif line.startswith('CTA:'):
                parts = line.replace('CTA:', '').strip().split('|')
                if len(parts) >= 2:
                    cta = parts[0].strip()
                    score_match = re.search(r'(\d{1,3})', parts[1])
                    if score_match:
                        cta_score = min(100, max(0, int(score_match.group(1))))
                else:
                    cta = parts[0].strip()
            elif line.startswith('CONTACT:'):
                parts = line.replace('CONTACT:', '').strip().split('|')
                if len(parts) >= 2:
                    contact = parts[0].strip()
                    score_match = re.search(r'(\d{1,3})', parts[1])
                    if score_match:
                        contact_score = min(100, max(0, int(score_match.group(1))))
                else:
                    contact = parts[0].strip()
            elif line.startswith('TRUST:'):
                parts = line.replace('TRUST:', '').strip().split('|')
                if len(parts) >= 2:
                    trust = parts[0].strip()
                    score_match = re.search(r'(\d{1,3})', parts[1])
                    if score_match:
                        trust_score = min(100, max(0, int(score_match.group(1))))
                else:
                    trust = parts[0].strip()
            elif line.startswith('CAPTURE:'):
                parts = line.replace('CAPTURE:', '').strip().split('|')
                if len(parts) >= 2:
                    capture = parts[0].strip()
                    score_match = re.search(r'(\d{1,3})', parts[1])
                    if score_match:
                        capture_score = min(100, max(0, int(score_match.group(1))))
                else:
                    capture = parts[0].strip()
            elif line.startswith('FRICTION:'):
                friction = line.replace('FRICTION:', '').strip()
            elif line.startswith('CLARITY:'):
                clarity = line.replace('CLARITY:', '').strip()
            elif line.startswith('HIERARCHY:'):
                hierarchy = line.replace('HIERARCHY:', '').strip()
            elif line.startswith('OVERALL:'):
                overall = line.replace('OVERALL:', '').strip()
            elif line.startswith('SCORE:'):
                try:
                    score = int(re.search(r'\d+', line).group())
                    score = min(100, max(0, score))
                except:
                    score = 50
            elif line.startswith('PRIORITY:'):
                priority = line.replace('PRIORITY:', '').strip().upper()
            elif line.startswith('RECOMMENDATIONS:'):
                recommendations = line.replace('RECOMMENDATIONS:', '').strip()
        
        return {
            "design": design, "design_score": design_score,
            "cta": cta, "cta_score": cta_score,
            "contact": contact, "contact_score": contact_score,
            "trust": trust, "trust_score": trust_score,
            "capture": capture, "capture_score": capture_score,
            "friction": friction,
            "clarity": clarity,
            "hierarchy": hierarchy,
            "overall": overall,
            "score": score,
            "priority": priority,
            "recommendations": recommendations
        }
        
    except Exception as e:
        error_msg = str(e)[:100]
        print(f"      ❌ Gemini error: {error_msg}")
        return {
            "design": f"Error: {error_msg}", "design_score": 50,
            "cta": "Error", "cta_score": 50,
            "contact": "Error", "contact_score": 50,
            "trust": "Error", "trust_score": 50,
            "capture": "Error", "capture_score": 50,
            "friction": "Cannot determine",
            "clarity": "Cannot determine",
            "hierarchy": "Cannot determine",
            "overall": f"Error: {error_msg}",
            "score": 50,
            "priority": "MEDIUM",
            "recommendations": "Check error logs"
        }

def analyze_all_sections(screenshot_paths, business_name, business_type, target_customer, primary_conversion, secondary_conversion):
    """
    Analyze all section screenshots and combine into full report
    """
    if not screenshot_paths:
        return {
            "design": "No screenshots", "design_score": 50,
            "cta": "No screenshots", "cta_score": 50,
            "contact": "No screenshots", "contact_score": 50,
            "trust": "No screenshots", "trust_score": 50,
            "capture": "No screenshots", "capture_score": 50,
            "friction": "Cannot determine",
            "clarity": "Cannot determine",
            "hierarchy": "Cannot determine",
            "overall": "No screenshots available",
            "score": 50,
            "priority": "MEDIUM",
            "recommendations": "No screenshots to analyze"
        }
    
    print(f"      🤖 Analyzing {len(screenshot_paths)} screenshots with Gemini...")
    
    all_results = []
    
    for i, img_path in enumerate(screenshot_paths):
        if i == 0:
            section_name = "Hero"
        elif i == 1:
            section_name = "Services"
        elif i == 2:
            section_name = "About"
        elif i == 3:
            section_name = "Testimonials"
        elif i == 4:
            section_name = "Contact"
        else:
            section_name = f"Section {i+1}"
        
        print(f"      📊 Analyzing {section_name}...")
        
        result = analyze_section_with_gemini(
            img_path,
            business_name,
            business_type,
            section_name,
            target_customer,
            primary_conversion,
            secondary_conversion
        )
        
        all_results.append({
            "section": section_name,
            "design": result["design"],
            "design_score": result["design_score"],
            "cta": result["cta"],
            "cta_score": result["cta_score"],
            "contact": result["contact"],
            "contact_score": result["contact_score"],
            "trust": result["trust"],
            "trust_score": result["trust_score"],
            "capture": result["capture"],
            "capture_score": result["capture_score"],
            "friction": result["friction"],
            "clarity": result["clarity"],
            "hierarchy": result["hierarchy"],
            "overall": result["overall"],
            "score": result["score"],
            "priority": result["priority"],
            "recommendations": result["recommendations"]
        })
    
    # Find highest priority
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    highest_priority = "LOW"
    for r in all_results:
        if r["priority"] in priority_order:
            if priority_order[r["priority"]] < priority_order.get(highest_priority, 2):
                highest_priority = r["priority"]
    
    # Collect recommendations
    all_recommendations = []
    for r in all_results:
        if r["recommendations"] and r["recommendations"] != "No specific recommendation":
            all_recommendations.append({
                "section": r["section"],
                "text": r["recommendations"],
                "priority": r["priority"]
            })
    
    all_recommendations.sort(key=lambda x: priority_order.get(x["priority"], 2))
    
    unique_recs = []
    seen = set()
    for rec in all_recommendations:
        if rec["text"] not in seen:
            seen.add(rec["text"])
            unique_recs.append(rec)
            if len(unique_recs) >= 3:
                break
    
    # Calculate weighted averages
    weights = {"Hero": 1.5, "Services": 1.0, "About": 0.8, "Testimonials": 0.8, "Contact": 1.3, "Footer": 0.6}
    
    total_weight = 0
    weighted_design = 0
    weighted_cta = 0
    weighted_contact = 0
    weighted_trust = 0
    weighted_capture = 0
    weighted_score = 0
    
    for r in all_results:
        section = r["section"]
        weight = weights.get(section, 1.0)
        
        weighted_design += r["design_score"] * weight
        weighted_cta += r["cta_score"] * weight
        weighted_contact += r["contact_score"] * weight
        weighted_trust += r["trust_score"] * weight
        weighted_capture += r["capture_score"] * weight
        weighted_score += r["score"] * weight
        total_weight += weight
    
    if total_weight > 0:
        avg_design = round(weighted_design / total_weight)
        avg_cta = round(weighted_cta / total_weight)
        avg_contact = round(weighted_contact / total_weight)
        avg_trust = round(weighted_trust / total_weight)
        avg_capture = round(weighted_capture / total_weight)
        avg_score = round(weighted_score / total_weight)
    else:
        avg_design = 50
        avg_cta = 50
        avg_contact = 50
        avg_trust = 50
        avg_capture = 50
        avg_score = 50
    
    # Combine friction, clarity, hierarchy
    frictions = [r["friction"] for r in all_results if r["friction"] and r["friction"] != "Cannot determine"]
    clarities = [r["clarity"] for r in all_results if r["clarity"] and r["clarity"] != "Cannot determine"]
    hierarchies = [r["hierarchy"] for r in all_results if r["hierarchy"] and r["hierarchy"] != "Cannot determine"]
    
    combined_friction = frictions[0] if frictions else "None identified"
    combined_clarity = clarities[0] if clarities else "Cannot determine"
    combined_hierarchy = hierarchies[0] if hierarchies else "Cannot determine"
    
    combined_recs = []
    for rec in unique_recs[:3]:
        combined_recs.append(f"{rec['section']}: {rec['text']}")
    
    combined_recommendations = " | ".join(combined_recs) if combined_recs else "No specific recommendations"
    
    overall_summary = f"Conversion effectiveness: {avg_score}/100 | Priority: {highest_priority}"
    
    print(f"      ✅ Gemini complete: Conversion Score={avg_score}")
    
    return {
        "design": f"Average design quality across sections", "design_score": avg_design,
        "cta": f"Average CTA effectiveness across sections", "cta_score": avg_cta,
        "contact": f"Average contact accessibility across sections", "contact_score": avg_contact,
        "trust": f"Average trust signals across sections", "trust_score": avg_trust,
        "capture": f"Average lead capture across sections", "capture_score": avg_capture,
        "friction": combined_friction,
        "clarity": combined_clarity,
        "hierarchy": combined_hierarchy,
        "overall": overall_summary,
        "score": avg_score,
        "priority": highest_priority,
        "recommendations": combined_recommendations,
        "sections": all_results
    }

# ============================================================
# PLAYWRIGHT METRICS AND SCREENSHOTS
# ============================================================
def get_playwright_metrics_and_screenshots(url, business_name):
    """
    Get website metrics and section screenshots using Playwright
    """
    if not HAS_PLAYWRIGHT:
        return None, False, False, None, None, 0, []
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.set_default_timeout(PAGE_LOAD_TIMEOUT * 1000)
            
            # Load page
            start = time.time()
            try:
                page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT * 1000)
            except:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=5000)
                except:
                    browser.close()
                    return None, False, False, None, None, 0, []
            
            load_time = time.time() - start
            https = url.startswith("https")
            
            # Check mobile friendly
            try:
                viewport = page.evaluate("""
                    () => {
                        const meta = document.querySelector('meta[name="viewport"]');
                        return meta ? meta.content : null;
                    }
                """)
                mobile_friendly = viewport is not None and "width=device-width" in viewport.lower()
            except:
                mobile_friendly = False
            
            # Take section screenshots
            folder_path = SCREENSHOTS_DIR
            success, screenshot_paths, err = take_section_screenshots(page, business_name, folder_path)
            
            screenshot_count = len(screenshot_paths) if screenshot_paths else 0
            
            browser.close()
            
            # Calculate performance score from load time
            if load_time < LOAD_FAST:
                perf_score = 85
            elif load_time < LOAD_AVERAGE:
                perf_score = 70
            elif load_time < LOAD_SLOW:
                perf_score = 55
            else:
                perf_score = 40
            
            # Calculate SEO score from HTTPS + Mobile
            seo_score = 50
            if https:
                seo_score += 20
            if mobile_friendly:
                seo_score += 20
            
            print(f"      ✅ Playwright: Load={load_time:.1f}s, HTTPS={https}, Mobile={mobile_friendly}, Screenshots={screenshot_count}")
            
            return load_time, https, mobile_friendly, perf_score, seo_score, screenshot_count, screenshot_paths
            
    except Exception as e:
        print(f"      ⚠️ Playwright error: {e}")
        return None, False, False, None, None, 0, []

def take_section_screenshots(page, business_name, folder_path):
    """
    Take section-based screenshots of a website
    """
    try:
        # Get page height and viewport
        page_height = page.evaluate("document.body.scrollHeight")
        viewport_height = page.evaluate("window.innerHeight")
        
        if page_height <= 0:
            return False, [], "Invalid page height"
        
        # Calculate number of screenshots needed
        step = viewport_height - SCREENSHOT_OVERLAP
        total_steps = max(1, int((page_height - viewport_height) / step) + 2)
        total_steps = min(total_steps, MAX_SCREENSHOTS)
        
        screenshot_paths = []
        
        # Create business folder
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', business_name)
        business_folder = os.path.join(folder_path, safe_name)
        os.makedirs(business_folder, exist_ok=True)
        
        for i in range(total_steps):
            scroll_position = min(i * step, page_height - viewport_height)
            if scroll_position < 0:
                scroll_position = 0
            
            # Scroll to position
            page.evaluate(f"window.scrollTo(0, {scroll_position})")
            time.sleep(0.3)
            
            # Take screenshot
            img_path = os.path.join(business_folder, f"{i+1}.png")
            page.screenshot(path=img_path, full_page=False)
            screenshot_paths.append(img_path)
            
            print(f"      📷 Screenshot {i+1}/{total_steps}: {scroll_position}px")
        
        return True, screenshot_paths, None
        
    except Exception as e:
        return False, [], str(e)

# ============================================================
# MAIN AUDIT PROCESSOR
# ============================================================
def process_single_audit(data, worker_id, is_revisit=False):
    name = data.get("name", "Unknown")
    website = sanitize_string(data.get("website", ""))
    niche = sanitize_string(data.get("niche", "Service Provider"))
    rating = data.get("rating")
    try:
        rating = float(rating) if rating else None
    except:
        rating = None
    
    review_count = data.get("review_count", 0)
    try:
        review_count = int(review_count) if review_count else 0
    except:
        review_count = 0
    
    last_review_date = sanitize_string(data.get("last_review_date", "N/A"))
    revisit_attempts = data.get("revisit_attempts", 0)
    
    print(f"[Worker {worker_id}] {'REVISIT' if is_revisit else 'AUDITING'}: {name}")
    
    # Get business context
    context = get_business_context(niche)
    target_customer = context.get("target_customer", "Customers needing services")
    primary_conversion = context.get("primary_conversion", "Contact the Business")
    secondary_conversion = context.get("secondary_conversion", "Request Information")
    business_type = niche.capitalize() if niche else "Service Provider"
    
    print(f"[Worker {worker_id}] Context: {business_type} | {primary_conversion}")
    
    audit_results = {
        "perf_score": "N/A",
        "seo_score": "N/A",
        "https": "N/A",
        "mobile_friendly": "N/A",
        "load_time": "N/A",
        "load_category": "unknown",
        "conversion_score": 50,
        "design_score": 50,
        "cta_score": 50,
        "contact_score": 50,
        "trust_score": 50,
        "capture_score": 50,
        "priority": "MEDIUM",
        "friction": "",
        "clarity": "",
        "hierarchy": "",
        "recommendations": "",
        "screenshot_count": 0,
        "health_score": 50,
        "opportunity_score": 50,
        "design_notes": "Processing...",
        "audit_status": "Pending",
        "is_critical": False,
        "revisit_attempts": revisit_attempts
    }
    
    # No website - quick complete
    if not website:
        print(f"[Worker {worker_id}] No website - high opportunity")
        audit_results["design_notes"] = "No website - High opportunity"
        audit_results["conversion_score"] = 30
        audit_results["health_score"] = 20
        audit_results["opportunity_score"] = 95
        audit_results["audit_status"] = "Audited"
        
        email_subject, email_body, whatsapp_msg = generate_messages(
            name, "N/A", "unknown", 0, False, False, "", "", ""
        )
        audit_results.update({
            "email_subject": email_subject,
            "email_body": email_body,
            "whatsapp_message": whatsapp_msg
        })
        return audit_results
    
    # Get metrics and screenshots
    print(f"[Worker {worker_id}] Getting website metrics and screenshots...")
    load_time, https, mobile_friendly, perf_score, seo_score, screenshot_count, screenshot_paths = get_playwright_metrics_and_screenshots(website, name)
    
    if load_time is not None:
        print(f"[Worker {worker_id}] Load Time: {load_time:.1f}s, HTTPS: {https}, Mobile: {mobile_friendly}")
        audit_results["load_time"] = f"{load_time:.1f}s"
        audit_results["https"] = "Yes" if https else "No"
        audit_results["mobile_friendly"] = "Yes" if mobile_friendly else "No"
        audit_results["perf_score"] = perf_score
        audit_results["seo_score"] = seo_score
        audit_results["screenshot_count"] = screenshot_count
        
        # Determine category
        category = get_load_category(load_time)
        audit_results["load_category"] = category
        
        # Check if critical
        if load_time >= LOAD_CRITICAL:
            print(f"[Worker {worker_id}] ⚠️ Critical - load time {load_time:.1f}s >= {LOAD_CRITICAL}s")
            audit_results["is_critical"] = True
            audit_results["audit_status"] = "Critical" if revisit_attempts >= 1 else "Pending"
            
            # Estimate conversion from load time
            if load_time > 100:
                audit_results["conversion_score"] = 20
            elif load_time > 70:
                audit_results["conversion_score"] = 30
            elif load_time > 45:
                audit_results["conversion_score"] = 40
            else:
                audit_results["conversion_score"] = 45
            
            audit_results["design_notes"] = f"Critical - Load time {load_time:.1f}s exceeds {LOAD_CRITICAL}s threshold"
        else:
            # Full audit with Gemini if we have screenshots
            if screenshot_count > 0:
                gemini_results = analyze_all_sections(
                    screenshot_paths,
                    name,
                    business_type,
                    target_customer,
                    primary_conversion,
                    secondary_conversion
                )
                
                # Extract results
                audit_results["design_score"] = gemini_results.get("design_score", 50)
                audit_results["cta_score"] = gemini_results.get("cta_score", 50)
                audit_results["contact_score"] = gemini_results.get("contact_score", 50)
                audit_results["trust_score"] = gemini_results.get("trust_score", 50)
                audit_results["capture_score"] = gemini_results.get("capture_score", 50)
                audit_results["conversion_score"] = gemini_results.get("score", 50)
                audit_results["priority"] = gemini_results.get("priority", "MEDIUM")
                audit_results["friction"] = gemini_results.get("friction", "")
                audit_results["clarity"] = gemini_results.get("clarity", "")
                audit_results["hierarchy"] = gemini_results.get("hierarchy", "")
                audit_results["recommendations"] = gemini_results.get("recommendations", "")
                audit_results["design_notes"] = gemini_results.get("overall", "Analysis complete")
                audit_results["audit_status"] = "Audited"
            else:
                audit_results["design_notes"] = "No screenshots captured"
                audit_results["conversion_score"] = 50 if load_time < 30 else 40
                audit_results["audit_status"] = "Audited"
    else:
        print(f"[Worker {worker_id}] ❌ All metrics failed")
        audit_results["perf_score"] = 40
        audit_results["seo_score"] = 35
        audit_results["https"] = "Unknown"
        audit_results["mobile_friendly"] = "Unknown"
        audit_results["load_time"] = "N/A"
        audit_results["load_category"] = "unknown"
        audit_results["conversion_score"] = 30
        audit_results["design_notes"] = "All metrics failed - check website"
        audit_results["audit_status"] = "Failed"
    
    # Calculate scores
    health_score = calculate_health_score(
        audit_results["perf_score"],
        audit_results["seo_score"],
        audit_results["conversion_score"],
        review_count,
        rating
    )
    audit_results["health_score"] = health_score
    
    opp_score = calculate_opportunity_score(
        True,
        audit_results["perf_score"],
        audit_results["seo_score"],
        audit_results["conversion_score"],
        review_count,
        audit_results["load_time"],
        audit_results.get("is_critical", False)
    )
    audit_results["opportunity_score"] = opp_score
    
    # Generate messages
    try:
        load_seconds = parse_load_time(audit_results["load_time"])
        visitor_loss = calculate_visitor_loss(load_seconds)
    except:
        visitor_loss = 30
    
    email_subject, email_body, whatsapp_msg = generate_messages(
        name,
        audit_results["load_time"],
        audit_results["load_category"],
        visitor_loss,
        True,
        audit_results.get("is_critical", False),
        audit_results.get("design_notes", ""),
        audit_results.get("recommendations", "")
    )
    
    audit_results.update({
        "email_subject": email_subject,
        "email_body": email_body,
        "whatsapp_message": whatsapp_msg
    })
    
    if audit_results.get("audit_status") == "Pending":
        audit_results["audit_status"] = "Audited"
    
    print(f"[Worker {worker_id}] ✅ Complete: {name} (Health={health_score}, Opp={opp_score})")
    return audit_results

def calculate_health_score(perf_score, seo_score, conversion_score, review_count, rating):
    score = 50
    
    if perf_score and perf_score != "N/A":
        score += (perf_score - 50) * 0.15
    
    if seo_score and seo_score != "N/A":
        score += (seo_score - 50) * 0.10
    
    if conversion_score:
        score += (conversion_score - 50) * 0.15
    
    if review_count and review_count > 0:
        if review_count > 50:
            score += 15
        elif review_count > 20:
            score += 10
        elif review_count > 5:
            score += 5
    
    if rating and rating > 0:
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 10
        elif rating >= 3.5:
            score += 5
    
    return round(min(max(score, 0), 100))

def calculate_opportunity_score(has_website, perf_score, seo_score, conversion_score, review_count, load_time, is_critical=False):
    if not has_website:
        return 95
    
    if is_critical:
        return 95
    
    score = 50
    
    if perf_score and perf_score != "N/A" and perf_score < 70:
        score += (70 - perf_score) * 0.3
    
    if seo_score and seo_score != "N/A" and seo_score < 70:
        score += (70 - seo_score) * 0.2
    
    if conversion_score and conversion_score < 60:
        score += (60 - conversion_score) * 0.3
    
    if review_count < 12:
        score += 15
    elif review_count < 25:
        score += 10
    
    if load_time:
        load_seconds = parse_load_time(load_time)
        if load_seconds and load_seconds > 4:
            score += 15
        elif load_seconds and load_seconds > 3:
            score += 10
    
    return round(min(score, 100))

def generate_messages(name, load_time, load_category, visitor_loss, has_website, is_critical=False, design_notes="", recommendations=""):
    if not has_website:
        subject = f"Website missing for {name}"
        email_body = f"""Hello,

I was looking at {name} on Google Maps and noticed you don't have a website listed.

You have great reviews from customers, but without a website, you're losing potential customers who want to learn more before calling.

I help local businesses get online quickly and start getting more calls.

Would you like to see what a simple website could look like for your business?

Best,
{YOUR_NAME}"""
        
        whatsapp_msg = f"Hi {name}, I found your business on Google Maps. You have great reviews but no website! This means you're losing customers who want to check you out online. Want to see a quick mock-up? No pressure."
        
        return subject, email_body, whatsapp_msg
    
    if load_time and load_time != "N/A" and load_time != "Unknown":
        load_display = f"{load_time}s" if isinstance(load_time, (int, float)) else load_time
    else:
        load_display = "a few seconds"
    
    # Build audit summary
    audit_summary = []
    if design_notes and design_notes != "Processing audit..." and design_notes != "No screenshots available":
        audit_summary.append(f"Analysis: {design_notes[:80]}")
    if recommendations:
        audit_summary.append(f"Recommendation: {recommendations[:80]}")
    
    audit_summary_text = "\n".join([f"  - {item}" for item in audit_summary]) if audit_summary else "  - Full audit available"
    
    if is_critical or load_category == "critical":
        subject = f"Urgent: Your website is extremely slow"
        email_body = f"""Hello,

I was looking at {name} on Google Maps and noticed your website is taking {load_display} to load.

This is a critical issue - about 70% of visitors will leave before your site loads.

This could be costing you dozens of potential customers every day.

I went ahead and did a quick audit of your business' online presence.

Here's what I found:
{audit_summary_text}

Found a few simple fixes that could get your site loading faster.

It'll take you less than one minute to check it out.

Best,
{YOUR_NAME}"""
        
        whatsapp_msg = f"Hi {name}, your website is taking {load_display} to load - this is costing you about {visitor_loss}% of visitors. I did a quick audit and found some simple fixes. Want to see them? No pressure."
        
        return subject, email_body, whatsapp_msg
    
    subject = f"Quick observation about {name}"
    
    email_body = f"""Hello,

I was looking at {name} on Google Maps and noticed something about your website.

When I click your website on my phone, it takes {load_display} to load.

That doesn't sound like much, but it means about {visitor_loss}% of your mobile visitors are leaving before they even see your services.

I went ahead and did a quick audit of your business' online presence, no strings attached.

Here's what I found:
{audit_summary_text}

Found a few simple things that could help you get more calls from your website.

It'll take you less than one minute to check it out.

Best,
{YOUR_NAME}"""
    
    whatsapp_msg = f"""Hi {name}, I was looking at your business on Google Maps and noticed your website takes {load_display} to load on mobile.

That's costing you about {visitor_loss}% of visitors.

I did a quick audit of your online presence - no strings attached.

Found some simple ways to get more calls.

Want to see what I found? Just say yes and I'll send it over."""
    
    return subject, email_body, whatsapp_msg

# ============================================================
# WORKERS
# ============================================================
def save_worker():
    global revisit_lead_count
    print("Save worker started")
    
    while True:
        try:
            data = save_queue.get(timeout=1)
            if data is None:
                continue
            
            name = data.get("name", "Unknown")
            print(f"\n💾 SAVING: {name}")
            
            phone = sanitize_string(data.get("phone", ""))
            website = sanitize_string(data.get("website", ""))
            
            rating = data.get("rating")
            try:
                rating = float(rating) if rating else "N/A"
            except:
                rating = "N/A"
            
            review_count = 0
            try:
                review_count = int(data.get("review_count", 0))
            except:
                pass
            
            last_review_date = sanitize_string(data.get("last_review_date", "N/A"))
            phone_info = validate_phone(phone)
            
            record = {
                "name": name,
                "phone": phone_info["formatted"],
                "phone_valid": "Yes" if phone_info["valid_format"] else "No",
                "line_type": phone_info["line_type"],
                "website": website,
                "rating": rating,
                "review_count": review_count,
                "last_review_date": last_review_date,
                "perf_score": "N/A",
                "seo_score": "N/A",
                "https": "N/A",
                "mobile_friendly": "N/A",
                "load_time": "N/A",
                "load_category": "unknown",
                "conversion_score": 50,
                "design_score": 50,
                "cta_score": 50,
                "contact_score": 50,
                "trust_score": 50,
                "capture_score": 50,
                "priority": "MEDIUM",
                "friction": "",
                "clarity": "",
                "hierarchy": "",
                "recommendations": "",
                "screenshot_count": 0,
                "health_score": 50,
                "opportunity_score": 95 if not website else 50,
                "design_notes": "Processing audit...",
                "audit_status": "Pending",
                "revisit_attempts": 0,
                "email_subject": f"Quick observation about {name}",
                "email_body": f"Hello,\n\nI was looking at {name} on Google Maps and noticed something about your website.\n\nI went ahead and did a quick audit of your business' online presence, no strings attached.\n\nFound a few simple things that could help you get more calls from your website.\n\nIt'll take you less than one minute to check it out.\n\nBest,\n{YOUR_NAME}",
                "whatsapp_message": f"Hi {name}, I found your business on Google Maps and did a quick audit of your website. No strings attached. Want to see it?"
            }
            
            success = save_to_excel(record)
            
            if success:
                print(f"   ✅ Excel saved")
                all_leads_cache.append(record)
                build_dashboard()
                audit_queue.put(data)
                revisit_lead_count += 1
                print(f"   📊 Queued for audit (Audit queue: {audit_queue.qsize()})")
                
                if revisit_lead_count >= REVISIT_INTERVAL:
                    print(f"\n🔄 Revisit interval reached ({REVISIT_INTERVAL} leads). Processing revisit queue...")
                    revisit_lead_count = 0
                    process_revisit_queue()
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Save worker error: {e}")
            log_error(f"Save worker error: {e}")

def audit_worker(worker_id):
    print(f"Audit worker {worker_id} started")
    
    while True:
        try:
            data = audit_queue.get(timeout=2)
            if data is None:
                continue
            
            name = data.get("name", "Unknown")
            print(f"\n[Worker {worker_id}] Processing: {name}")
            
            audit_results = process_single_audit(data, worker_id, is_revisit=False)
            
            found = False
            for i, lead in enumerate(all_leads_cache):
                if lead["name"] == name:
                    all_leads_cache[i].update(audit_results)
                    save_to_excel(all_leads_cache[i])
                    build_dashboard()
                    print(f"[Worker {worker_id}] ✅ Updated: {name}")
                    found = True
                    break
            
            if not found:
                print(f"[Worker {worker_id}] ⚠️ Lead not found in cache: {name}")
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Audit worker {worker_id} error: {e}")
            log_error(f"Audit worker {worker_id} error: {e}")
            time.sleep(2)

def revisit_worker():
    print(f"🔄 Revisit worker started")
    
    while True:
        try:
            data = revisit_queue.get(timeout=5)
            if data is None:
                continue
            
            name = data.get("name", "Unknown")
            revisit_attempts = data.get("revisit_attempts", 0) + 1
            
            print(f"\n🔄 REVISIT {revisit_attempts}/{MAX_REVISIT_ATTEMPTS}: {name}")
            
            if revisit_attempts > MAX_REVISIT_ATTEMPTS:
                print(f"   ⏭️ Max attempts reached for {name}, marking as critical")
                for lead in all_leads_cache:
                    if lead["name"] == name:
                        lead["audit_status"] = "Critical"
                        lead["revisit_attempts"] = revisit_attempts
                        save_to_excel(lead)
                        build_dashboard()
                        break
                continue
            
            data["revisit_attempts"] = revisit_attempts
            
            audit_results = process_single_audit(data, 4, is_revisit=True)
            
            for i, lead in enumerate(all_leads_cache):
                if lead["name"] == name:
                    all_leads_cache[i].update(audit_results)
                    save_to_excel(all_leads_cache[i])
                    build_dashboard()
                    print(f"🔄 ✅ Revisit complete: {name}")
                    break
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Revisit worker error: {e}")
            log_error(f"Revisit worker error: {e}")
            time.sleep(2)

def process_revisit_queue():
    with revisit_lock:
        critical_leads = []
        for lead in all_leads_cache:
            if lead.get("audit_status") == "Pending" and lead.get("website"):
                if lead.get("perf_score") == "N/A" or lead.get("load_time") == "N/A":
                    critical_leads.append(lead)
            elif lead.get("audit_status") == "Critical" and lead.get("revisit_attempts", 0) < MAX_REVISIT_ATTEMPTS:
                critical_leads.append(lead)
        
        if not critical_leads:
            print("   No leads to revisit")
            return
        
        print(f"   Found {len(critical_leads)} leads to revisit")
        
        for lead in critical_leads:
            revisit_data = {
                "name": lead.get("name"),
                "website": lead.get("website"),
                "rating": lead.get("rating"),
                "review_count": lead.get("review_count"),
                "last_review_date": lead.get("last_review_date"),
                "revisit_attempts": lead.get("revisit_attempts", 0)
            }
            revisit_queue.put(revisit_data)
            print(f"   🔄 Queued: {lead.get('name')} (Attempt {lead.get('revisit_attempts', 0) + 1})")

# ============================================================
# FLASK ENDPOINTS
# ============================================================
@app.route('/api/lead', methods=['POST', 'OPTIONS'])
def receive_lead():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    
    try:
        data = request.json
        name = data.get('name', 'Unknown')
        print(f"\n📥 Received: {name}")
        
        for key in ['name', 'website', 'phone', 'niche', 'city', 'last_review_date']:
            if key in data:
                if isinstance(data[key], list):
                    data[key] = ' '.join(str(x) for x in data[key])
                elif data[key] is None:
                    data[key] = ""
        
        if name in processed_names:
            print(f"⏭️ Duplicate skipped")
            response = make_response(jsonify({"status": "duplicate"}))
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response, 200
        
        processed_names.add(name)
        save_queue.put(data)
        print(f"   📥 Queued for save (Save queue: {save_queue.qsize()})")
        
        response = make_response(jsonify({"status": "queued"}))
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, 200
        
    except Exception as e:
        print(f"Receive error: {e}")
        response = make_response(jsonify({"status": "error", "message": str(e)}))
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "save_queue": save_queue.qsize(),
        "audit_queue": audit_queue.qsize(),
        "revisit_queue": revisit_queue.qsize(),
        "leads_processed": len(all_leads_cache),
        "unique_leads": len(processed_names),
        "revisit_interval": REVISIT_INTERVAL,
        "workers": NUM_WORKERS,
        "revisit_workers": NUM_REVISIT_WORKERS,
        "playwright_available": HAS_PLAYWRIGHT,
        "gemini_configured": bool(GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE")
    })

@app.route('/api/revisit', methods=['POST'])
def trigger_revisit():
    process_revisit_queue()
    return jsonify({"status": "revisit_triggered", "queue_size": revisit_queue.qsize()})

@app.route('/api/debug', methods=['GET'])
def debug():
    return jsonify({
        "save_queue": save_queue.qsize(),
        "audit_queue": audit_queue.qsize(),
        "revisit_queue": revisit_queue.qsize(),
        "leads_processed": len(all_leads_cache),
        "unique_leads": len(processed_names),
        "cache_sample": all_leads_cache[:3] if all_leads_cache else []
    })

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("FOOTPRINT AUDIT SYSTEM - SSL BYPASS VERSION")
    print("=" * 70)
    print(f"Excel: {OUTPUT_EXCEL}")
    print(f"Dashboard: {DASHBOARD_FILE}")
    print(f"Screenshots: {SCREENSHOTS_DIR}/")
    print("=" * 70)
    print()
    
    print("SYSTEM STATUS:")
    print(f"   Flask: Ready")
    print(f"   OpenPyXL: Ready")
    print(f"   Playwright: {'✅ Available' if HAS_PLAYWRIGHT else '❌ Not installed'}")
    print(f"   Phone Validation: {'✅ Available' if HAS_PHONENUMBERS else '❌ Not installed'}")
    print(f"   Gemini: {'✅ Configured' if GEMINI_API_KEY and GEMINI_API_KEY != 'YOUR_GEMINI_API_KEY_HERE' else '❌ Not configured'}")
    print(f"   Gemini Model: {GEMINI_MODEL}")
    print(f"   SSL Bypass: ✅ Active")
    print(f"   Chrome: {'✅ Found' if CHROME_PATH else '❌ Not found'}")
    print(f"   Workers: {NUM_WORKERS} audit + {NUM_REVISIT_WORKERS} revisit")
    print(f"   Revisit Interval: Every {REVISIT_INTERVAL} leads")
    print(f"   Max Revisit Attempts: {MAX_REVISIT_ATTEMPTS}")
    print("=" * 70)
    print()
    print("SCREENSHOT SETTINGS:")
    print(f"   Viewport Height: {VIEWPORT_HEIGHT}px")
    print(f"   Max Screenshots per Page: {MAX_SCREENSHOTS}")
    print(f"   Screenshot Overlap: {SCREENSHOT_OVERLAP}px")
    print("=" * 70)
    print()
    print("LOAD TIME THRESHOLDS (Option B):")
    print(f"   ⚡ Fast: < {LOAD_FAST}s")
    print(f"   📊 Average: {LOAD_FAST}-{LOAD_AVERAGE}s")
    print(f"   ⚠️ Slow: {LOAD_AVERAGE}-{LOAD_SLOW}s")
    print(f"   ⚠️ Very Slow: {LOAD_SLOW}-{LOAD_VERY_SLOW}s")
    print(f"   🚨 Critical: ≥ {LOAD_CRITICAL}s")
    print("=" * 70)
    print()
    print("GEMINI ANALYSIS:")
    print("   • SSL bypass active for all HTTPS connections")
    print("   • Full system prompt with business context")
    print("   • Section-specific analysis")
    print("   • Per-section scores: Design, CTA, Contact, Trust, Capture")
    print("   • Overall conversion score + priority + recommendations")
    print("=" * 70)
    print()
    
    init_excel()
    build_dashboard()
    
    save_thread = threading.Thread(target=save_worker, daemon=False)
    save_thread.start()
    print("✅ Save worker started")
    
    for i in range(NUM_WORKERS):
        thread = threading.Thread(target=audit_worker, args=(i+1,), daemon=False)
        thread.start()
        print(f"✅ Audit worker {i+1} started")
    
    revisit_thread = threading.Thread(target=revisit_worker, daemon=False)
    revisit_thread.start()
    print(f"✅ Revisit worker started")
    
    print()
    print("Starting Flask server...")
    print("   Server: http://127.0.0.1:5000")
    print("   Dashboard: open index.html")
    print("   Trigger revisit manually: POST /api/revisit")
    print("=" * 70)
    print()
    
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)