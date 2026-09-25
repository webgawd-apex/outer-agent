"""
followup_crm.py
SQLite-based CRM for lead tracking + automated follow-up scheduling.
Runs as a background daemon alongside the bridge server.

Lead states:
  new → emailed → follow_up_sent → responded → closed / not_interested
"""

import os
import sqlite3
import datetime
import threading
import time

DB_PATH              = "leads.db"
FOLLOW_UP_DAYS       = 3    # Days after first email before sending follow-up
FOLLOW_UP_INTERVAL   = 300  # How often the daemon checks for due follow-ups (seconds)

# ── DB Setup ──────────────────────────────────────────────────────────────────
def init_db(db_path: str = DB_PATH):
    """Create the database and tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        phone           TEXT,
        email           TEXT,
        website         TEXT,
        niche           TEXT,
        city            TEXT,
        rating          REAL,
        review_count    INTEGER DEFAULT 0,
        opportunity_score INTEGER DEFAULT 50,
        status          TEXT DEFAULT 'new',
        -- Outreach
        html_path       TEXT,
        pdf_path        TEXT,
        outreach_email  TEXT,
        -- Timestamps
        scraped_at      TEXT DEFAULT (datetime('now')),
        emailed_at      TEXT,
        follow_up_at    TEXT,
        follow_up_sent_at TEXT,
        responded_at    TEXT,
        closed_at       TEXT,
        notes           TEXT
    );

    CREATE TABLE IF NOT EXISTS outreach_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id     INTEGER NOT NULL,
        type        TEXT NOT NULL,   -- 'first_email' | 'follow_up' | 'whatsapp'
        to_address  TEXT,
        subject     TEXT,
        status      TEXT,            -- 'sent' | 'failed' | 'bounced'
        sendgrid_id TEXT,
        sent_at     TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    );

    CREATE INDEX IF NOT EXISTS idx_leads_status   ON leads (status);
    CREATE INDEX IF NOT EXISTS idx_leads_niche    ON leads (niche);
    CREATE INDEX IF NOT EXISTS idx_leads_name     ON leads (name);
    """)

    conn.commit()
    conn.close()
    print(f"[CRM] Database ready: {db_path}")

# ── Lead CRUD ─────────────────────────────────────────────────────────────────
def upsert_lead(lead: dict, db_path: str = DB_PATH) -> int:
    """
    Insert a new lead or update if the name+city combo already exists.
    Returns the lead ID.
    """
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.execute(
        "SELECT id, status FROM leads WHERE name = ? AND city = ?",
        (lead.get("name", ""), lead.get("city", ""))
    )
    existing = cur.fetchone()

    if existing:
        lead_id, status = existing
        # Only update if still in early stages
        if status in ("new",):
            cur.execute("""
                UPDATE leads SET
                    phone=?, email=?, website=?, niche=?, rating=?,
                    review_count=?, opportunity_score=?
                WHERE id=?
            """, (
                lead.get("phone"),
                lead.get("email"),
                lead.get("website"),
                lead.get("niche"),
                lead.get("rating"),
                lead.get("review_count", 0),
                lead.get("opportunity_score", 50),
                lead_id,
            ))
        conn.commit()
        conn.close()
        return lead_id

    cur.execute("""
        INSERT INTO leads
            (name, phone, email, website, niche, city, rating, review_count, opportunity_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead.get("name"),
        lead.get("phone"),
        lead.get("email"),
        lead.get("website"),
        lead.get("niche"),
        lead.get("city"),
        lead.get("rating"),
        lead.get("review_count", 0),
        lead.get("opportunity_score", 50),
    ))
    lead_id = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[CRM] New lead saved: {lead.get('name')} (id={lead_id})")
    return lead_id

def mark_emailed(lead_id: int, email_address: str, html_path: str = "", pdf_path: str = "", db_path: str = DB_PATH):
    """Mark a lead as emailed and schedule a follow-up."""
    follow_up_at = (datetime.datetime.utcnow() + datetime.timedelta(days=FOLLOW_UP_DAYS)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE leads SET
            status='emailed', outreach_email=?, html_path=?, pdf_path=?,
            emailed_at=datetime('now'), follow_up_at=?
        WHERE id=?
    """, (email_address, html_path, pdf_path, follow_up_at, lead_id))
    conn.execute("""
        INSERT INTO outreach_log (lead_id, type, to_address, status)
        VALUES (?, 'first_email', ?, 'sent')
    """, (lead_id, email_address))
    conn.commit()
    conn.close()
    print(f"[CRM] Lead {lead_id} marked emailed. Follow-up scheduled: {follow_up_at}")

