# MapsAuditor & Outer Agent 🚀

Autonomous Lead Outreach & Contact Automation Engine.

## Overview
MapsAuditor Engine automates contractor and business outreach across Google Maps, local directories, contact forms, and email channels.

### Features
- **Autonomous Agent**: Scrapes and analyzes business opportunities.
- **Form Submitter**: Playwright-based contact form detection, filling, and submission with fallback handling.
- **Email Finder & Sender**: Pattern-based email discovery and automated personalized outreach via Gmail/SendGrid.
- **Follow-up CRM**: SQLite tracking of leads, pipeline stages, touchpoints, and scheduled follow-ups.
- **Reply Checker**: Automated monitoring for incoming lead responses.
- **Bridge Server & Webhook Notifiers**: Real-time Discord & Telegram alerting for CAPTCHAs, lead replies, and errors.
- **Chrome Extension**: In-browser scraper and auditor tool for manual workflows.

---

## Quick Start

### 1. Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configuration
Copy the sample environment and settings files:
```bash
cp .env.example .env
cp settings.example.json settings.json
```
Edit `.env` and `settings.json` with your API keys and sender info.

### 3. Run Pipeline
```bash
python run_pipeline.py
```
Or start the background server:
```bash
python server_runner.py
```

---

## Deployment
Includes a `Dockerfile` and `render.yaml` ready for one-click deployment to Render or any container hosting platform.
