# 🗂 ProjectHub

> Your self-hosted AI-powered developer hub. Manage all local projects, connect any AI IDE in one click, track Git & Docker, and give your AI agent persistent memory across sessions.

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

Then open **http://localhost:8472**

[🇷🇺 Русский](#русский) · [🇨🇳 中文](#中文) · [🇩🇪 Deutsch](#deutsch)

---

| Dark | Light |
|------|-------|
| ![Dark theme](docs/assets/screenshot-dark.png) | ![Light theme](docs/assets/screenshot-light.png) |

| Project Modal | Connect to IDE |
|---------------|----------------|
| ![Modal](docs/assets/screenshot-modal.png) | ![Connect IDE](docs/assets/screenshot-connect.png) |

---

## ✨ Features

### 🗂 Project Dashboard

- **Auto-discovery** — scans `~/Projects/` recursively, groups by `@category`
- **Smart cards** — language icon, open count, last-opened time-ago
- **LIVE badges** — animated green pulse on cards with running Docker containers, polls every 15s
- **Activity heatmap** — 84-day GitHub-style bar in sticky nav (always visible while scrolling)
- **One-click launch** — open in Windsurf, VS Code, or any custom editor
- **Sorting** — by name / activity / status / favorite / custom drag order
- **Labels** — ★ Favorite · ▶ In Progress · ◼ Archive

### 🔌 Connect to IDE — one-click MCP setup

**New!** Go to **Settings → Connect IDE** — ProjectHub detects all installed AI editors and injects the MCP config automatically.

![Connect IDE](docs/assets/screenshot-connect.png)

Supported editors (auto-detected):

| Editor | | Editor | |
|--------|-|--------|-|
| Windsurf | Codeium Cascade | Qoder | qoder.com |
| Cursor | Cursor AI | Claude Code | Anthropic CLI |
| VS Code | + Copilot | AntiGravity | antigravity.ai |
| Zed | AI Assistant | Neovim | mcphub.nvim |
| JetBrains | IDEA/PyCharm/WS | Continue | continue.dev |
| Aider | CLI pair programmer | Void | open-source Cursor alt |
| Trae | ByteDance IDE | Gemini CLI | Google CLI |
| OpenCode | terminal agent | | |

- Click **Connect** → MCP config injected automatically
- Click **Disconnect** → config removed cleanly
- Shows config file path for each IDE
- **Manual setup** JSON with copy button for unsupported editors

### 🧠 AI Brain — persistent memory across sessions

The MCP server gives your AI agent a full memory of every project:

| Tool | What it does |
|------|-------------|
| `list_all_projects` | List all projects (prevents hallucinations) |
| `get_project_details` | Full info: git, docker, deps, type |
| `get_project_dependencies` | Dependencies for a specific project |
| `get_project_history` | **Full git log + session insights** for any time period |
| `get_project_context` | Load accumulated knowledge at session start |
| `log_session_insight` | Save decisions, bugs, patterns to knowledge base |
| `compile_knowledge` | Compile daily logs into permanent articles |
| `get_docker_status` | Live Docker container status |
| `get_databases` | PostgreSQL database list |
| `get_system_status` | Overall system health |
| `compare_projects` | Side-by-side project comparison |
| `read_project_file` | Read any project file (read-only, secure) |

#### `get_project_history` — the AI knows everything

```
# Full history (no limits)
get_project_history("myproject")

# Specific period
get_project_history("myproject", date_from="2026-01-01", date_to="2026-04-09")

# Only git, no memory
get_project_history("myproject", include_insights=false)

# Unlimited commits
get_project_history("myproject", max_commits=0)
```

Returns git commits + saved session insights merged chronologically. The AI gets the full picture of a project developed over months.

- **Brain tab** in dashboard — browse knowledge articles, full-text search
- **Log Insight modal** — type, tags, content, without leaving the browser
- Insight types: `decision` · `bug` · `pattern` · `gotcha` · `stack` · `qa`
- **Obsidian-compatible vault** at `~/Projects/@memory/brain/`

### 🐳 Docker & Git

- Per-project Docker container list with live status
- Git branch, uncommitted changes, last commit message
- LIVE detection — cards glow green when containers are running

### 📊 System Metrics

- Real-time CPU, RAM, Disk, Uptime in sidebar
- Smart polling — pauses when tab is hidden

### � Internationalization

- **Russian** · **English** · **Chinese (中文)** — full UI translation
- Instant language switch — no reload required

### �🎨 Themes

- **Dark** (default) · **Light** · **Midnight OLED**

---

## 🛠 Full Setup Guide

### Step 1 — Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Git | any | for Git status features |
| Docker | any | optional, for LIVE badges |
| Obsidian | any | optional, for Brain vault UI |

### Step 2 — One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

The script automatically:
- Checks Python 3.10+, installs `python3-venv` if needed
- Clones repo, creates venv, installs dependencies
- Sets up MCP server
- Creates systemd autostart service
- Optionally adds Obsidian autostart (opens `@memory` vault)
- Starts the dashboard and opens browser

### Step 3 — Manual install

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub

python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
python backend/main.py
```

Open **http://localhost:8472**

### Step 4 — Connect your AI editor

Go to **Settings → Connect IDE** in the dashboard. ProjectHub will:
1. Scan for installed editors
2. Show connection status for each
3. Inject MCP config on click

Or manually edit your IDE's MCP config:

```json
{
  "mcpServers": {
    "project-context": {
      "command": "/path/to/projecthub/mcp-server/.venv/bin/python",
      "args": ["/path/to/projecthub/mcp-server/server.py"]
    }
  }
}
```

> ⚠️ Use **absolute paths** — no `~` or relative paths in MCP configs.

Config file locations:

| Editor | Config path |
|--------|------------|
| Windsurf | `~/.config/Windsurf/User/mcp.json` |
| Qoder | `~/.config/Qoder/User/mcp.json` |
| Cursor | `~/.cursor/mcp.json` |
| Claude Code | `~/.claude/mcp_servers.json` |
| VS Code | `~/.config/Code/User/mcp.json` |
| AntiGravity | `~/.config/Antigravity/User/mcp.json` |
| Zed | `~/.config/zed/settings.json` → `context_servers` |

### Step 5 — Verify AI connection

Restart your IDE. In a new chat, ask:

```
Use get_project_context to load context for "myproject"
```

Or test history:

```
Use get_project_history to show me everything that changed in "myproject" this month
```

### Step 6 — Obsidian vault (optional)

1. Download from **https://obsidian.md**
2. Open → **Open folder as vault** → select `~/Projects/@memory/brain/`
3. All knowledge articles appear in the file explorer with graph view

---

## 🏗 Architecture

```
projecthub/
├── backend/
│   ├── main.py              # FastAPI — REST API + MCP connect endpoints
│   ├── static/
│   │   ├── index.html       # Dashboard SPA (Vanilla JS + Lucide Icons)
│   │   └── settings.html    # Settings: General, Appearance, Editors, Connect IDE
│   └── projecthub.db        # SQLite — projects, notes, settings, translations
└── mcp-server/
    └── server.py            # MCP server — 12 tools for AI agents
```

**Backend:** FastAPI · SQLite · subprocess (Git/Docker)
**Frontend:** Vanilla JS · Lucide Icons · CSS Variables (3 themes) · i18n (ru/en/zh)
**MCP:** Python MCP SDK · Markdown vault (Obsidian-compatible) · 12 tools
**Zero external services** — everything runs on localhost

---

## 📡 API

| Endpoint | Description |
|----------|-------------|
| `GET /api/projects` | All projects with filters |
| `GET /api/projects/live` | Projects with running Docker containers |
| `GET /api/projects/{id}/git` | Git status |
| `GET /api/projects/{id}/docker` | Docker containers |
| `GET /api/activity/heatmap` | 84-day activity data |
| `GET /api/brain/stats` | Knowledge base stats |
| `GET /api/brain/projects` | Projects with articles |
| `POST /api/brain/log` | Log new insight |
| `GET /api/brain/search?q=` | Full-text search |
| `GET /api/system` | CPU / RAM / Disk / Uptime |
| `GET /api/mcp/detect` | Scan installed IDEs + connection status |
| `POST /api/mcp/connect/{ide}` | Inject MCP config into IDE |
| `DELETE /api/mcp/connect/{ide}` | Remove MCP config from IDE |

---

## Русский

**ProjectHub** — самохостируемый AI-дашборд для управления локальными проектами разработчика.

### Установка одной командой

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

Скрипт автоматически: проверит Python 3.10+, клонирует репо, создаст venv, установит зависимости, настроит MCP сервер, создаст systemd сервис, опционально добавит Obsidian в автозапуск и откроет браузер.

### Что нового

- **Connect IDE** — подключи MCP к любому из 14 поддерживаемых редакторов одной кнопкой прямо из дашборда
- **get_project_history** — AI получает полную историю проекта: все git коммиты + сохранённые инсайты за любой период
- **12 MCP инструментов** — полный контекст системы для AI агента
- **Интерфейс на 3 языках** — русский, английский, китайский

### Как это работает

1. Запускаешь `python backend/main.py` — FastAPI стартует на порту 8472
2. Открываешь `http://localhost:8472` — дашборд находит все проекты из `~/Projects/`
3. **Settings → Connect IDE** — выбираешь редактор, жмёшь "Подключить", перезапускаешь IDE
4. AI агент получает доступ к 12 инструментам: проекты, Docker, Git история, память сессий
5. `get_project_history` — AI понимает что и когда менялось за всё время разработки

### AI Brain

- `log_session_insight` → инсайт записывается в Markdown (Obsidian vault)
- `get_project_context` → вся база знаний по проекту одним вызовом
- `get_project_history` → полная история: git + инсайты за любой период
- **Вкладка Brain** — просмотр и поиск по всем статьям
- Совместимо с **Obsidian** — `~/Projects/@memory/brain/`

### Поддерживаемые IDE

Windsurf · Qoder · Cursor · Claude Code · VS Code · AntiGravity · Zed · Neovim · JetBrains · Continue · Aider · Void · Trae · Gemini CLI · OpenCode

---

## 中文

**ProjectHub** 是一个面向开发者的自托管 AI 项目管理仪表板。

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

### 新功能

- **Connect IDE** — 一键将 MCP 连接到 14 款主流 AI 编辑器
- **get_project_history** — AI 获取项目完整历史：git 提交 + 会话洞察，支持任意时间段查询
- **12 个 MCP 工具** — 为 AI 智能体提供完整系统上下文
- **三语言界面** — 中文、英文、俄文

### 主要功能

- 自动发现 `~/Projects/` 下的所有项目，按类别分组
- **LIVE 徽章** — 有运行中 Docker 容器的项目显示绿色脉冲动画
- **活动热力图** — 84天记录，固定在导航栏顶部
- **Settings → Connect IDE** — 自动检测已安装的编辑器并注入 MCP 配置
- **Brain 标签** — AI 知识库，兼容 Obsidian

### 支持的编辑器

Windsurf · Qoder · Cursor · Claude Code · VS Code · AntiGravity · Zed · Neovim · JetBrains · Continue · Aider · Void · Trae · Gemini CLI · OpenCode

---

## Deutsch

**ProjectHub** ist ein selbst gehostetes AI-Dashboard zur Verwaltung lokaler Entwicklungsprojekte.

### Ein-Befehl-Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

### Neue Funktionen

- **Connect IDE** — MCP mit einem Klick in 14 AI-Editoren einrichten
- **get_project_history** — KI erhält vollständige Projekthistorie: Git-Commits + Session-Insights für beliebige Zeiträume
- **12 MCP-Werkzeuge** — vollständiger Systemkontext für KI-Agenten
- **3 Sprachen** — Deutsch, Englisch, Russisch, Chinesisch

### Funktionen

- Automatische Projekterkennung aus `~/Projects/`
- **LIVE-Badges** — grüner Puls bei laufenden Docker-Containern
- **Aktivitäts-Heatmap** — 84 Tage, fest in der Navigationsleiste
- **Connect IDE** — automatische MCP-Konfiguration für alle gängigen KI-Editoren
- **Brain-Tab** — KI-Wissensdatenbank, Obsidian-kompatibel

---

## License

MIT © [Habartru](https://github.com/Habartru)
