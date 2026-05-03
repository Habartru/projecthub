"""OpenAI-format tool schemas exposed by the ProjectHub memory provider."""

REMEMBER_SCHEMA = {
    "name": "projecthub_remember",
    "description": (
        "Save a project-specific insight to the ProjectHub knowledge base. "
        "Use this — NOT the built-in memory tool — for: architecture decisions, "
        "bug+fix pairs, reusable patterns specific to this codebase, tech stack "
        "details (versions, configs), and any technical learning a future "
        "session on this project would benefit from. The current project is "
        "auto-detected from the working directory; pass `project` only when "
        "logging cross-project insights."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "insight_type": {
                "type": "string",
                "enum": ["decision", "bug", "pattern", "gotcha", "stack", "qa", "other"],
                "description": (
                    "decision = why something was built this way; "
                    "bug = a bug found and fixed; "
                    "pattern = reusable approach in this codebase; "
                    "gotcha = non-obvious trap; "
                    "stack = library/version/config detail; "
                    "qa = recurring question with answer; "
                    "other = doesn't fit categories above"
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "The insight, specific and actionable. Ideally 1-3 sentences. "
                    "State the WHAT and WHY. Avoid 'we did X' — write 'X works "
                    "because Y' so it's useful out of context."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Free-form tags for searchability, e.g. ['fastapi', 'auth', 'docker'].",
            },
            "project": {
                "type": "string",
                "description": "Optional. Override auto-detected project. Use only for cross-project insights.",
            },
        },
        "required": ["insight_type", "content"],
    },
}

RECALL_SCHEMA = {
    "name": "projecthub_recall",
    "description": (
        "Retrieve all accumulated knowledge for a project: past decisions, bugs, "
        "patterns, gotchas, stack details. Call this when starting work on "
        "something non-trivial in the current project, or when explicitly asked "
        "'what do you know about <project>'. Returns a markdown article. The "
        "current project is auto-detected; pass `project` for cross-project lookup."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Optional. Project name. Defaults to current project from cwd.",
            },
        },
        "required": [],
    },
}

HISTORY_SCHEMA = {
    "name": "projecthub_history",
    "description": (
        "Get the development timeline of a project: git commits merged with "
        "saved insights, in chronological order. Use this to understand what "
        "changed and WHY over time, especially when investigating regressions, "
        "onboarding to a project, or answering 'when did X happen'. Defaults "
        "to current project; supports date filtering."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Optional. Defaults to current project."},
            "date_from": {"type": "string", "description": "Optional ISO date YYYY-MM-DD. Defaults to project start."},
            "date_to": {"type": "string", "description": "Optional ISO date YYYY-MM-DD. Defaults to today."},
            "max_commits": {"type": "integer", "description": "Optional, default 200. Set 0 for unlimited."},
        },
        "required": [],
    },
}

ALL_SCHEMAS = [REMEMBER_SCHEMA, RECALL_SCHEMA, HISTORY_SCHEMA]
