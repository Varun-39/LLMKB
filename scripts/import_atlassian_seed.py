"""
Jira / Confluence one-time seed importer — the deck's "Jira one-time seed"
Markdown Knowledge Layer component: "One-time seed from Jira / Confluence /
runbooks into approved Markdown knowledge files."

This is genuinely one-time, not a sync: unlike scripts/sync_to_minio.py
(repeatable, mtime-aware, wiki/ -> MinIO), this script has no delta tracking
and simply regenerates its output files by deterministic name on every run.
It is also NOT approved-by-default: output lands in wiki/Pending Review/,
which src/loader.py explicitly excludes from ingestion (same mechanism as
Templates/) — a human must read, edit, and move a file into a real category
folder (Incidents/, Runbooks/, System/, ...) before it's ever indexed. This
mirrors the deck's own "Git Review Workflow: tracks changes, supports review,
approval, rollback" component; nothing here auto-approves imported content.

Two source modes:
    --source export   (default) Reads local export JSON files shaped like the
                       real Jira/Confluence REST responses — see
                       data/sample_atlassian_export/*.json. This is the
                       "synthetic/test data for PoC if live access is not
                       available" path the deck's own Dependencies slide names.
    --source live      Pulls from real Jira/Confluence Cloud REST APIs using
                       ATLASSIAN_EMAIL/ATLASSIAN_API_TOKEN + JIRA_BASE_URL/
                       JIRA_JQL/CONFLUENCE_BASE_URL/CONFLUENCE_SPACE_KEY env
                       vars (see .env.example). Needs `requests` (already a
                       dependency) and real credentials — nothing else in this
                       repo requires either.

Usage:
    python scripts/import_atlassian_seed.py
    python scripts/import_atlassian_seed.py --source export --export-dir data/sample_atlassian_export
    python scripts/import_atlassian_seed.py --source live
    python scripts/import_atlassian_seed.py --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import WIKI_SOURCE_DIR

PENDING_REVIEW_DIR = Path(WIKI_SOURCE_DIR) / "Pending Review"

_BLOCK_CLOSE_RE = re.compile(r"</(p|div|li|h[1-6])>", re.IGNORECASE)
_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RUN_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")


def strip_html(value: str) -> str:
    """Minimal storage-format-HTML -> plain text: no new HTML/Markdown library
    dependency for a one-time import whose output a human reviews anyway.
    Block-level closes and <br> become newlines FIRST, so adjacent <p> blocks
    don't get silently concatenated into one run-on sentence once tags are
    stripped."""
    text = _BLOCK_CLOSE_RE.sub("\n\n", value or "")
    text = _BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip()


def _yaml_str(value: str) -> str:
    """Quote a frontmatter scalar defensively (titles/summaries may contain
    colons, quotes, etc. that would otherwise break YAML parsing)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_PRIORITY_TO_SEVERITY = {
    "highest": "SEV-1",
    "high": "SEV-2",
    "medium": "SEV-3",
    "low": "SEV-4",
    "lowest": "SEV-4",
}


def jira_issue_to_markdown(issue: dict) -> tuple[str, str]:
    """Convert one Jira REST API issue object into a Pending Review Markdown
    file. Returns (filename, content). Deliberately does NOT set error_family/
    resolution_runbook/resolution_outcome — those are curated KB facts, not
    something inferable from a raw Jira export; a reviewer adds them when
    promoting the file out of Pending Review/."""
    key = issue["key"]
    fields = issue.get("fields", {})
    summary = fields.get("summary", key)
    components = fields.get("components") or []
    service = components[0]["name"].lower() if components else "general"
    priority = ((fields.get("priority") or {}).get("name") or "").lower()
    severity = _PRIORITY_TO_SEVERITY.get(priority, "")
    status = (fields.get("status") or {}).get("name", "")
    resolution = (fields.get("resolution") or {}).get("name", "")
    created = (fields.get("created") or "")[:10]

    body_lines = [
        "## Summary",
        "",
        strip_html(fields.get("description", "")) or "_(no description)_",
        "",
        "## Jira Comments",
        "",
    ]
    comments = ((fields.get("comment") or {}).get("comments")) or []
    if comments:
        for c in comments:
            author = (c.get("author") or {}).get("displayName", "unknown")
            when = (c.get("created") or "")[:10]
            body_lines.append(f"- **{author}** ({when}): {strip_html(c.get('body', ''))}")
    else:
        body_lines.append("_(no comments)_")

    frontmatter = "\n".join([
        "---",
        f"id: JIRA-{key}",
        f"title: {_yaml_str(summary)}",
        "source: jira",
        f"source_key: {key}",
        f"service: {service}",
        f"severity: {severity}",
        f"status: {_yaml_str(status)}",
        f"resolution: {_yaml_str(resolution)}",
        "tags:",
        "  - imported",
        "  - jira",
        f"date: {created or 'unknown'}",
        f"imported_at: {datetime.now(timezone.utc).isoformat()}",
        "review_status: pending",
        "---",
        "",
        "",
    ])
    return f"JIRA-{key}.md", frontmatter + "\n".join(body_lines) + "\n"


