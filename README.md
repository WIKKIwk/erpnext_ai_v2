# ERPNext AI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Frappe](https://img.shields.io/badge/frappe-v15-orange.svg)](https://github.com/frappe/frappe)
[![ERPNext](https://img.shields.io/badge/erpnext-v15-green.svg)](https://github.com/frappe/erpnext)

AI assistant and reporting for ERPNext admins. The app adds a role-aware AI Command Center that summarises ERPNext activity and can generate OpenAI powered executive briefs.

## 🌟 Features

- 🤖 **AI Assistant** - OpenAI GPT-4/GPT-5 powered assistant for ERPNext
- 📊 **Daily Admin Summary** - Automated daily executive reports with scheduler
- 💬 **AI Chat** - Interactive conversations grounded in ERPNext context
- 📱 **Telegram Bot** - Sales team integration with order management
- 🔐 **Secure** - Encrypted credentials and secure API key storage
- 🎯 **Role-based Access** - AI Manager role for controlled access
- 📝 **Audit Trail** - All conversations and reports are logged

## 📋 Requirements

- **Frappe**: v15.x
- **ERPNext**: v15.x (**REQUIRED** - this app depends on ERPNext)
- **Python**: 3.10 or higher
- **Node.js**: 18.x or higher
- **OpenAI API Key**: For AI features

**Note:** This app requires ERPNext to be installed. It will not work with Frappe-only installations.

## 📦 Installation

### Method 1: Using bench (Recommended)

```bash
# Navigate to your bench directory
cd /path/to/your/bench

# Get the app from GitHub (run after installing frappe/erpnext core apps)
bench get-app https://github.com/WIKKIwk/erpnext_ai.git

# Install the app on your site
bench --site your-site-name install-app erpnext_ai

# Migrate and build
bench --site your-site-name migrate
bench build
```

### Method 2: Manual installation

```bash
# Clone the repository
cd apps
git clone https://github.com/WIKKIwk/erpnext_ai.git

# Install dependencies
cd erpnext_ai
pip install -e .

# Install the app on your site
cd ../..
bench --site your-site-name install-app erpnext_ai
```

### Method 3: Provision a Fresh Bench on Ubuntu

If you need a brand-new ERPNext environment, this repository ships with `install_erpnext.sh`. It installs all dependencies on Ubuntu 22.04/24.04, sets up Bench, creates a site, and installs ERPNext.

```bash
curl -fsSL https://raw.githubusercontent.com/WIKKIwk/erpnext_ai/master/install_erpnext.sh | sudo bash
```

Environment variables such as `TARGET_USER`, `BENCH_NAME`, `SITE_NAME`, `FRAPPE_BRANCH`, `ERPNEXT_BRANCH`, and `SITE_ADMIN_PASSWORD` can be exported before running the script to customise the installation.

## ⚙️ Configuration

### 1. Assign Roles

Assign the new **AI Manager** role to users who should access AI reports. System Managers retain full access automatically.

### 2. Configure OpenAI API Key

**Recommended:** Add to bench-level `.env` file:

```bash
# In your bench directory, edit or create .env file
OPENAI_API_KEY=sk-your-api-key-here
```

**Alternative:** Configure via UI in **AI Settings** (`Desk → Build → Chatting with AI → AI Settings`)

### 3. Configure AI Settings

Navigate to **AI Settings** and configure:

- **Provider**: OpenAI (default)
- **Model**: Choose from:
  - `gpt-4o` - Most capable (recommended for production)
  - `gpt-4o-mini` - Cost-effective option
  - `gpt-5` - Latest model (if available)
  - `gpt-5-mini` - Fast and efficient
- **Timeout**: Request timeout in seconds (default: 30)
- **Prompt Template**: Customize the AI summary style

### 4. Start Scheduler

The app includes a daily scheduler task for automatic admin summaries:

```bash
# Development
bench start

# Production (supervisor will handle this automatically)
sudo systemctl restart supervisor
```

## 🚀 Usage

### AI Admin Summary

1. Navigate to **Desk → Build → Chatting with AI**
2. Click "Generate Summary" to create an instant report
3. Daily summaries are automatically generated via scheduler

### AI Chat

1. Open **AI Chat** workspace
2. Start a conversation with the AI assistant
3. All messages are stored in `AI Conversation` records
4. Context from ERPNext is automatically included

### Access Reports

- Navigate to **AI Report** DocType to view all generated reports
- Filter by date, user, or report type
- Export reports as needed

## 📱 Telegram Bot Integration

The app includes an optional Telegram bot for sales team integration.

### Setup

1. **Create a Telegram Bot:**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command and follow instructions
   - Copy the bot token

2. **Configure Environment Variables:**

```bash
# Add to bench .env file
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_ADMIN_IDS=123456789,987654321
FRAPPE_BASE_URL=https://your-erp-domain.com

# Optional security hardening
BOT_ENCRYPTION_KEY=your-32-byte-base64-key
TELEGRAM_BOT_DB_PATH=/path/to/telegram_bot.db
```

3. **Install Dependencies:**

```bash
pip install -e apps/erpnext_ai
```

4. **Run the Bot:**

```bash
# From bench directory
bench --site your-site-name execute erpnext_ai.erpnext_ai.telegram.bot.main

# Or using systemd/supervisor (recommended for production)
# Create a service file that runs the above command
```

### Bot Workflow

1. **Admin Setup:**
   - Admin sends `/add_master_manager <telegram_id>` to bot in private chat
   - This registers a sales master manager

2. **Master Manager Setup:**
   - Sales master manager joins target groups
   - Runs `/users` command in group
   - Selects future sales manager from inline list

3. **Sales Manager Setup:**
   - Sales manager receives DM from bot
   - Runs `/set_api <api_key> <api_secret>` to connect ERPNext account
   - Credentials are verified and stored encrypted

4. **Team Usage:**
   - `/report` - View recent ERPNext sales data
   - `/order` - Submit structured order request
   - Orders are saved as ERPNext Leads and logged locally

### Bot Commands

- `/start` - Initialize bot
- `/help` - Show help message
- `/users` - Select sales manager (master managers only)
- `/set_api` - Configure ERPNext credentials
- `/report` - Generate sales report
- `/order` - Submit new order
- `/add_master_manager` - Add master manager (admins only)

## 🗂️ DocTypes

The app creates the following DocTypes:

| DocType | Description |
|---------|-------------|
| **AI Settings** | Global configuration for AI features |
| **AI Report** | Stores generated admin summaries |
| **AI Conversation** | Chat history and context |
| **AI Message** | Individual messages in conversations |

## 📅 Scheduled Tasks

The app includes scheduled tasks that run automatically:

- **Daily**: `generate_daily_admin_summary` - Creates automated admin summary

## 🔧 Development

### Setup Development Environment

```bash
cd apps/erpnext_ai
pre-commit install
```

### Code Quality Tools

The app uses pre-commit hooks for code quality:

- **ruff** - Python linting and formatting
- **eslint** - JavaScript linting
- **prettier** - Code formatting
- **pyupgrade** - Python syntax modernization

### Running Tests

```bash
# Run all tests
bench --site your-site-name run-tests --app erpnext_ai

# Run specific test
bench --site your-site-name run-tests --app erpnext_ai --module path.to.test
```

## 🐛 Troubleshooting

### AI Features Not Working

1. Verify OpenAI API key is set correctly
2. Check AI Settings configuration
3. Review logs: `bench --site your-site-name console`

### Telegram Bot Not Responding

1. Verify `TELEGRAM_BOT_TOKEN` is set
2. Check bot is running: `ps aux | grep telegram`
3. Review bot logs
4. Ensure bot is added to group as administrator

### Scheduler Not Running

1. Check scheduler is enabled: `bench --site your-site-name doctor`
2. Verify services are running: `sudo supervisorctl status`
3. Check scheduler logs: `tail -f sites/your-site-name/logs/scheduler.log`

### Dependencies Issues

```bash
# Reinstall dependencies
pip install -e apps/erpnext_ai --force-reinstall

# Clear cache
bench --site your-site-name clear-cache
```

## 📝 License

MIT License

Copyright (c) 2024 Codex Assistant

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📧 Support

For issues, questions, or contributions, please open an issue on GitHub.

## 🙏 Acknowledgments

- Built with [Frappe Framework](https://frappeframework.com/)
- Powered by [OpenAI](https://openai.com/)
- Telegram integration using [python-telegram-bot](https://python-telegram-bot.org/)

---

**Note:** Remember to replace `YOUR-USERNAME` with your actual GitHub username in the installation commands.
