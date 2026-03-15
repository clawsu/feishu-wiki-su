#!/usr/bin/env python3
"""
feishu-wiki-su — Sheet (spreadsheet) read/write
Commands: list, read, write, append

Usage: python3 scripts/sheet.py <command> [options]

IMPORTANT: spreadsheet_token = obj_token from wiki.py get-node (when obj_type == "sheet")
           Always run 'list' first to get the sheet_id required for range operations.
           Range format: <sheet_id>!<start>:<end>  e.g.  Q7PlXT!A1:C10
"""
import sys
import os
import json
import argparse
import urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import _api, _get_token, _out, _die


# ── Commands ──────────────────────────────────────────────────────────────────

def do_list(a):
    """List all sheets — run this first to get sheet_id values."""
    tok = _get_token()
    resp = _api("GET",
                f"/open-apis/sheets/v3/spreadsheets/{a.spreadsheet_token}/sheets/query",
                token=tok)
    if resp.get("code") != 0:
        _die(f"list failed: {resp}")
    _out(resp.get("data", {}))


def do_read(a):
    tok = _get_token()
    enc = urllib.parse.quote(a.cell_range, safe="")
    resp = _api("GET",
                f"/open-apis/sheets/v2/spreadsheets/{a.spreadsheet_token}/values/{enc}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"read failed: {resp}")
    _out(resp.get("data", {}))


def do_write(a):
    """Overwrite the specified cell range."""
    tok = _get_token()
    values = json.loads(a.values_json)
    body = {"valueRange": {"range": a.cell_range, "values": values}}
    resp = _api("PUT",
                f"/open-apis/sheets/v2/spreadsheets/{a.spreadsheet_token}/values",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"write failed: {resp}")
    d = resp.get("data", {})
    _out({"ok": True, "updatedRange": d.get("updatedRange"), "updatedCells": d.get("updatedCells")})


def do_clear(a):
    """Clear cell values in a range by reading dimensions then writing empty strings."""
    tok = _get_token()
    enc = urllib.parse.quote(a.cell_range, safe="")
    resp = _api("GET",
                f"/open-apis/sheets/v2/spreadsheets/{a.spreadsheet_token}/values/{enc}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"clear failed (read): {resp}")
    values = resp.get("data", {}).get("valueRange", {}).get("values", [])
    if not values:
        _out({"ok": True, "message": "Range already empty"})
        return
    rows = len(values)
    cols = max(len(r) for r in values)
    nulls = [[""] * cols for _ in range(rows)]
    body = {"valueRange": {"range": a.cell_range, "values": nulls}}
    resp2 = _api("PUT",
                 f"/open-apis/sheets/v2/spreadsheets/{a.spreadsheet_token}/values",
                 token=tok, body=body)
    if resp2.get("code") != 0:
        _die(f"clear failed (write): {resp2}")
    _out({"ok": True, "cleared_range": a.cell_range, "rows": rows, "cols": cols})


def do_append(a):
    """Append rows below existing data in the range."""
    tok = _get_token()
    values = json.loads(a.values_json)
    body = {"valueRange": {"range": a.cell_range, "values": values}}
    resp = _api("POST",
                f"/open-apis/sheets/v2/spreadsheets/{a.spreadsheet_token}/values_append",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"append failed: {resp}")
    _out({"ok": True, "updates": resp.get("data", {}).get("updates", {})})


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="sheet",
        description="Feishu spreadsheet read/write (serial calls only — no concurrency)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp = p.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("list", help="List sheets and get sheet_id values (required before read/write)")
    c.add_argument("spreadsheet_token", help="obj_token from wiki.py get-node (obj_type=sheet)")

    c = sp.add_parser("read", help="Read a cell range")
    c.add_argument("spreadsheet_token")
    c.add_argument("cell_range", help='e.g. "Q7PlXT!A1:C10"')

    c = sp.add_parser("write", help="Write to a cell range (overwrites)")
    c.add_argument("spreadsheet_token")
    c.add_argument("cell_range", help='e.g. "Q7PlXT!A1:C2"')
    c.add_argument("--values-json", required=True, dest="values_json",
                   help='2D array: [["col1","col2"],[1,2]]')

    c = sp.add_parser("append", help="Append rows below existing data")
    c.add_argument("spreadsheet_token")
    c.add_argument("cell_range", help='e.g. "Q7PlXT!A:C"')
    c.add_argument("--values-json", required=True, dest="values_json",
                   help='2D array: [["new","row"]]')

    c = sp.add_parser("clear", help="Clear all cell values in a range (writes empty strings)")
    c.add_argument("spreadsheet_token")
    c.add_argument("cell_range", help='e.g. "Q7PlXT!A1:C10"')

    a = p.parse_args()
    {
        "list":   do_list,
        "read":   do_read,
        "write":  do_write,
        "append": do_append,
        "clear":  do_clear,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
