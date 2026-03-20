#!/usr/bin/env python3
"""
feishu-wiki-su — Recursive wiki scan → Markdown report
Usage: python3 scripts/scan.py <wiki_url_or_node_token>

Accepts a full Feishu wiki URL or a bare node_token.
Outputs a Markdown report following references/report-format.md.
"""
import sys
import os
import argparse
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import _api, _get_token, _die, ICONS, _get_default_target


# ── Helpers ───────────────────────────────────────────────────────────────────

def _list_all_nodes(tok, space_id, parent_token=""):
    """Recursively list all descendant nodes under parent_token."""
    params = {"page_size": 50, "parent_node_token": parent_token}
    nodes = []
    while True:
        resp = _api("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
                    token=tok, params=params)
        if resp.get("code") != 0:
            break
        data = resp.get("data", {})
        for n in data.get("items", []):
            nodes.append(n)
            if n.get("has_child"):
                nodes.extend(_list_all_nodes(tok, space_id, n["node_token"]))
        if not data.get("has_more"):
            break
        params["page_token"] = data.get("page_token", "")
    return nodes


def _docx_preview(tok, obj_token):
    """Return a short text preview of a docx node, or None on permission error."""
    resp = _api("GET", f"/open-apis/docx/v1/documents/{obj_token}/blocks",
                token=tok, params={"page_size": 20})
    if resp.get("code") != 0:
        return None
    texts = []
    for b in resp.get("data", {}).get("items", []):
        if b.get("block_type") == 2:
            for el in b.get("text", {}).get("elements", []):
                t = el.get("text_run", {}).get("content", "").strip()
                if t:
                    texts.append(t)
        if len(texts) >= 5:
            break
    joined = " ".join(texts)
    return (joined[:150] + "…") if len(joined) > 150 else joined


def _classify(preview):
    if preview is None:
        return "🔒 No permission"
    if not preview or len(preview) < 10:
        return "⚠️ Empty"
    if any(k in preview for k in ["待补充", "编写中", "TODO", "🚧", "WIP", "Draft"]):
        return "🚧 In progress"
    return "✅ Complete"


def _build_tree(nodes, parent_token, prefix=""):
    children = [n for n in nodes if n.get("parent_node_token", "") == parent_token]
    lines = []
    for i, n in enumerate(children):
        last = i == len(children) - 1
        icon = ICONS.get(n.get("obj_type", ""), "📎")
        connector = "└── " if last else "├── "
        lines.append(f"{prefix}{connector}{icon} {n.get('title', '(untitled)')}")
        child_prefix = prefix + ("    " if last else "│   ")
        lines.extend(_build_tree(nodes, n["node_token"], child_prefix))
    return lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="scan",
        description="Recursively scan a wiki space and output a Markdown summary report",
    )
    p.add_argument("url", nargs="?", help="Feishu wiki URL or bare node_token; defaults to configured root node")
    p.add_argument("--target", default=None, help="Named target from targets_json")
    a = p.parse_args()

    tok = _get_token()

    # extract node_token from URL or use as-is
    if a.url:
        raw = a.url.rstrip("/").split("/")[-1].split("?")[0]
    else:
        raw = _get_default_target(a.target).get("root_node_token", "")
        if not raw:
            _die("No node token provided and no default_root_node_token configured")

    root_resp = _api("GET", "/open-apis/wiki/v2/spaces/get_node",
                     token=tok, params={"token": raw})
    if root_resp.get("code") != 0:
        _die(f"get_node failed: {root_resp}")

    root = root_resp["data"]["node"]
    space_id = root["space_id"]
    root_title = root.get("title", "Wiki")

    nodes = _list_all_nodes(tok, space_id, raw)

    # collect docx previews and stats
    summaries = {}
    stats = {"total": len(nodes), "complete": 0, "in_progress": 0, "empty": 0, "no_permission": 0}
    stat_map = {
        "✅ Complete": "complete", "🚧 In progress": "in_progress",
        "⚠️ Empty": "empty", "🔒 No permission": "no_permission",
    }
    for n in nodes:
        if n.get("obj_type") == "docx":
            preview = _docx_preview(tok, n.get("obj_token", ""))
            st = _classify(preview)
            summaries[n["node_token"]] = {"preview": preview or "", "status": st}
            stats[stat_map.get(st, "empty")] += 1

    # build report
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {root_title} — Wiki Summary Report", "",
        f"**Source:** {a.url}",
        f"**Generated:** {now}",
        f"**Total nodes:** {stats['total']}",
        "", "---", "", "## Directory Structure", "",
        root_title,
    ]
    lines.extend(_build_tree(nodes, raw))
    lines += ["", "---", "", "## Content Summaries", ""]

    for i, n in enumerate(nodes, 1):
        nt = n.get("node_token", "")
        obj = n.get("obj_type", "unknown")
        icon = ICONS.get(obj, "📎")
        lines.append(f"### {i}. {icon} {n.get('title', '(untitled)')}")
        lines.append(f"- **Type:** {obj}")
        if obj == "docx" and nt in summaries:
            s = summaries[nt]
            lines.append(f"- **Status:** {s['status']}")
            if s["preview"]:
                lines.append(f"- **Summary:** {s['preview']}")
        lines.append("")

    lines += [
        "---", "", "## Statistics", "",
        "| Category | Count | Status |",
        "|----------|-------|--------|",
        f"| Total | {stats['total']} | — |",
        f"| Complete | {stats['complete']} | ✅ |",
        f"| In progress | {stats['in_progress']} | 🚧 |",
        f"| Empty | {stats['empty']} | ⚠️ |",
        f"| No permission | {stats['no_permission']} | 🔒 |",
        "", "---", "", "*Generated by feishu-wiki-su*",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