def mark_follow_up_sent(lead_id: int, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE leads SET status='follow_up_sent', follow_up_sent_at=datetime('now')
        WHERE id=?
    """, (lead_id,))
    conn.execute("""
        INSERT INTO outreach_log (lead_id, type, status)
        VALUES (?, 'follow_up', 'sent')
    """, (lead_id,))
    conn.commit()
    conn.close()

def mark_responded(lead_id: int, notes: str = "", db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE leads SET status='responded', responded_at=datetime('now'), notes=?
        WHERE id=?
    """, (notes, lead_id))
    conn.commit()
    conn.close()
    print(f"[CRM] Lead {lead_id} marked as RESPONDED!")

def mark_closed(lead_id: int, notes: str = "", db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE leads SET status='closed', closed_at=datetime('now'), notes=?
        WHERE id=?
    """, (notes, lead_id))
    conn.commit()
    conn.close()

def get_leads_for_pipeline(db_path: str = DB_PATH) -> list[dict]:
    """Return all 'new' leads that have an email and haven't been contacted yet."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM leads
        WHERE status = 'new' AND email IS NOT NULL AND email != ''
        ORDER BY opportunity_score DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_due_follow_ups(db_path: str = DB_PATH) -> list[dict]:
    """Return leads where follow-up is due and not yet sent."""
    now = datetime.datetime.utcnow().isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM leads
        WHERE status = 'emailed'
          AND follow_up_at IS NOT NULL
          AND follow_up_at <= ?
        ORDER BY follow_up_at ASC
    """, (now,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pipeline_summary(db_path: str = DB_PATH) -> dict:
    """Return a count of leads in each stage."""
    conn  = sqlite3.connect(db_path)
    rows  = conn.execute("SELECT status, COUNT(*) as cnt FROM leads GROUP BY status").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

# ── Follow-up daemon ──────────────────────────────────────────────────────────
def _follow_up_worker(db_path: str = DB_PATH):
    """
    Background thread that checks every FOLLOW_UP_INTERVAL seconds
    for leads that are due a follow-up and sends them.
    """
    # Import here to avoid circular deps
    from email_sender import send_outreach_email

    print(f"[CRM] Follow-up daemon started (checks every {FOLLOW_UP_INTERVAL}s)")

    while True:
        try:
            due = get_due_follow_ups(db_path)
            if due:
                print(f"[CRM] {len(due)} follow-up(s) due")
                for lead in due:
                    email = lead.get("outreach_email") or lead.get("email")
                    if not email:
                        continue

                    # Build follow-up version of the lead
                    follow_up_lead = dict(lead)
                    follow_up_lead["_is_followup"] = True

                    result = send_outreach_email(follow_up_lead, email, pdf_path=lead.get("pdf_path") or "")
                    if result["success"]:
                        mark_follow_up_sent(lead["id"], db_path)
                        print(f"[CRM] Follow-up sent: {lead['name']} -> {email}")
                    else:
                        print(f"[CRM] Follow-up FAILED: {lead['name']} | {result['message']}")
            else:
                print(f"[CRM] No follow-ups due at {datetime.datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            print(f"[CRM] Follow-up daemon error: {e}")

        time.sleep(FOLLOW_UP_INTERVAL)

def start_followup_daemon(db_path: str = DB_PATH) -> threading.Thread:
    """Start the follow-up daemon as a background thread. Returns the thread."""
    t = threading.Thread(target=_follow_up_worker, args=(db_path,), daemon=True)
    t.start()
    return t

# ── CLI utilities ─────────────────────────────────────────────────────────────
def print_pipeline(db_path: str = DB_PATH):
    summary = get_pipeline_summary(db_path)
    print("\n" + "=" * 50)
    print("  CRM PIPELINE SUMMARY")
    print("=" * 50)
    stages = ["new", "emailed", "follow_up_sent", "responded", "closed", "not_interested"]
    labels = {
        "new":            "New / Uncontacted",
        "emailed":        "Emailed (awaiting reply)",
        "follow_up_sent": "Follow-up Sent",
        "responded":      "Responded",
        "closed":         "Closed (Won)",
        "not_interested": "Not Interested",
    }
    for stage in stages:
        count = summary.get(stage, 0)
        bar   = "█" * min(count, 40)
        print(f"  {labels.get(stage, stage):<28} {bar} {count}")
    print("=" * 50 + "\n")


class CRM:
    """Object-oriented wrapper for SQLite CRM."""
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def save_lead(self, lead: dict) -> int:
        return upsert_lead(lead, self.db_path)

    def get_lead_by_name(self, name: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM leads WHERE name = ?", (name,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_lead_status(self, lead_id: int, status: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        conn.commit()
        conn.close()

    def record_outreach(self, lead_id: int, outreach_type: str, details: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO outreach_log (lead_id, type, to_address, subject, status)
            VALUES (?, ?, ?, ?, 'sent')
        """, (lead_id, outreach_type, details.get("to", ""), details.get("subject", "")))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    init_db()
    print_pipeline()

    # Optionally start daemon for testing
    import sys
    if "--daemon" in sys.argv:
        print("[CRM] Starting follow-up daemon (Ctrl+C to stop)...")
        start_followup_daemon()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[CRM] Daemon stopped.")
