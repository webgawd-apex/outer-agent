"""
run_pipeline.py
======================================================
MASTER PIPELINE — Run this after the Chrome extension
has scraped leads into the Excel file.

What it does, automatically:
  1. Reads the Excel file (footprint_audited_leads_*.xlsx)
  2. Filters leads: no website OR low reviews
  3. Tries to find their email
  4. Builds a custom HTML demo website
  5. Converts it to a PDF screenshot
  6. Sends the PDF via email (SendGrid)
  7. Logs everything to SQLite CRM
  8. Starts a follow-up daemon in the background

Usage:
  python run_pipeline.py
  python run_pipeline.py --excel "footprint_audited_leads_20260903_1655.xlsx"
  python run_pipeline.py --dry-run   (build sites + PDFs, skip sending)
"""

import os
import sys
import glob
import time
import argparse
import datetime

# ── Pipeline config ────────────────────────────────────────────────────────────
MAX_REVIEW_COUNT    = 25      # Filter: businesses with fewer than this many reviews
MIN_OPPORTUNITY     = 60      # Filter: only process leads with score >= this
EMAIL_DELAY_SECONDS = 8       # Pause between sends (avoid spam flags)
SKIP_IF_HAS_WEBSITE = False   # Set True to skip businesses that DO have a website

def find_excel_file(override: str = None) -> str:
    """Find the most recently created Excel lead file."""
    if override and os.path.exists(override):
        return override
    files = sorted(glob.glob("footprint_audited_leads_*.xlsx"), reverse=True)
    if not files:
        print("[pipeline] ERROR: No footprint_audited_leads_*.xlsx file found.")
        print("           Run the Chrome extension scraper first.")
        sys.exit(1)
    chosen = files[0]
    print(f"[pipeline] Using Excel file: {chosen}")
    return chosen

