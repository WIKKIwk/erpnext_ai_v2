```
███████╗██████╗ ██████╗ ███╗   ██╗███████╗██╗  ██╗████████╗     █████╗ ██╗
██╔════╝██╔══██╗██╔══██╗████╗  ██║██╔════╝╚██╗██╔╝╚══██╔══╝    ██╔══██╗██║
█████╗  ██████╔╝██████╔╝██╔██╗ ██║█████╗   ╚███╔╝    ██║       ███████║██║
██╔══╝  ██╔══██╗██╔═══╝ ██║╚██╗██║██╔══╝   ██╔██╗    ██║       ██╔══██║██║
███████╗██║  ██║██║     ██║ ╚████║███████╗██╔╝ ██╗   ██║       ██║  ██║██║
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝   ╚═╝       ╚═╝  ╚═╝╚═╝
```

# ERPNEXT AI :: ADMIN COPILOT + ITEM OPS

```
PROJECT: ERPNext AI
AUTHOR: Abdulfattox Qurbonov
LICENSE: MIT
VERSION: 1.0.0
PLATFORM: Frappe Framework + ERPNext (bench)
RUNTIME: Python 3.10+ | Node.js 18+ (per ERPNext)
```

---

## SYSTEM OVERVIEW

```
ERPNext AI is a desk-native assistant for ERPNext administrators.
It combines an AI chat interface, a command center dashboard, and
bulk item tooling to speed up routine operations.

CRITICAL: ERPNext is required. Frappe-only installs are not supported.
```

---

## CAPABILITY MATRIX

```
CORE CONSOLE
├── AI Chat workspace with ERP context injection
├── AI Command Center metrics dashboard
├── AI Report generation (AI Report DocType)
├── AI Item Creator (preview + bulk create)
└── Conversation history stored in ERPNext

CONTEXT & REPORTING
├── Sales/Purchase totals and volumes
├── Delivery notes + open support tickets
├── Cash/bank + receivables/payables snapshot
├── Inventory snapshot + top stock items
├── Task + HR overview
└── Recent records (users, customers, items, invoices)

ITEM OPERATIONS
├── Preview-first item creation (max 200 items)
├── Optional AI parsing for messy lists
├── Series generator (prefix + numbering)
├── Create as Disabled option
├── Update limited to safe fields
└── Delete/update only for AI-created items

TELEGRAM SALES BOT (OPTIONAL)
├── Group-based /report and /order workflows
├── Sales manager assignment flow
├── Encrypted API credentials storage
└── SQLite-backed bot state

SECURITY & ACCESS
├── Role-based access (System Manager / AI Manager)
├── API keys stored in Password fields or env vars
├── Item operations respect ERPNext permissions
└── AI-created items flagged via erpnext_ai_created
```

---

## TECHNICAL REQUIREMENTS

```
MANDATORY
├── ERPNext bench (Frappe + ERPNext)
└── Python deps: openai, requests, python-telegram-bot, cryptography

OPTIONAL
└── Telegram bot env vars (if enabled)
```

---

## DEPLOYMENT PROTOCOLS

### [PROTOCOL 1] BENCH INSTALLATION

```bash
cd /path/to/your/bench
bench get-app https://github.com/WIKKIwk/erpnext_ai.git
bench --site your-site-name install-app erpnext_ai
bench --site your-site-name migrate
bench build
```

### [PROTOCOL 2] MANUAL INSTALLATION

```bash
cd /path/to/your/bench/apps
git clone https://github.com/WIKKIwk/erpnext_ai.git
cd erpnext_ai
pip install -e .

cd ../..
bench --site your-site-name install-app erpnext_ai
bench --site your-site-name migrate
```

### [PROTOCOL 3] OPTIONAL FULL BENCH PROVISIONING (UBUNTU 22.04/24.04)

```bash
# From repository root (or use the raw URL)
./install_erpnext.sh
```

**ENVIRONMENT OVERRIDES (SCRIPT):**
```
TARGET_USER=frappe
BENCH_NAME=frappe-bench
SITE_NAME=erp.localhost
FRAPPE_BRANCH=version-15
ERPNEXT_BRANCH=version-15
SITE_ADMIN_PASSWORD=Admin@123
```

