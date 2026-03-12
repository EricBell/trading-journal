"""About / Release Notes blueprint."""

from pathlib import Path

import markdown
from flask import Blueprint, render_template

from ..auth import login_required
from ...authorization import AuthContext

bp = Blueprint("about", __name__, url_prefix="/about")

# Project root is three levels up from this file:
# trading_journal/web/routes/about.py → trading_journal/web/routes → trading_journal/web → trading_journal → project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_RELEASE_NOTES_PATH = _PROJECT_ROOT / "RELEASE_NOTES.md"


@bp.route("/")
@login_required
def index():
    user = AuthContext.get_current_user()
    releases = _parse_release_notes()
    return render_template("about/index.html", user=user, releases=releases)


def _parse_release_notes() -> list[dict]:
    try:
        text = _RELEASE_NOTES_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [{"heading": "Release Notes", "html": "<p>No release notes found.</p>", "is_current": True}]

    # Split on section boundaries; keep heading text with each section
    raw_sections = text.split("\n## ")

    releases = []
    for i, section in enumerate(raw_sections):
        section = section.strip()
        if not section:
            continue

        # Strip leading "## " if present on the very first section
        if section.startswith("## "):
            section = section[3:]

        lines = section.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        html = markdown.markdown(body, extensions=["nl2br"])

        releases.append({
            "heading": heading,
            "html": html,
            "is_current": i == 0 or (i == 1 and raw_sections[0].strip() == ""),
        })

    # Mark only the first real release as current
    if releases:
        for r in releases:
            r["is_current"] = False
        releases[0]["is_current"] = True

    return releases