def confluence_page_to_markdown(page: dict) -> tuple[str, str]:
    """Convert one Confluence REST API content object into a Pending Review
    Markdown file. Same non-approval stance as jira_issue_to_markdown()."""
    page_id = page["id"]
    title = page.get("title", page_id)
    space = (page.get("space") or {}).get("key", "")
    when = ((page.get("version") or {}).get("when") or "")[:10]
    storage_value = ((page.get("body") or {}).get("storage") or {}).get("value", "")

    frontmatter = "\n".join([
        "---",
        f"id: CONF-{page_id}",
        f"title: {_yaml_str(title)}",
        "source: confluence",
        f"source_key: \"{page_id}\"",
        f"space: {space}",
        "tags:",
        "  - imported",
        "  - confluence",
        f"date: {when or 'unknown'}",
        f"imported_at: {datetime.now(timezone.utc).isoformat()}",
        "review_status: pending",
        "---",
        "",
        "",
    ])
    body = "## Content\n\n" + (strip_html(storage_value) or "_(empty page)_") + "\n"
    return f"CONF-{page_id}.md", frontmatter + body


def _fetch_live_jira(base_url: str, email: str, token: str, jql: str) -> list[dict]:
    import requests
    resp = requests.get(
        f"{base_url.rstrip('/')}/rest/api/2/search",
        params={"jql": jql, "fields": "summary,description,priority,status,resolution,components,created,comment"},
        auth=(email, token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("issues", [])


def _fetch_live_confluence(base_url: str, email: str, token: str, space_key: str) -> list[dict]:
    import requests
    resp = requests.get(
        f"{base_url.rstrip('/')}/rest/api/content",
        params={"spaceKey": space_key, "expand": "body.storage,space,version"},
        auth=(email, token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def run_import(source: str, export_dir: Optional[Path], dry_run: bool = False) -> dict:
    stats = {"jira_issues": 0, "confluence_pages": 0, "written": []}

    if source == "export":
        export_dir = export_dir or Path("data/sample_atlassian_export")
        jira_issues = json.loads((export_dir / "jira_issues.json").read_text(encoding="utf-8"))
        confluence_pages = json.loads((export_dir / "confluence_pages.json").read_text(encoding="utf-8"))
    elif source == "live":
        jira_issues = _fetch_live_jira(
            os.environ["JIRA_BASE_URL"], os.environ["ATLASSIAN_EMAIL"],
            os.environ["ATLASSIAN_API_TOKEN"], os.environ.get("JIRA_JQL", "resolution is not EMPTY"),
        )
        confluence_pages = _fetch_live_confluence(
            os.environ["CONFLUENCE_BASE_URL"], os.environ["ATLASSIAN_EMAIL"],
            os.environ["ATLASSIAN_API_TOKEN"], os.environ["CONFLUENCE_SPACE_KEY"],
        )
    else:
        raise ValueError(f"unknown source: {source!r}")

    if not dry_run:
        PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    for issue in jira_issues:
        filename, content = jira_issue_to_markdown(issue)
        stats["jira_issues"] += 1
        stats["written"].append(filename)
        if not dry_run:
            (PENDING_REVIEW_DIR / filename).write_text(content, encoding="utf-8")

    for page in confluence_pages:
        filename, content = confluence_page_to_markdown(page)
        stats["confluence_pages"] += 1
        stats["written"].append(filename)
        if not dry_run:
            (PENDING_REVIEW_DIR / filename).write_text(content, encoding="utf-8")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Jira/Confluence one-time seed importer")
    parser.add_argument("--source", choices=["export", "live"], default="export")
    parser.add_argument("--export-dir", type=Path, default=None,
                         help="Directory with jira_issues.json / confluence_pages.json (export mode)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be written, write nothing")
    args = parser.parse_args()

    stats = run_import(args.source, args.export_dir, dry_run=args.dry_run)

    action = "Would write" if args.dry_run else "Wrote"
    print(f"{action} {stats['jira_issues']} Jira issue(s) + {stats['confluence_pages']} Confluence page(s) "
          f"to {PENDING_REVIEW_DIR}/:")
    for name in stats["written"]:
        print(f"  {name}")
    if not args.dry_run:
        print(
            "\nNothing here is indexed yet - wiki/Pending Review/ is excluded from "
            "ingestion. Review each file, add error_family/resolution_runbook/"
            "resolution_outcome if it's an incident, then move it into the right "
            "category folder (Incidents/, Runbooks/, System/, ...) before running "
            "python -m src.ingest."
        )


if __name__ == "__main__":
    main()