---

## CONFIGURATION MATRIX

### [CONFIG 1] ROLE ASSIGNMENT

```
Roles:
├── System Manager ............. Full access
└── AI Manager ................. Read access to AI features

Procedure:
1) Desk → Users and Permissions → Role Permissions Manager
2) Assign "AI Manager" to designated users
```

### [CONFIG 2] AI SETTINGS

```
Path: Desk → Chatting with AI → AI Settings

Fields:
├── Provider ............... OpenAI | Gemini
├── Model .................. OpenAI: gpt-4o, gpt-4o-mini, gpt-5, gpt-5-mini
│                            Gemini: gemini-2.5-flash
├── Run As User ............ Context collection user (default: Administrator)
├── OpenAI API Key ......... Optional (Password field)
├── Gemini API Key .......... Optional (Password field)
└── Allow AI Item Creation . Enables AI item operations
```

**API KEY RESOLUTION ORDER**
```
OpenAI:  OPENAI_API_KEY env -> frappe.conf.openai_api_key -> AI Settings field
Gemini:  GEMINI_API_KEY / GOOGLE_API_KEY env -> frappe.conf.gemini_api_key
         / frappe.conf.google_api_key -> AI Settings field
```

### [CONFIG 3] ITEM OPS SAFEGUARD

```
Custom Field:
Item.erpnext_ai_created (Check)

Notes:
- Added via migrate/patch.
- Update/delete operations are limited to AI-created items.
- Item permissions still apply.
```

### [CONFIG 4] SCHEDULER

```
Task: erpnext_ai.tasks.generate_daily_admin_summary
Frequency: daily (hooks.py)
Output: Comment on AI Settings + realtime event (erpnext_ai_daily_summary)

Manual trigger:
bench --site your-site-name execute erpnext_ai.tasks.generate_daily_admin_summary
```

---

## OPERATIONAL PROCEDURES

### AI COMMAND CENTER

```
Access:
- Page route: /app/ai-command-center

Actions:
- Refresh Metrics -> pulls ERPNext context
- Generate Summary -> creates an AI Report record

Output:
- AI Report DocType with prompt, context JSON, and AI output
```

### AI CHAT

```
Access:
Desk → Chatting with AI → AI Chat

Core Behavior:
- Stores conversations in AI Conversation / AI Message.
- Injects ERP context when enabled.
- Supports item create/update/delete via action blocks.

Action Blocks:
- Use fenced code block: ```erpnext_ai_action
- Set "auto_apply": 1 for immediate execution (UI default).
```

### AI ITEM CREATOR

```
Access:
Desk → Chatting with AI → AI Item Creator

Workflow:
- Preview items first
- Optional AI parsing of messy lists
- Create as Disabled option (default on the page)
```

---

## ACTION BLOCK PROTOCOL (AI CHAT)

```erpnext_ai_action
{"action":"preview_item_creation","item_group":"Raw Material","stock_uom":"Nos","raw_text":"PL_1 - PLYONKA_1\nPL_2 - PLYONKA_2","create_disabled":1,"auto_apply":1}
```

```erpnext_ai_action
{"action":"preview_item_creation_series","item_group":"Raw Material","stock_uom":"Nos","name_prefix":"plyonka_","code_prefix":"pl_","start":1,"count":20,"pad":0,"create_disabled":1,"auto_apply":1}
```

```erpnext_ai_action
{"action":"preview_item_deletion_series","code_prefix":"pl_","start":1,"count":20,"pad":0,"auto_apply":1}
```

```erpnext_ai_action
{"action":"preview_item_update_series","code_prefix":"pl_","start":1,"count":20,"pad":0,"updates":{"item_group":"Raw Material","stock_uom":"Nos","disabled":0},"auto_apply":1}
```

**Allowed update fields:** `item_name`, `item_group`, `stock_uom`, `disabled`, `description`

---

## TELEGRAM BOT DEPLOYMENT (OPTIONAL)

### REQUIRED ENVIRONMENT VARIABLES

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_IDS=123456789,987654321
FRAPPE_BASE_URL=https://your-erp-domain.com
```

