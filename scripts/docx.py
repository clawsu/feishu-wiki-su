#!/usr/bin/env python3
"""
feishu-wiki-su — Docx content reading, writing, and ownership transfer
Commands: read, write, append, write-md, blocks, delete-blocks, clear, transfer-owner

Usage: python3 scripts/docx.py <command> [options]

  read  <document_id>                             Extract all text content as structured JSON
  write <document_id> [--content TEXT]            Write content; --format auto|plain|md (default auto)
  append <document_id> [--content TEXT]           Append content; same --format option
  write-md <document_id> [--content TEXT]         Alias for write --format md (backwards compat)
  blocks <document_id>                            List all blocks with IDs and parent relationships
  delete-blocks <document_id> --start N --end M   Delete children[N:M] from a parent block
  clear <document_id>                             Delete ALL content from a docx
  transfer-owner <document_id> --openid ou_xxx    Transfer ownership

document_id = obj_token from wiki.py get-node or create-node response.

Auto-format detection (--format auto, the default):
  Detects Markdown markers (# headings, - bullets, ``` fences, **bold**, etc.)
  If found  → converts via Markdown parser (same as write-md)
  If absent → writes as plain text (chunked at ≤3000 chars)

Overwrite pattern: clear first, then write.
  python3 scripts/docx.py clear <document_id>
  python3 scripts/docx.py write <document_id> --content "new content"
"""
import sys
import os
import re
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import _api, _get_token, _out, _die, CHUNK_SIZE, BLOCK_BATCH


# ── Markdown constants (source: Feishu Open Platform docs) ───────────────────

# field name in block JSON body for each block_type
_BT_FIELD = {
    2:  "text",
    3:  "heading1", 4:  "heading2", 5:  "heading3",
    6:  "heading4", 7:  "heading5", 8:  "heading6",
    9:  "heading7", 10: "heading8", 11: "heading9",
    12: "bullet",   13: "ordered",
    14: "code",     15: "quote",    17: "todo",    22: "divider",
}

# code block language enum (Feishu API; 1 = PlainText fallback)
_LANG = {
    "":           1, "text": 1, "plain": 1, "plaintext": 1,
    "bash":       7,
    "c":         10, "cpp": 9, "c++": 9,
    "dockerfile":18,
    "go":        22,
    "java":      29,
    "javascript":30, "js": 30,
    "json":      28,
    "markdown":  39, "md": 39,
    "php":       43,
    "powershell":46, "ps1": 46,
    "python":    49, "py": 49,
    "r":         50,
    "ruby":      52, "rb": 52,
    "rust":      53,
    "shell":     60, "sh": 60, "zsh": 60,
    "sql":       56,
    "swift":     61,
    "toml":      75,
    "typescript":63, "ts": 63,
    "xml":       66,
    "yaml":      67, "yml": 67,
}

# inline style regex: ** before * to avoid false matches
_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`(.+?)`|\*(.+?)\*|_(.+?)_")

# ordered list: "1." or "1)"
_ORDERED_RE = re.compile(r"^\d+[.)]\s+(.*)")

# Markdown markers used for auto-detection
_MD_LINE_RE = re.compile(r"^(#{1,9} |[-*+] |>\s|\d+[.)]\s|```)")
_MD_INLINE_RE = re.compile(r"\*\*|__|`[^`]")


# ── Format auto-detection ─────────────────────────────────────────────────────

def _looks_like_markdown(text):
    """Heuristic: True if text contains Markdown block or inline markers."""
    for line in text.splitlines():
        if _MD_LINE_RE.match(line.strip()):
            return True
        if _MD_INLINE_RE.search(line):
            return True
    return False


# ── Inline parser ─────────────────────────────────────────────────────────────

def _parse_inline(text):
    """Convert inline Markdown to a list of text_run elements."""
    elements = []
    last = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > last:
            elements.append({"text_run": {"content": text[last:m.start()]}})
        g1, g2, g3, g4, g5 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        if g1 is not None:
            elements.append({"text_run": {"content": g1, "text_element_style": {"bold": True}}})
        elif g2 is not None:
            elements.append({"text_run": {"content": g2, "text_element_style": {"bold": True}}})
        elif g3 is not None:
            elements.append({"text_run": {"content": g3, "text_element_style": {"inline_code": True}}})
        elif g4 is not None:
            elements.append({"text_run": {"content": g4, "text_element_style": {"italic": True}}})
        elif g5 is not None:
            elements.append({"text_run": {"content": g5, "text_element_style": {"italic": True}}})
        last = m.end()
    if last < len(text):
        elements.append({"text_run": {"content": text[last:]}})
    return elements or [{"text_run": {"content": text}}]


# ── Markdown → block list ─────────────────────────────────────────────────────

