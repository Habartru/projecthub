# ProjectHub Memory Plugin for Hermes

Bridges Hermes-agent to the ProjectHub knowledge vault, so project-specific
insights (decisions, bugs, patterns) flow into the persistent vault at
`~/Projects/@memory/brain/` instead of (or in addition to) Hermes'
internal `MEMORY.md`.

## What it does

- Auto-detects the current project from the working directory at session start
  (with `system/scratch` fallback if cwd isn't inside any registered project).
- Injects a project-aware system-prompt block each turn that routes "project
  facts" to `projecthub_remember` and "user persona" to the built-in memory tool.
- Exposes three tools to the agent: `projecthub_remember`, `projecthub_recall`,
  `projecthub_history`.
- Runs an end-of-session curator that extracts 1-3 reusable insights from the
  conversation and persists them tagged `#auto-curated`.
- Mirrors built-in `MEMORY.md` writes that look project-scoped.

## Install

```bash
./install.sh
```

This symlinks the plugin source into `~/.hermes/plugins/projecthub/` and
installs `httpx` in Hermes' venv if missing.

Then activate in `~/.hermes/config.yaml`:

```yaml
memory:
  provider: projecthub
```

Restart Hermes (or just start a new session — config is read fresh).

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PROJECTHUB_URL` | `http://127.0.0.1:8765` | ProjectHub backend endpoint. |
| `TERMINAL_CWD` | (Hermes-managed) | Hermes sets this in some run modes; the plugin prefers it over `os.getcwd()` for cwd resolution. |

## Other terminal emulators (for the "Open in Hermes" UI button)

The ProjectHub UI button uses `gnome-terminal` by default. Edit the editor in
ProjectHub's Settings → Editors. Recipes:

- **konsole**: `konsole` / `--workdir {path} -e hermes`
- **kitty**: `kitty` / `--directory {path} hermes`
- **alacritty**: `alacritty` / `--working-directory {path} -e hermes`
- **wezterm**: `wezterm` / `start --cwd {path} hermes`
- **xterm**: `xterm` / `-e bash -c "cd {path} && exec hermes"`

## Troubleshooting

- "ProjectHub backend at http://127.0.0.1:8765 unreachable" → check `systemctl --user status projecthub`.
- Plugin doesn't activate → confirm `memory.provider: projecthub` in `~/.hermes/config.yaml` and that the symlink at `~/.hermes/plugins/projecthub/` resolves.
- httpx ImportError → run `~/.hermes/hermes-agent/venv/bin/pip install httpx`.