### OPTIONAL OVERRIDES

```
BOT_ENCRYPTION_KEY=base64-32-byte-key
TELEGRAM_BOT_DB_PATH=/var/lib/erpnext_ai/telegram_bot.sqlite3
ERP_REQUEST_TIMEOUT=10

TELEGRAM_REPORT_RESOURCE=Sales Order
TELEGRAM_REPORT_FIELDS=["name","customer_name","transaction_date","grand_total","per_delivered"]
TELEGRAM_REPORT_LIMIT=5
TELEGRAM_REPORT_ORDER_BY=transaction_date desc

TELEGRAM_ORDER_TARGET_DOCTYPE=Lead
TELEGRAM_ORDER_SOURCE=Telegram Bot
TELEGRAM_ORDER_TERRITORY=
TELEGRAM_ORDER_STATUS=Lead
TELEGRAM_ORDER_ATTACH_PHOTO=true
TELEGRAM_BOT_NAME=sales_bot
FRAPPE_VERIFICATION_ENDPOINT=/api/method/frappe.auth.get_logged_user
```

### BOT STARTUP

```bash
# Inside bench venv
python -m erpnext_ai.erpnext_ai.telegram.bot

# Or via bench
bench --site your-site-name execute erpnext_ai.erpnext_ai.telegram.bot.main
```

### COMMANDS

```
/start
/help
/add_master_manager <telegram_id>
/remove_master_manager <telegram_id>
/list_master_managers
/users
/set_api <api_key> <api_secret>
/report
/order
/whoami
/cancel
/skip
```

---

## DATA MODEL

```
AI Settings (Single)
├── api_provider (Select) ....... OpenAI | Gemini
├── openai_model (Select) ....... Provider-specific model list
├── service_user (Link) ......... Run-as User
├── openai_api_key (Password) ... Optional override
├── gemini_api_key (Password) ... Optional override
└── allow_item_creation (Check) . Feature flag

AI Report
├── title (Data)
├── report_type (Select) ........ Summary | Custom Prompt | Trend
├── generated_on (Datetime)
├── status (Select) ............. Draft | Running | Success | Failed
├── model_used (Data)
├── error_message (Small Text)
├── prompt (Code)
├── context_json (Code)
└── ai_output (Text Editor)

AI Conversation
├── title (Data)
├── user (Link)
├── status (Select) ............. Open | Closed
├── include_context (Check)
├── last_interaction (Datetime)
├── system_prompt (Code)
└── messages (Table → AI Message)

AI Message (Child)
├── role (Select) ............... system | user | assistant
├── content (Text Editor)
├── context_json (Code)
└── token_usage (Int)

Item (Custom Field)
└── erpnext_ai_created (Check) .. AI created flag
```

---

## DIAGNOSTIC PROCEDURES

### ISSUE: AI FEATURES UNRESPONSIVE

```
[1] Verify AI Settings API key
    Desk → Chatting with AI → AI Settings

[2] Verify model/provider selection
    OpenAI: gpt-4o, gpt-4o-mini, gpt-5, gpt-5-mini
    Gemini: gemini-2.5-flash

[3] Test report generation
    bench --site your-site-name execute erpnext_ai.api.generate_admin_summary
```

### ISSUE: ITEM OPS BLOCKED

```
[1] Enable "Allow AI Item Creation" in AI Settings
[2] Ensure user has Item create/write/delete permissions
[3] Run migrate to add Item.erpnext_ai_created
```

### ISSUE: TELEGRAM BOT NON-RESPONSIVE

```
[1] Verify TELEGRAM_BOT_TOKEN and FRAPPE_BASE_URL
[2] Check bot process logs
[3] Ensure TELEGRAM_ADMIN_IDS contains your Telegram ID
```

---

## LICENSE TERMS

```
MIT License

Copyright (c) 2024 Abdulfattox Qurbonov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

```
PROJECT: ERPNext AI
VERSION: 1.0.0
LAST_UPDATED: 2025-12-25
MAINTAINER: Abdulfattox Qurbonov
STATUS: PRODUCTION_READY
```

**END DOCUMENTATION**