def _md_to_blocks(text):
    """
    Convert Markdown to a list of Feishu block dicts.
    Supported → block_type:
      # H1–H9        → 3–11    heading1–heading9
      - / * / + item → 12      bullet
      1. / 1) item   → 13      ordered
      - [ ] task     → 17      todo (done=false)
      - [x] task     → 17      todo (done=true)
      > text         → 15      quote
      ```lang … ```  → 14      code  (language from _LANG table)
      ---            → 22      divider
      plain text     → 2       text
      (empty line)   → skipped

    Inline: **bold** __bold__ *italic* _italic_ `inline code`
    NOT supported: tables, images, links, nested lists (see references/templates.md)
    """
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()

        # fenced code block
        if s.startswith("```"):
            lang_code = _LANG.get(s[3:].strip().lower(), 1)
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "block_type": 14,
                "code": {
                    "elements": [{"text_run": {"content": "\n".join(code_lines)}}],
                    "style": {"language": lang_code, "wrap": False},
                },
            })
            i += 1
            continue

        # divider: 3+ identical - * _ chars on one line
        if len(s) >= 3 and s[0] in ("-", "*", "_") and all(c == s[0] for c in s):
            blocks.append({"block_type": 22, "divider": {}})
            i += 1
            continue

        # headings # through #########
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            if 1 <= level <= 9 and len(s) > level and s[level] == " ":
                bt = 2 + level
                field = _BT_FIELD[bt]
                blocks.append({
                    "block_type": bt,
                    field: {"elements": _parse_inline(s[level + 1:]), "style": {}},
                })
                i += 1
                continue

        # todo: - [ ] / - [x]
        if s.startswith("- [") and len(s) >= 6 and s[3] in (" ", "x", "X") and s[4] == "]":
            done = s[3].lower() == "x"
            blocks.append({
                "block_type": 17,
                "todo": {"elements": _parse_inline(s[6:].lstrip()), "style": {"done": done}},
            })
            i += 1
            continue

        # bullet list
        if len(s) >= 2 and s[0] in ("-", "*", "+") and s[1] == " ":
            blocks.append({
                "block_type": 12,
                "bullet": {"elements": _parse_inline(s[2:]), "style": {}},
            })
            i += 1
            continue

        # ordered list
        m = _ORDERED_RE.match(s)
        if m:
            blocks.append({
                "block_type": 13,
                "ordered": {"elements": _parse_inline(m.group(1)), "style": {}},
            })
            i += 1
            continue

        # blockquote
        if s.startswith("> "):
            blocks.append({
                "block_type": 15,
                "quote": {"elements": _parse_inline(s[2:]), "style": {}},
            })
            i += 1
            continue

        # empty line
        if not s:
            i += 1
            continue

        # plain text paragraph
        blocks.append({
            "block_type": 2,
            "text": {"elements": _parse_inline(s), "style": {}},
        })
        i += 1

    return blocks


# ── Write helpers ─────────────────────────────────────────────────────────────

def _split_chunks(text, size=CHUNK_SIZE):
    """Split text at paragraph/line boundaries for plain-text chunked writes."""
    chunks = []
    while len(text) > size:
        cut = text.rfind("\n\n", 0, size)
        if cut < 0:
            cut = text.rfind("\n", 0, size)
        if cut < 0:
            cut = size
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text.strip():
        chunks.append(text)
    return chunks


