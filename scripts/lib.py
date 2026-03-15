#!/usr/bin/env python3
"""
feishu-wiki-su shared library
Provides HTTP helper, auth, and shared constants.

Usage in other scripts:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lib import _api, _get_token, _out, _die, BASE, ICONS
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://open.feishu.cn"
CHUNK_SIZE = 3000   # max chars per plain-text docx chunk
BLOCK_BATCH = 50    # max blocks per docx batch-insert call
ICONS = {
    "docx": "📄", "doc": "📄", "bitable": "📊", "sheet": "📋",
    "mindnote": "🧠", "folder": "📁", "file": "📎", "slides": "📎",
}


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _api(method, path, token=None, body=None, params=None):
    url = BASE + path
    if params:
        cleaned = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(cleaned)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": e.code, "msg": str(e)}


def _out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _die(msg):
    _out({"error": str(msg)})
    sys.exit(1)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_token():
    """Fetch tenant_access_token. Dies with a diagnostic message on failure."""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        _die("FEISHU_APP_ID and FEISHU_APP_SECRET must be set (see SETUP in SKILL.md)")
    resp = _api("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                body={"app_id": app_id, "app_secret": app_secret})
    code = resp.get("code", -1)
    if code == 0:
        return resp["tenant_access_token"]
    msgs = {
        10003: "App not found — check FEISHU_APP_ID",
        10014: "Invalid app secret — check FEISHU_APP_SECRET",
        10019: "App not activated — publish app version (SETUP Step C)",
    }
    _die(msgs.get(code, f"Auth error {code}: {resp.get('msg')}"))
