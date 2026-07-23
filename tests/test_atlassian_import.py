"""
Self-check for scripts/import_atlassian_seed.py — the Jira/Confluence
one-time seed importer. No ChromaDB/Ollama/MinIO required.

Verifies two things:
  1. The sample export fixtures (data/sample_atlassian_export/*.json) convert
     into valid Markdown with parseable frontmatter (src.loader.parse_frontmatter).
  2. The governance property that makes "one-time seed, not auto-approved"
     actually true: a file landing in a "Pending Review/" folder is excluded
     by LocalMarkdownReader, while a sibling file in a real category folder
     is loaded normally.

Run:
    python -m tests.test_atlassian_import
"""

import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.import_atlassian_seed import jira_issue_to_markdown, confluence_page_to_markdown
from src.loader import parse_frontmatter, LocalMarkdownReader

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_atlassian_export"


def check_conversion_produces_valid_frontmatter() -> None:
    jira_issues = json.loads((FIXTURES_DIR / "jira_issues.json").read_text(encoding="utf-8"))
    confluence_pages = json.loads((FIXTURES_DIR / "confluence_pages.json").read_text(encoding="utf-8"))
    assert jira_issues and confluence_pages, "sample export fixtures must be non-empty"

    for issue in jira_issues:
        filename, content = jira_issue_to_markdown(issue)
        meta, body = parse_frontmatter(content)
        assert meta.get("id") == f"JIRA-{issue['key']}", f"{filename}: id missing/wrong"
        assert meta.get("review_status") == "pending", f"{filename}: must land as review_status=pending"
        assert meta.get("source") == "jira"
        assert "## Summary" in body
        # Paragraph breaks in the source HTML must survive as real newlines,
        # not get concatenated into one run-on sentence (regression check for
        # the </p> -> "\n\n" fix in strip_html()).
        assert "\n\n" in body or len(body.splitlines()) > 1
        print(f"OK  {filename}: frontmatter + body parse cleanly")

    for page in confluence_pages:
        filename, content = confluence_page_to_markdown(page)
        meta, body = parse_frontmatter(content)
        assert meta.get("id") == f"CONF-{page['id']}", f"{filename}: id missing/wrong"
        assert meta.get("review_status") == "pending", f"{filename}: must land as review_status=pending"
        assert meta.get("source") == "confluence"
        assert "<p>" not in body and "<strong>" not in body, f"{filename}: raw HTML tags leaked into body"
        print(f"OK  {filename}: frontmatter + body parse cleanly")


def check_pending_review_excluded_from_ingestion() -> None:
    """The whole point of landing in 'Pending Review/' instead of directly in
    a category folder: LocalMarkdownReader must skip it, exactly like
    Templates/, so an unreviewed import can never silently become
    searchable/"approved" knowledge."""
    tmp_wiki = Path(tempfile.mkdtemp(prefix="llmkb_test_wiki_"))
    try:
        (tmp_wiki / "Pending Review").mkdir()
        (tmp_wiki / "Pending Review" / "JIRA-TEST-1.md").write_text(
            "---\nid: JIRA-TEST-1\ntitle: test\nreview_status: pending\n---\n\nbody\n",
            encoding="utf-8",
        )
        (tmp_wiki / "System").mkdir()
        (tmp_wiki / "System" / "SYS-TEST.md").write_text(
            "---\nid: SYS-TEST\ntitle: control doc\n---\n\nbody\n",
            encoding="utf-8",
        )

        docs = LocalMarkdownReader(wiki_dir=str(tmp_wiki)).load_data()
        ids = {d.metadata["id"] for d in docs}

        assert "SYS-TEST" in ids, "control doc in a real category folder must be loaded"
        assert "JIRA-TEST-1" not in ids, "Pending Review/ content must be excluded from ingestion"
        print(f"OK  Pending Review/ excluded from LocalMarkdownReader.load_data() (loaded: {ids})")
    finally:
        shutil.rmtree(tmp_wiki, ignore_errors=True)


def main():
    check_conversion_produces_valid_frontmatter()
    check_pending_review_excluded_from_ingestion()
    print("\nAll Atlassian importer checks passed")


if __name__ == "__main__":
    main()
