# 🗂 ProjectHub

> The developer dashboard you always wanted. Manage all your local projects — open editors, track Git, monitor Docker, and log AI memory. All from a self-hosted web UI.

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

Then open **http://localhost:8472**

[🇷🇺 Русский](#русский) · [🇨🇳 中文](#中文) · [🇩🇪 Deutsch](#deutsch)

---

| Dark | Light |
|------|-------|
| ![Dark theme](docs/assets/screenshot-dark.png) | ![Light theme](docs/assets/screenshot-light.png) |

![Modal](docs/assets/screenshot-modal.png)

---

## ✨ Features

### 🗂 Project Dashboard

- **Auto-discovery** — scans `~/Projects/` recursively, groups by category
- **Smart cards** — language icon, open count, last-opened time-ago
- **LIVE badges** — animated green pulse on cards with running Docker containers, polls every 15s
- **Activity heatmap** — 84-day GitHub-style bar in the sticky nav (always visible while scrolling)
- **One-click launch** — open in Windsurf, VS Code, or any custom editor
- **Sorting** — by name / activity / status / favorite / custom drag order
- **Labels** — ★ Favorite · ▶ In Progress · ◼ Archive

### 🧠 AI Brain (Knowledge Base)

- MCP server with 3 tools: `log_session_insight`, `get_project_context`, `compile_knowledge`
- Insights stored as structured Markdown — **Obsidian-compatible vault**
- **Brain tab** in dashboard — browse articles by project, full-text search
- **Log Insight modal** — type, tags, content, all without leaving the browser
- Insight types: `decision` · `bug` · `pattern` · `gotcha` · `stack` · `qa`

### 🐳 Docker & Git

- Per-project Docker container list with live status badges
- Git branch, uncommitted changes, last commit message
- LIVE detection — cards glow green when containers are running

### 📊 System Metrics

- Real-time CPU, RAM, Disk, Uptime in sidebar
- Smart polling — pauses when tab is hidden

### 🎨 Themes

- **Dark** (default) · **Light** · **Midnight** OLED

---

## 🛠 Full Setup Guide

### Step 1 — Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Git | any | for Git status features |
| Docker | any | optional, for LIVE badges |
| Obsidian | any | optional, for Brain vault UI |

### Step 2 — Clone & Run Dashboard

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub

python -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

pip install -r backend/requirements.txt
python backend/main.py
```

Open **http://localhost:8472** — done. Dashboard starts scanning `~/Projects/` immediately.

> **Want a different projects root?** Edit `PROJECTS_ROOT` at the top of `backend/main.py`.

---

### Step 3 — Configure Editors (optional)

Go to **http://localhost:8472/static/settings.html** → Editors tab.

By default Windsurf and VS Code are pre-configured. To add a custom editor:

- **Command:** the binary name, e.g. `cursor`, `idea`, `zed`
- **Args template:** `{path}` is replaced with the project path
- **Color:** button accent color (hex)
- **Icon:** path to a `.png` icon (optional)

---

### Step 4 — AI Brain + MCP Server

The Brain is an **MCP server** that your AI agent (Claude Code, Windsurf Cascade, etc.) connects to. It gives the AI persistent memory across sessions.

#### 4a. Install the MCP server

```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4b. Register in your AI client

**Windsurf / Cascade** — edit `~/.config/Qoder/User/mcp.json`:

```json
{
  "mcpServers": {
    "project-context": {
      "command": "/absolute/path/to/projecthub/mcp-server/.venv/bin/python",
      "args": ["/absolute/path/to/projecthub/mcp-server/server.py"]
    }
  }
}
```

**Claude Code** — edit `~/.claude/mcp_servers.json` (same format).

**Cursor** — Settings → MCP → Add server (same JSON).

> ⚠️ Use **absolute paths** — no `~` or relative paths in MCP configs.

#### 4c. Verify it works

Restart your AI client. In a new chat, ask:

```
Use the project-context MCP tool to get context for project "myproject"
```

If it responds with project knowledge — Brain is connected.

#### 4d. Available MCP tools

| Tool | What it does |
|------|-------------|
| `log_session_insight` | Save a decision, bug fix, or pattern to the knowledge base |
| `get_project_context` | Load all saved knowledge for a project at session start |
| `compile_knowledge` | Compile daily logs into permanent project articles |

---

### Step 5 — Obsidian (optional but recommended)

Obsidian is **not required** — the Brain works without it. But it lets you visually browse and edit the knowledge vault with a beautiful graph view.

#### Where the vault lives

```
~/Projects/@memory/brain/
├── knowledge/
│   ├── index.md              # Auto-generated index of all articles
│   └── projects/
│       ├── myproject.md      # Per-project knowledge article
│       └── ...
└── logs/
    └── 2026-04-09.md         # Daily log (auto-created by MCP)
```

#### Opening in Obsidian

1. Download Obsidian from **https://obsidian.md** (free)
2. Open Obsidian → **Open folder as vault**
3. Select `~/Projects/@memory/brain/`
4. Done — all knowledge articles appear in the file explorer

> The vault path is configured in `mcp-server/server.py` as `MEMORY_DIR`. Change it if your `@memory` folder is elsewhere.

---

### Step 6 — Autostart (optional)

**systemd (Linux):**

```ini
# ~/.config/systemd/user/projecthub.service
[Unit]
Description=ProjectHub Dashboard

[Service]
WorkingDirectory=/path/to/projecthub
ExecStart=/path/to/projecthub/venv/bin/python backend/main.py
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now projecthub
```

> The one-line installer handles all of this automatically.

---

## 🏗 Architecture

```
projecthub/
├── backend/
│   ├── main.py            # FastAPI — all REST endpoints
│   ├── static/
│   │   └── index.html     # Single-page dashboard (Vanilla JS + Lucide Icons)
│   └── projecthub.db      # SQLite — projects, notes, settings, labels
└── mcp-server/
    └── server.py          # MCP server — Brain tools for AI agents
```

**Backend:** FastAPI · SQLite · Docker SDK · subprocess (Git)
**Frontend:** Vanilla JS · Lucide Icons · CSS Variables (3 themes)
**MCP:** Python MCP SDK · Markdown vault (Obsidian-compatible)
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

---

## Русский

**ProjectHub** — самохостируемый дашборд для управления локальными проектами разработчика.

### Установка одной командой

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

Скрипт сам: проверит Python 3.10+, клонирует репо, создаст venv, установит зависимости, пропишет MCP в конфиг твоего AI-клиента (Windsurf/Claude Code/Cursor), создаст systemd сервис и запустит браузер.

### Как это работает

1. Запускаешь `python backend/main.py` — FastAPI стартует на порту 8472
2. Открываешь `http://localhost:8472` — дашборд автоматически находит все проекты из `~/Projects/`
3. **LIVE-бейдж** (зелёный пульс) — на карточках проектов с запущенными Docker контейнерами, обновляется каждые 15 секунд
4. **Activity Heatmap** в sticky панели навигации — 84-дневный график, всегда виден при прокрутке
5. Кликаешь на карточку — Git ветка, коммит, Docker контейнеры, заметки
6. Кнопки редакторов открывают проект в Windsurf / VS Code

### AI Brain

- **MCP сервер** — подключается к любому AI-агенту
- `log_session_insight` → инсайт записывается в Markdown
- `get_project_context` → возвращает всю базу знаний по проекту
- **Вкладка Brain** в дашборде — просмотр и поиск по всем статьям
- Совместимо с **Obsidian** — открывай `~/Projects/@memory/brain/` как vault

---

## 中文

**ProjectHub** 是一个面向开发者的自托管本地项目管理仪表板。

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

安装脚本会自动：检查 Python 3.10+、克隆仓库、创建虚拟环境、安装依赖、注册 MCP 配置（Windsurf/Claude Code/Cursor）、创建 systemd 服务并打开浏览器。

### 主要功能

- 自动发现 `~/Projects/` 下的所有项目，按类别分组
- **LIVE 徽章** — 有运行中 Docker 容器的项目显示绿色脉冲动画
- **活动热力图** — 84天记录，固定在导航栏顶部
- 一键在 Windsurf / VS Code 中打开项目
- **Brain 标签** — AI 知识库，兼容 Obsidian

---

## Deutsch

**ProjectHub** ist ein selbst gehostetes Dashboard zur Verwaltung lokaler Entwicklungsprojekte.

### Ein-Befehl-Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

Das Skript erledigt automatisch: Python 3.10+ prüfen, Repository klonen, venv erstellen, Abhängigkeiten installieren, MCP in AI-Client-Konfiguration eintragen (Windsurf/Claude Code/Cursor), systemd-Service erstellen und Browser öffnen.

### Funktionen

- Automatische Projekterkennung aus `~/Projects/`
- **LIVE-Badges** — grüner Puls bei laufenden Docker-Containern
- **Aktivitäts-Heatmap** — 84 Tage, fest in der Navigationsleiste
- Ein-Klick-Start in Windsurf / VS Code
- **Brain-Tab** — KI-Wissensdatenbank, Obsidian-kompatibel

---

## License

MIT © [Habartru](https://github.com/Habartru)
