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
import time
import hashlib
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
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT_DIR, ".feishu-wiki-su-state.json")
OPENCLAW_CONFIG_PATHS = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    os.path.expanduser("~/.openclaw/config.json"),
]


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


# ── Config ────────────────────────────────────────────────────────────────────

def _load_openclaw_config():
    for path in OPENCLAW_CONFIG_PATHS:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {}


def _skill_section():
    cfg = _load_openclaw_config()
    return cfg.get("skills", {}).get("feishu-wiki-su", {})


def _skill_env():
    return _skill_section().get("env", {})


def _skill_config():
    return _skill_section().get("config", {})


def _get_config_value(key, env_name=None, default=""):
    if env_name:
        val = os.environ.get(env_name)
        if val is not None and str(val).strip():
            return str(val).strip()
    cfg = _skill_config()
    val = cfg.get(key)
    if val is None:
        return default
    if isinstance(val, str):
        return val.strip() or default
    return val


def _get_json_config(key, env_name=None, default=None):
    raw = _get_config_value(key, env_name=env_name, default="")
    if not raw:
        return {} if default is None else default
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        _die(f"Invalid JSON in config '{key}'")


def _get_default_target(name=None):
    targets = _get_json_config("targets_json", env_name="FEISHU_TARGETS_JSON", default={})
    if name:
        target = targets.get(name)
        if not isinstance(target, dict):
            _die(f"Unknown target alias: {name}")
        return {
            "target_name": name,
            "space_id": str(target.get("space_id", "")).strip(),
            "root_node_token": str(target.get("root_node_token", "")).strip(),
        }
    return {
        "target_name": "",
        "space_id": _get_config_value("default_space_id", env_name="FEISHU_DEFAULT_SPACE_ID", default=""),
        "root_node_token": _get_config_value(
            "default_root_node_token", env_name="FEISHU_DEFAULT_ROOT_NODE_TOKEN", default=""
        ),
    }


def _get_owner_openid():
    return _get_config_value("owner_openid", env_name="FEISHU_OWNER_OPENID", default="")


# ── Local state ───────────────────────────────────────────────────────────────

def _load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("permission_checks", {})
                    data.setdefault("permission_failures", {})
                    return data
    except Exception:
        pass
    return {"permission_checks": {}, "permission_failures": {}}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def _permission_cache_key(app_id, space_id, node_token):
    raw = f"{app_id}:{space_id}:{node_token}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _get_cached_permission_check(app_id, space_id, node_token):
    state = _load_state()
    return state.get("permission_checks", {}).get(_permission_cache_key(app_id, space_id, node_token))


def _set_cached_permission_check(app_id, space_id, node_token, payload):
    state = _load_state()
    state.setdefault("permission_checks", {})
    payload = dict(payload)
    payload["cached_at"] = int(time.time())
    state["permission_checks"][_permission_cache_key(app_id, space_id, node_token)] = payload
    _save_state(state)


def _set_permission_failure(app_id, space_id, node_token, payload):
    state = _load_state()
    state.setdefault("permission_failures", {})
    payload = dict(payload)
    payload["recorded_at"] = int(time.time())
    state["permission_failures"][_permission_cache_key(app_id, space_id, node_token)] = payload
    _save_state(state)


def _get_permission_failure(app_id, space_id, node_token):
    state = _load_state()
    return state.get("permission_failures", {}).get(_permission_cache_key(app_id, space_id, node_token))


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_credentials():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    source = "env"
    if app_id and app_secret:
        return app_id, app_secret, source

    skill_env = _skill_env()
    app_id = str(skill_env.get("FEISHU_APP_ID", "")).strip()
    app_secret = str(skill_env.get("FEISHU_APP_SECRET", "")).strip()
    source = "openclaw.skills.feishu-wiki-su.env"
    if app_id and app_secret:
        return app_id, app_secret, source

    channels = _load_openclaw_config().get("channels", {}).get("feishu", {})
    app_id = str(channels.get("appId", "")).strip()
    app_secret = str(channels.get("appSecret", "")).strip()
    source = "openclaw.channels.feishu"
    return app_id, app_secret, source


def _get_token():
    """Fetch tenant_access_token. Dies with a diagnostic message on failure."""
    app_id, app_secret, _source = _get_credentials()
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