def load_leads_from_excel(excel_path: str) -> list[dict]:
    """Read the Excel file and return a list of lead dicts."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("[pipeline] ERROR: openpyxl not installed. Run: pip install openpyxl")
        sys.exit(1)

    wb   = load_workbook(excel_path)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if not rows:
        print("[pipeline] Excel file is empty.")
        return []

    # Header row
    headers = [str(h).strip().lower().replace(" ", "_") if h else f"col_{i}"
               for i, h in enumerate(rows[0])]

    leads = []
    for row in rows[1:]:
        if not any(row):
            continue
        lead = dict(zip(headers, row))
        leads.append(lead)

    print(f"[pipeline] Loaded {len(leads)} leads from Excel")
    return leads

def qualify_lead(lead: dict) -> bool:
    """
    Return True if this lead should be processed.
    Priority:
      - No website         → ALWAYS process
      - Low reviews        → process if review_count < MAX_REVIEW_COUNT
    """
    website      = str(lead.get("website") or "").strip()
    review_count = lead.get("review_count") or lead.get("review_count", 0)
    opp_score    = lead.get("opportunity_score") or 50

    try:
        review_count = int(str(review_count).replace(",", ""))
    except (ValueError, TypeError):
        review_count = 0

    try:
        opp_score = int(float(str(opp_score)))
    except (ValueError, TypeError):
        opp_score = 50

    if SKIP_IF_HAS_WEBSITE and website:
        return False

    if not website:
        return True  # No website — top priority

    if review_count < MAX_REVIEW_COUNT:
        return True

    if opp_score >= MIN_OPPORTUNITY:
        return True

    return False

def normalise_lead(raw: dict) -> dict:
    """Normalise Excel column names to pipeline-standard keys."""
    # Map possible Excel column names → standard keys
    mapping = {
        "business_name": "name",
        "businessname":  "name",
        "phone_number":  "phone",
        "review_count":  "review_count",
        "reviewcount":   "review_count",
        "last_review_date": "last_review_date",
        "opportunity_score": "opportunity_score",
        "email_subject": "email_subject",
        "email_body":    "email_body",
        "whatsapp_message": "whatsapp_message",
    }

    normalised = {}
    for k, v in raw.items():
        std_key = mapping.get(k, k)
        normalised[std_key] = v

    # Default niche/city from first two words of name if not set
    if not normalised.get("niche"):
        normalised["niche"] = "Local Business"
    if not normalised.get("city"):
        normalised["city"] = "USA"

    return normalised

def run_pipeline(excel_path: str, dry_run: bool = False):
    # ── imports ────────────────────────────────────────────────────────────────
    from website_builder import build_website
    from screenshot_pdf  import screenshot_to_pdf
    from email_finder    import find_email
    from email_sender    import send_outreach_email
    from followup_crm    import init_db, upsert_lead, mark_emailed, print_pipeline, start_followup_daemon

    # ── init ───────────────────────────────────────────────────────────────────
    init_db()
    print("\n" + "=" * 60)
    print("  MAPS AUDITOR → WEBSITE BUILDER → OUTREACH ENGINE")
    print("=" * 60)
    print(f"  Mode:       {'DRY RUN (no emails)' if dry_run else 'LIVE'}")
    print(f"  Excel:      {excel_path}")
    print(f"  Max reviews: {MAX_REVIEW_COUNT}  |  Min score: {MIN_OPPORTUNITY}")
    print("=" * 60 + "\n")

    # ── load + filter ──────────────────────────────────────────────────────────
    raw_leads  = load_leads_from_excel(excel_path)
    all_leads  = [normalise_lead(r) for r in raw_leads]
    qualified  = [l for l in all_leads if qualify_lead(l)]

    print(f"[pipeline] {len(all_leads)} total leads | {len(qualified)} qualified\n")

    stats = {"built": 0, "emailed": 0, "no_email": 0, "failed": 0}

    for i, lead in enumerate(qualified, 1):
        name = lead.get("name", "Unknown")
        print(f"\n[{i}/{len(qualified)}] Processing: {name}")
        print(f"  Website:  {lead.get('website') or 'NONE'}")
        print(f"  Reviews:  {lead.get('review_count', 0)}  |  Rating: {lead.get('rating', 'N/A')}")

        # ── Step 1: Save to CRM ────────────────────────────────────────────────
        lead_id = upsert_lead(lead)

        # ── Step 2: Find email ─────────────────────────────────────────────────
        email = find_email(lead.get("website", ""), name)
        if email:
            lead["email"] = email
            print(f"  Email:    {email}")
        else:
            print(f"  Email:    NOT FOUND — skipping email (will use WhatsApp)")
            stats["no_email"] += 1
            # Still build the site even without an email
            html_path = build_website(lead)
            stats["built"] += 1
            continue

        # ── Step 3: Build website ──────────────────────────────────────────────
        print(f"  Building demo site...")
        html_path = build_website(lead)
        stats["built"] += 1

        # ── Step 4: Screenshot → PDF ───────────────────────────────────────────
        print(f"  Generating PDF...")
        pdf_path = screenshot_to_pdf(html_path)
        if not pdf_path:
            print(f"  [WARN] PDF failed — will send email without attachment")

        # ── Step 5: Send email ─────────────────────────────────────────────────
        if dry_run:
            print(f"  [DRY RUN] Would send to {email} with PDF: {pdf_path}")
            continue

        print(f"  Sending email to {email}...")
        result = send_outreach_email(lead, email, pdf_path=pdf_path)

        if result["success"]:
            mark_emailed(lead_id, email, html_path=html_path, pdf_path=pdf_path or "")
            stats["emailed"] += 1
            print(f"  [OK] Email sent!")
        else:
            stats["failed"] += 1
            print(f"  [FAIL] {result['message']}")

        # Polite delay between sends
        if i < len(qualified):
            print(f"  Waiting {EMAIL_DELAY_SECONDS}s before next send...")
            time.sleep(EMAIL_DELAY_SECONDS)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Sites built:     {stats['built']}")
    print(f"  Emails sent:     {stats['emailed']}")
    print(f"  No email found:  {stats['no_email']}")
    print(f"  Failed:          {stats['failed']}")
    print("=" * 60)
    print_pipeline()

    # ── Start follow-up daemon ─────────────────────────────────────────────────
    if not dry_run and stats["emailed"] > 0:
        print(f"[pipeline] Starting follow-up daemon (checks every {FOLLOW_UP_INTERVAL}s)...")
        start_followup_daemon()
        print("[pipeline] Daemon running. Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(60)
                print_pipeline()
        except KeyboardInterrupt:
            print("\n[pipeline] Stopped.")

FOLLOW_UP_INTERVAL = 300  # re-export for daemon

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maps Auditor → Outreach Pipeline")
    parser.add_argument("--excel",   type=str, default=None, help="Path to the Excel leads file")
    parser.add_argument("--dry-run", action="store_true",    help="Build sites + PDFs but don't send emails")
    args = parser.parse_args()

    excel = find_excel_file(args.excel)
    run_pipeline(excel, dry_run=args.dry_run)
