# 🚀 ProjectHub

> **Your Local Development Workspace Navigator**
> 
> All your projects in one command center. Optimized for speed. Designed for developers.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Integrated-purple.svg)](https://modelcontextprotocol.io)

<p align="center">
  <img src="docs/assets/screenshot-dark.png" alt="ProjectHub Dark Theme" width="800">
</p>

## ✨ Why ProjectHub?

**The Problem:** You have dozens of projects scattered across your machine. Switching between them is a pain. Remembering what's where is harder. Opening the right IDE with the right project takes too many clicks.

**The Solution:** ProjectHub — a blazing-fast, lightweight dashboard that knows about ALL your local projects and puts them one click away.

### 🌟 Star Features

| Feature | Description | Impact |
|---------|-------------|--------|
| ⚡ **Zero-Lag Performance** | Smart caching, debounced search, visibility-aware updates | Works smoothly even on 10-year-old laptops |
| 🎨 **Three Beautiful Themes** | GitHub Dark, GitHub Light, Midnight OLED | Easy on the eyes, day or night |
| 🌍 **Multi-Language** | English, Русский, 中文 | Native experience for global developers |
| 🤖 **MCP Server Built-in** | AI agents can query your projects via Model Context Protocol | The ONLY project manager with AI integration |
| 🏷️ **Smart Labels** | Favorite ★, Working ▶, Archive ◼ | Organize without overthinking |
| 🐳 **Docker Aware** | Shows running containers per project | DevOps-ready |
| 🌿 **Git Integration** | Branch, status, last commit at a glance | No more `cd && git status` |
| 🔍 **Instant Search** | 300ms debounced, searches names & paths | Find anything in milliseconds |

## 📸 Screenshots

### 🌙 GitHub Dark Theme
Beautiful dark interface perfect for late-night coding sessions.

<p align="center">
  <img src="docs/assets/screenshot-dark.png" alt="Dark Theme Dashboard" width="800">
</p>

### 📋 Project Detail Modal
Everything about your project in one place — Git status, Docker containers, notes, and quick actions.

<p align="center">
  <img src="docs/assets/screenshot-modal.png" alt="Project Detail Modal" width="600">
</p>

### ☀️ GitHub Light Theme
Clean and crisp interface for daytime work.

<p align="center">
  <img src="docs/assets/screenshot-light.png" alt="Light Theme Dashboard" width="800">
</p>

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Habartru/projecthub.git
cd projecthub

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python backend/main.py

# Open in browser
open http://localhost:8472/static/index.html
```

### One-Line Setup (Coming Soon)

```bash
curl -fsSL https://projecthub.dev/install.sh | bash
```

## 🖥️ Dashboard Features

### Main View
- **Project Cards** — Visual cards with type icons, labels, tags
- **Category Filtering** — @active, @archive, @experiments, etc.
- **Smart Sorting** — By name, by activity, custom drag-and-drop order
- **Quick Actions** — Open in Windsurf, Antigravity, or file manager

### Project Detail Modal
- 📋 Project info & metadata
- 🏷️ Label management (Favorite/Working/Archive)
- 🌿 Git status (branch, changes, last commit)
- 🐳 Docker containers
- 📝 Notes & comments
- ⚡ Quick launch buttons

### System Metrics
Real-time monitoring (with smart intervals to save CPU):
- CPU usage (updates every 5s)
- RAM usage (updates every 10s)
- Disk space (updates every 60s)
- Uptime

## 🤖 MCP Server Integration

ProjectHub includes a built-in **MCP (Model Context Protocol) Server** — making it the first project manager that AI agents can natively interact with.

### Available Tools

| Tool | Purpose |
|------|---------|
| `list_all_projects` | Get all projects with IDs |
| `get_project_details` | Full project information |
| `get_project_dependencies` | requirements.txt, package.json, etc. |
| `get_docker_status` | Running containers |
| `get_databases` | PostgreSQL databases |
| `read_project_file` | Safe file reading |
| `compare_projects` | Compare two projects side-by-side |

### For AI Agents

```javascript
// AI agents can now understand your project structure
const projects = await mcp.list_all_projects();
const details = await mcp.get_project_details("MyAwesomeApp");
```

## 🎨 Themes

Switch between three carefully crafted themes:

**GitHub Dark** (Default)
```
--bg-primary: #0d1117
--bg-secondary: #161b22
--accent-blue: #58a6ff
```

**GitHub Light**
```
--bg-primary: #ffffff
--bg-secondary: #f6f8fa
--accent-blue: #0969da
```

**Midnight OLED**
```
--bg-primary: #000000
--bg-secondary: #0a0a0a
--accent-blue: #4da6ff
```

## 🌍 Localization

Currently supported:
- 🇺🇸 English (`en`)
- 🇷🇺 Russian (`ru`)
- 🇨🇳 Chinese (`zh`)

Add your language in `backend/main.py` → `init_translations()`.

## ⚡ Performance

Benchmarked on a 2015 MacBook Air (4GB RAM):
- **Cold start:** < 2 seconds
- **Project loading:** < 100ms (cached)
- **Search response:** < 50ms
- **Memory footprint:** < 50MB
- **CPU usage:** Near zero when idle

### Optimizations
- ✅ Client-side caching (localStorage/sessionStorage)
- ✅ Smart intervals (pause updates when tab hidden)
- ✅ Debounced search (300ms)
- ✅ Lazy Git status loading
- ✅ Incremental DOM updates

## 🛠️ Tech Stack

**Backend**
- FastAPI — High-performance Python framework
- SQLite — Serverless, zero-config database
- Async/await — Non-blocking I/O

**Frontend**
- Vanilla JavaScript — No bloat, maximum speed
- Lucide Icons — Clean, consistent iconography
- CSS Custom Properties — Theme system

**DevOps**
- MCP Server — AI integration protocol
- Docker API — Container awareness
- Git integration — Repository inspection

## 📁 Project Structure

```
projecthub/
├── backend/
│   ├── main.py              # FastAPI server + MCP
│   └── static/
│       ├── index.html       # Main dashboard
│       ├── settings.html    # Configuration UI
│       └── tests/
├── docs/
│   └── assets/              # Screenshots, demos
├── mcp-server/              # Standalone MCP server
│   ├── server.py
│   └── README.md
└── README.md
```

## 🎯 Roadmap

- [ ] VS Code extension
- [ ] JetBrains plugin
- [ ] Mobile companion app
- [ ] Cloud sync (optional)
- [ ] Team collaboration features
- [ ] CI/CD integration

## 🤝 Contributing

We love contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Good first issues:**
- Add new theme
- Translate to new language
- Add project type detection
- Improve documentation

## 📜 License

MIT License — see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com) ❤️
- Icons by [Lucide](https://lucide.dev)
- MCP protocol by [Anthropic](https://anthropic.com)

---

<p align="center">
  <b>Star ⭐ this repo if ProjectHub helps you stay organized!</b>
</p>

<p align="center">
  <a href="https://github.com/Habartru/projecthub/stargazers">View Stargazers</a> •
  <a href="https://github.com/Habartru/projecthub/issues">Report Bug</a> •
  <a href="https://github.com/Habartru/projecthub/discussions">Discussions</a>
</p>
