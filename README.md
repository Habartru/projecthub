<div align="center">

# 🗂 ProjectHub

**The developer dashboard you always wanted.**  
Manage all your local projects in one place — open editors, track Git, monitor Docker, and log AI memory. All from a beautiful self-hosted web UI.

[🇷🇺 Русский](#русский) · [🇨🇳 中文](#中文) · [🇩🇪 Deutsch](#deutsch)

```bash
curl -fsSL https://raw.githubusercontent.com/Habartru/projecthub/main/install.sh | bash
```

</div>

---

## What is ProjectHub?

ProjectHub is a **self-hosted local project management dashboard** built with FastAPI + Vanilla JS. It automatically discovers all your projects from the filesystem, shows Git status, Docker containers, and lets you open them in any editor — directly from the browser.

It also has a built-in **AI Brain** powered by an MCP server: log insights from your coding sessions and they persist in a structured Obsidian-compatible Markdown vault.

---

## ✨ Features

### 🗂 Project Dashboard
- **Auto-discovery** — scans `~/Projects/` recursively, groups by category
- **Smart cards** — language icon, open count, last-opened time-ago label
- **LIVE badges** — animated green pulse on cards with running Docker containers, polls every 15s
- **Activity heatmap** — 84-day GitHub-style bar in the sticky nav (always visible while scrolling)
- **One-click launch** — open in Windsurf, VS Code, or any custom editor
- **Open folder** — reveal project in file manager
- **Sorting** — by name / activity / status / favorite / custom drag order
- **Labels** — ★ Favorite · ▶ In Progress · ◼ Archive
- **Categories** — sidebar filter with project counts

### 🧠 AI Brain (Knowledge Base)
- MCP server with 3 tools: `log_session_insight`, `get_project_context`, `compile_knowledge`
- Insights stored as structured Markdown — **Obsidian-compatible vault**
- **Brain tab** in dashboard — browse articles by project, full-text search
- **Log Insight modal** — type, tags, content — all without leaving the browser
- Insight types: `decision` · `bug` · `pattern` · `gotcha` · `stack` · `qa`
- Daily logs auto-compiled into permanent per-project knowledge articles

### 🐳 Docker & Git
- Per-project Docker container list with status badges
- Git branch, uncommitted changes count, last commit message
- LIVE detection via Docker SDK — green glow card border when containers are running

### 📊 System Metrics
- Real-time CPU, RAM, Disk, Uptime in sidebar
- Smart polling — pauses automatically when tab is hidden

### 🎨 Themes
- **Dark** (default) · **Light** · **Midnight** OLED

---

## � Full Setup Guide

### Step 1 — Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Git | any | for Git status features |
| Docker | any | optional, for LIVE badges |
| Obsidian | any | **optional**, for Brain UI |

### Step 2 — Clone & Run Dashboard

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub

# Create virtualenv
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
- **Args template:** `{path}` is replaced with the project path, e.g. `{path}`
- **Color:** button accent color (hex)
- **Icon:** path to a `.png` icon (optional)

---

### Step 4 — AI Brain + MCP Server

The Brain is an **MCP server** that your AI agent (Claude Code, Windsurf Cascade, etc.) connects to. It gives the AI memory across sessions.

#### 4a. Start the MCP server

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
| `log_session_insight` | Save a decision, bug fix, pattern to the knowledge base |
| `get_project_context` | Load all saved knowledge for a project at session start |
| `compile_knowledge` | Compile daily logs into permanent project articles |

---

### Step 5 — Obsidian (optional but recommended)

Obsidian is **not required** — the Brain works without it. But it lets you visually browse and edit the knowledge vault.

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

To run ProjectHub automatically on login:

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

---

## 🚀 Quick Start (TL;DR)

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub && python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
python backend/main.py
# → http://localhost:8472
```

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

---

## Русский

**ProjectHub** — самохостируемый дашборд для управления локальными проектами разработчика.

### Как это работает

1. Запускаешь `python backend/main.py` — FastAPI стартует на порту 8472
2. Открываешь `http://localhost:8472` — дашборд автоматически находит все проекты из `~/Projects/`
3. Видишь все проекты в виде карточек: язык, категория, Git-статус, время последнего открытия
4. **LIVE-бейдж** (анимированный зелёный пульс) — на карточках проектов с запущенными Docker контейнерами, обновляется каждые 15 секунд
5. **Activity Heatmap** в sticky панели навигации — 84-дневный график, всегда виден при прокрутке
6. Кликаешь на карточку — модальное окно с Git веткой, коммитом, Docker контейнерами, заметками и кнопками редакторов
7. Кнопки редакторов открывают проект напрямую в Windsurf / VS Code

### AI Brain — как работает память

- **MCP сервер** подключается к любому AI-агенту (Claude Code, Windsurf Cascade и т.д.)
- Во время сессии агент вызывает `log_session_insight` → инсайт записывается в Markdown
- `get_project_context` возвращает всю накопленную базу знаний по проекту в начале новой сессии
- `compile_knowledge` компилирует дневные логи в постоянные статьи
- **Вкладка Brain** в дашборде — просмотр и поиск по всем статьям прямо из браузера
- Все файлы совместимы с **Obsidian** — открывай vault как обычную папку

### Быстрый старт
```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub && python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
python backend/main.py
# → http://localhost:8472
```

---

## 中文

**ProjectHub** 是一个面向开发者的自托管本地项目管理仪表板。

### 工作原理

1. 运行 `python backend/main.py` — FastAPI 在 8472 端口启动
2. 打开 `http://localhost:8472` — 自动发现 `~/Projects/` 下的所有项目
3. 卡片显示：语言、分类、Git状态、最后打开时间
4. **LIVE 徽章**（绿色脉冲动画）— 有运行中 Docker 容器的项目，每15秒自动更新
5. **活动热力图** 固定在导航栏 — 84天记录，滚动时始终可见
6. 点击卡片 — 显示 Git 分支、提交信息、Docker 容器、笔记
7. 编辑器按钮 — 直接在 Windsurf / VS Code 中打开项目

### AI 大脑
- **Brain 标签** — 按项目浏览和搜索知识库
- MCP 服务器工具：`log_session_insight` · `get_project_context` · `compile_knowledge`
- 所有文件兼容 **Obsidian**

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub && python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt && python backend/main.py
```

---

## Deutsch

**ProjectHub** ist ein selbst gehostetes Dashboard zur Verwaltung lokaler Entwicklungsprojekte.

### So funktioniert es

1. `python backend/main.py` starten — Server läuft auf Port 8472
2. `http://localhost:8472` öffnen — erkennt automatisch alle Projekte in `~/Projects/`
3. Karten zeigen: Sprache, Kategorie, Git-Status, letzte Öffnungszeit
4. **LIVE-Badges** (grüner Puls) — Karten mit laufenden Docker-Containern, alle 15s aktualisiert
5. **Aktivitäts-Heatmap** fest in der Navigationsleiste — 84 Tage, immer sichtbar
6. Karte anklicken — Git-Branch, Commit, Docker-Container, Notizen
7. Editor-Buttons — Projekt direkt in Windsurf / VS Code öffnen

### KI-Gehirn
- **Brain-Tab** — Wissensdatenbank pro Projekt durchsuchen
- MCP-Tools: `log_session_insight` · `get_project_context` · `compile_knowledge`
- Alle Dateien **Obsidian-kompatibel**

```bash
git clone https://github.com/Habartru/projecthub.git
cd projecthub && python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt && python backend/main.py
```

---

## License

MIT © [Habartru](https://github.com/Habartru)