def _write_plain_block(tok, document_id, content):
    """POST a single plain-text block (block_type 2)."""
    body = {
        "index": -1,
        "children": [{
            "block_type": 2,
            "text": {
                "elements": [{"text_run": {"content": content}}],
                "style": {},
            },
        }],
    }
    return _api("POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                token=tok, body=body)


def _write_blocks_batch(tok, document_id, blocks):
    """POST Markdown-derived blocks in batches of BLOCK_BATCH."""
    for start in range(0, len(blocks), BLOCK_BATCH):
        batch = blocks[start:start + BLOCK_BATCH]
        body = {"index": -1, "children": batch}
        resp = _api("POST",
                    f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                    token=tok, body=body)
        if resp.get("code") != 0:
            end = start + len(batch)
            _die(f"write failed at batch {start // BLOCK_BATCH + 1} "
                 f"(blocks {start + 1}–{end}): {resp}")
    return len(blocks)


def _do_write_impl(tok, document_id, content, fmt):
    """Shared write logic for write/append/write-md."""
    if fmt == "auto":
        fmt = "md" if _looks_like_markdown(content) else "plain"

    if fmt == "md":
        blocks = _md_to_blocks(content)
        if not blocks:
            _die("No blocks generated — check Markdown syntax (see references/templates.md)")
        written = _write_blocks_batch(tok, document_id, blocks)
        return {"ok": True, "document_id": document_id, "format": "markdown", "blocks_written": written}
    else:
        chunks = _split_chunks(content)
        for i, chunk in enumerate(chunks):
            resp = _write_plain_block(tok, document_id, chunk)
            if resp.get("code") != 0:
                _die(f"write chunk {i + 1}/{len(chunks)} failed: {resp}")
        return {"ok": True, "document_id": document_id, "format": "plain", "chunks_written": len(chunks)}


# ── Read helper ───────────────────────────────────────────────────────────────

# block types that carry text content and their field name
_BT_TEXT_FIELD = {
    2: "text",
    3: "heading1", 4: "heading2",  5: "heading3",
    6: "heading4", 7: "heading5",  8: "heading6",
    9: "heading7", 10: "heading8", 11: "heading9",
    12: "bullet",  13: "ordered",  15: "quote",   17: "todo",
}


def _blocks_paginate(tok, document_id):
    """Return all blocks from a document (fully paginated)."""
    params = {"page_size": 500}
    all_blocks = []
    while True:
        resp = _api("GET", f"/open-apis/docx/v1/documents/{document_id}/blocks",
                    token=tok, params=params)
        if resp.get("code") != 0:
            _die(f"blocks list failed: {resp}")
        data = resp.get("data", {})
        all_blocks.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        params["page_token"] = data["page_token"]
    return all_blocks


# ── Commands ──────────────────────────────────────────────────────────────────

def do_read(a):
    """
    Extract all text content from a docx, fully paginated.
    Returns structured JSON with one entry per text-bearing block.
    Useful for checking existing content before appending/overwriting.
    """
    tok = _get_token()
    all_blocks = _blocks_paginate(tok, a.document_id)

    extracted = []
    for b in all_blocks:
        bt = b.get("block_type")
        field = _BT_TEXT_FIELD.get(bt)
        if field and field in b:
            elements = b[field].get("elements", [])
            text = "".join(el.get("text_run", {}).get("content", "") for el in elements)
            if text.strip():
                extracted.append({"block_type": bt, "block_id": b.get("block_id"), "text": text})
        elif bt == 14:  # code block
            elements = b.get("code", {}).get("elements", [])
            text = "".join(el.get("text_run", {}).get("content", "") for el in elements)
            lang_enum = b.get("code", {}).get("style", {}).get("language", 1)
            extracted.append({"block_type": bt, "block_id": b.get("block_id"),
                               "language_enum": lang_enum, "text": text})
        elif bt == 22:  # divider
            extracted.append({"block_type": bt, "block_id": b.get("block_id"), "text": "---"})

    _out({"total_blocks": len(all_blocks), "text_blocks": len(extracted), "content": extracted})


def do_write(a):
    """
    Write content into a docx.
    --format auto (default): auto-detect Markdown vs plain text.
    --format md:    force Markdown conversion.
    --format plain: force plain text (no Markdown parsing).
    """
    tok = _get_token()
    content = a.content if a.content else sys.stdin.read()
    if not content.strip():
        _die("No content — use --content or pipe via stdin")
    _out(_do_write_impl(tok, a.document_id, content, a.format))


def do_append(a):
    """Append content (index=-1 always appends). Same --format option as write."""
    do_write(a)


def do_write_md(a):
    """Backwards-compat alias for write --format md."""
    tok = _get_token()
    content = a.content if a.content else sys.stdin.read()
    if not content.strip():
        _die("No content — use --content or pipe via stdin")
    _out(_do_write_impl(tok, a.document_id, content, "md"))


def do_blocks(a):
    """List all blocks in a docx document (fully paginated)."""
    tok = _get_token()
    all_blocks = _blocks_paginate(tok, a.document_id)
    _out({"total": len(all_blocks), "blocks": all_blocks})


def do_delete_blocks(a):
    """Delete children[start_index:end_index] from a parent block.

    The page (root) block's ID equals the document_id.
    To delete top-level blocks at positions 2 and 3:
      --start 2 --end 4   (end is exclusive, like Python slices)
    """
    tok = _get_token()
    parent = a.parent_block_id or a.document_id
    body = {"start_index": a.start, "end_index": a.end}
    resp = _api("DELETE",
                f"/open-apis/docx/v1/documents/{a.document_id}/blocks/{parent}/children/batch_delete",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"delete-blocks failed: {resp}")
    _out({"ok": True, "parent_block_id": parent,
          "deleted_range": f"[{a.start}, {a.end})"})


def do_clear(a):
    """Delete ALL content blocks from a docx (useful during debugging/overwrite).

    Paginates fully to get accurate top-level block count, then deletes all at once.
    Keeps the empty page structure; the document stays open/accessible.
    """
    tok = _get_token()
    # paginate ALL blocks to accurately count top-level children
    all_blocks = _blocks_paginate(tok, a.document_id)
    top_count = sum(1 for b in all_blocks if b.get("parent_id") == a.document_id)
    if top_count == 0:
        _out({"ok": True, "message": "Document already empty", "deleted": 0})
        return
    body = {"start_index": 0, "end_index": top_count}
    resp = _api("DELETE",
                f"/open-apis/docx/v1/documents/{a.document_id}/blocks/{a.document_id}/children/batch_delete",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"clear failed: {resp}")
    _out({"ok": True, "deleted": top_count})


def do_rename(a):
    """Update document title by patching the page block.

    The page block's block_id equals the document_id, so both path params are
    the same value. Uses update_text_elements to replace the title text.
    """
    tok = _get_token()
    body = {
        "update_text_elements": {
            "elements": [{"text_run": {"content": a.title}}]
        }
    }
    resp = _api("PATCH",
                f"/open-apis/docx/v1/documents/{a.document_id}/blocks/{a.document_id}",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"rename failed: {resp}")
    _out({"ok": True, "document_id": a.document_id, "title": a.title})


def do_transfer_owner(a):
    tok = _get_token()
    # Per API: control flags go in query params; only member identity in body
    params = {
        "type": "docx",
        "need_notification": "false",
        "remove_old_owner": "false",
        "stay_put": "false",
        "old_owner_perm": a.old_owner_perm,
    }
    body = {"member_type": "openid", "member_id": a.openid}
    resp = _api("POST",
                f"/open-apis/drive/v1/permissions/{a.document_id}/members/transfer_owner",
                token=tok, params=params, body=body)
    code = resp.get("code", -1)
    if code == 0:
        _out({"ok": True, "document_id": a.document_id, "new_owner": a.openid})
    elif code in (403, 99991663):
        _out({"ok": False, "code": code,
              "msg": "Permission denied — enable docs:permission.member:transfer "
                     "and publish app version (SETUP Steps B–C)"})
    else:
        _die(f"transfer-owner failed: {resp}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="docx",
        description="Feishu docx read/write and ownership transfer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp = p.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("read", help="Extract all text content as structured JSON (fully paginated)")
    c.add_argument("document_id", help="obj_token from wiki.py get-node or create-node")

    c = sp.add_parser("write",
                      help="Write content (auto-detects Markdown vs plain; use --format to override)")
    c.add_argument("document_id", help="obj_token from wiki.py get-node or create-node")
    c.add_argument("--content", help="Content to write (omit to read from stdin)")
    c.add_argument("--format", choices=["auto", "plain", "md"], default="auto",
                   help="auto (default): detect Markdown; md: force Markdown; plain: force plain text")

    c = sp.add_parser("append", help="Append content — same as write (index=-1 always appends)")
    c.add_argument("document_id")
    c.add_argument("--content")
    c.add_argument("--format", choices=["auto", "plain", "md"], default="auto",
                   help="auto (default): detect Markdown; md: force Markdown; plain: force plain text")

    c = sp.add_parser("write-md",
                      help="Write Markdown (alias for write --format md — backwards compat)")
    c.add_argument("document_id")
    c.add_argument("--content", help="Markdown text (omit to read from stdin)")

    c = sp.add_parser("blocks", help="List all blocks with IDs, types, and parent relationships")
    c.add_argument("document_id")

    c = sp.add_parser("delete-blocks",
                      help="Delete a range of children from a parent block (end index is exclusive)")
    c.add_argument("document_id")
    c.add_argument("--start", type=int, required=True, help="Start index (0-based, inclusive)")
    c.add_argument("--end", type=int, required=True, help="End index (exclusive)")
    c.add_argument("--parent-block-id", dest="parent_block_id", default=None,
                   help="Parent block ID (defaults to document_id = page/root block)")

    c = sp.add_parser("clear",
                      help="Delete ALL content from a docx (paginated count; use before overwriting)")
    c.add_argument("document_id")

    c = sp.add_parser("rename", help="Update document title (patches the page block)")
    c.add_argument("document_id")
    c.add_argument("--title", required=True, help="New document title")

    c = sp.add_parser("transfer-owner", help="Transfer docx ownership to a user")
    c.add_argument("document_id")
    c.add_argument("--openid", required=True, help="New owner openid (ou_xxx)")
    c.add_argument("--old-owner-perm", dest="old_owner_perm", default="view",
                   choices=["view", "edit", "full_access"])

    a = p.parse_args()
    {
        "read":           do_read,
        "write":          do_write,
        "append":         do_append,
        "write-md":       do_write_md,
        "blocks":         do_blocks,
        "delete-blocks":  do_delete_blocks,
        "clear":          do_clear,
        "rename":         do_rename,
        "transfer-owner": do_transfer_owner,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
