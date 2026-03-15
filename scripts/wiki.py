#!/usr/bin/env python3
"""
feishu-wiki-su — Wiki operations
Commands: token, spaces, get-space, nodes, get-node, create-node, move-node,
          rename-node, add-member, remove-member

Usage: python3 scripts/wiki.py <command> [options]
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import _api, _get_token, _out, _die


# ── Credential check ──────────────────────────────────────────────────────────

def do_token(_a):
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        _out({"ok": False, "error": "FEISHU_APP_ID and FEISHU_APP_SECRET must be set"})
        return
    from lib import _api as api
    resp = api("POST", "/open-apis/auth/v3/tenant_access_token/internal",
               body={"app_id": app_id, "app_secret": app_secret})
    code = resp.get("code", -1)
    if code == 0:
        _out({"ok": True, "tenant_access_token": resp["tenant_access_token"],
              "expire_seconds": resp.get("expire")})
    else:
        msgs = {
            10003: "App not found — check FEISHU_APP_ID",
            10014: "Invalid app secret — check FEISHU_APP_SECRET",
            10019: "App not activated — publish app version (SETUP Step C)",
        }
        _out({"ok": False, "code": code, "msg": msgs.get(code, resp.get("msg"))})


# ── Spaces ────────────────────────────────────────────────────────────────────

def do_get_space(a):
    """Get detailed info for a single wiki space."""
    tok = _get_token()
    resp = _api("GET", f"/open-apis/wiki/v2/spaces/{a.space_id}", token=tok)
    if resp.get("code") != 0:
        _die(f"get-space failed: {resp}")
    _out(resp.get("data", {}).get("space", {}))


def do_spaces(_a):
    """List all wiki spaces (auto-paginated)."""
    tok = _get_token()
    params = {"page_size": 50}
    items = []
    while True:
        resp = _api("GET", "/open-apis/wiki/v2/spaces", token=tok, params=params)
        if resp.get("code") != 0:
            _die(f"list spaces failed: {resp}")
        data = resp.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        params["page_token"] = data["page_token"]
    _out({"total": len(items), "items": items})


# ── Nodes ─────────────────────────────────────────────────────────────────────

def do_nodes(a):
    tok = _get_token()
    params = {"page_size": 50}
    if a.parent:
        params["parent_node_token"] = a.parent
    items = []
    while True:
        resp = _api("GET", f"/open-apis/wiki/v2/spaces/{a.space_id}/nodes",
                    token=tok, params=params)
        if resp.get("code") != 0:
            _die(f"list nodes failed: {resp}")
        data = resp.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        params["page_token"] = data["page_token"]
    _out({"items": items, "total": len(items)})


def do_get_node(a):
    tok = _get_token()
    resp = _api("GET", "/open-apis/wiki/v2/spaces/get_node",
                token=tok, params={"token": a.node_token})
    if resp.get("code") != 0:
        _die(f"get-node failed: {resp}")
    _out(resp.get("data", {}).get("node", {}))


def do_create_node(a):
    tok = _get_token()
    body = {"obj_type": a.type, "title": a.title, "node_type": "origin"}
    if a.parent:
        body["parent_node_token"] = a.parent
    resp = _api("POST", f"/open-apis/wiki/v2/spaces/{a.space_id}/nodes",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"create-node failed: {resp}")
    node = resp.get("data", {}).get("node", {})
    _out({
        "ok": True,
        "node_token": node.get("node_token"),
        "obj_token": node.get("obj_token"),
        "obj_type": node.get("obj_type"),
        "title": node.get("title"),
    })


def do_move_node(a):
    tok = _get_token()
    resp = _api("POST",
                f"/open-apis/wiki/v2/spaces/{a.space_id}/nodes/{a.node_token}/move",
                token=tok, body={"target_parent_token": a.target_parent})
    if resp.get("code") != 0:
        _die(f"move-node failed: {resp}")
    _out({"ok": True, "node": resp.get("data", {}).get("node", {})})


def do_rename_node(a):
    tok = _get_token()
    resp = _api("PUT",
                f"/open-apis/wiki/v2/spaces/{a.space_id}/nodes/{a.node_token}",
                token=tok, body={"title": a.title})
    if resp.get("code") != 0:
        _die(f"rename-node failed: {resp}")
    _out({"ok": True, "node": resp.get("data", {}).get("node", {})})


# ── Members ───────────────────────────────────────────────────────────────────

def do_add_member(a):
    """Add a member by email. Response includes member_id (openid) needed for remove-member."""
    tok = _get_token()
    resp = _api("POST", f"/open-apis/wiki/v2/spaces/{a.space_id}/members",
                token=tok,
                body={"member_type": "email", "member_id": a.email, "role": a.role})
    if resp.get("code") != 0:
        _die(f"add-member failed: {resp}")
    member = resp.get("data", {}).get("member", {})
    _out({"ok": True, "member": member,
          "note": "save member.member_id (openid) for use with remove-member"})


def do_remove_member(a):
    """Remove a member. --member-type defaults to 'openid' (use the member_id from add-member)."""
    tok = _get_token()
    # Per API: member_type and member_role must be in the request body, not query params
    resp = _api("DELETE",
                f"/open-apis/wiki/v2/spaces/{a.space_id}/members/{a.member_id}",
                token=tok, body={"member_type": a.member_type, "member_role": a.member_role})
    if resp.get("code") != 0:
        _die(f"remove-member failed: {resp}")
    _out({"ok": True, "removed_member_id": a.member_id})


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="wiki",
        description="Feishu wiki spaces, nodes, and members",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("token", help="Verify credentials and show token")
    sp.add_parser("spaces", help="List all wiki spaces")

    c = sp.add_parser("get-space", help="Get detailed info for a single wiki space")
    c.add_argument("space_id")

    c = sp.add_parser("nodes", help="List nodes in a wiki space")
    c.add_argument("space_id")
    c.add_argument("--parent", metavar="NODE_TOKEN")

    c = sp.add_parser("get-node", help="Resolve node_token → space_id + obj_token")
    c.add_argument("node_token")

    c = sp.add_parser("create-node", help="Create a wiki node")
    c.add_argument("space_id")
    c.add_argument("--title", required=True)
    c.add_argument("--type", default="docx",
                   choices=["docx", "bitable", "sheet", "mindnote", "slides", "file"])
    c.add_argument("--parent", metavar="NODE_TOKEN")

    c = sp.add_parser("move-node", help="Move a node to a new parent")
    c.add_argument("space_id")
    c.add_argument("node_token")
    c.add_argument("--target-parent", required=True, dest="target_parent", metavar="TOKEN")

    c = sp.add_parser("rename-node", help="Rename a wiki node")
    c.add_argument("space_id")
    c.add_argument("node_token")
    c.add_argument("--title", required=True)

    c = sp.add_parser("add-member", help="Add an email member to a wiki space")
    c.add_argument("space_id")
    c.add_argument("--email", required=True)
    c.add_argument("--role", default="member", choices=["member", "admin"])

    c = sp.add_parser("remove-member", help="Remove a member from a wiki space")
    c.add_argument("space_id")
    c.add_argument("--member-id", required=True, dest="member_id",
                   help="member_id from add-member response (openid format ou_xxx)")
    c.add_argument("--member-type", dest="member_type", default="openid",
                   choices=["openid", "unionid", "userid", "email"],
                   help="Type of member_id (default: openid)")
    c.add_argument("--member-role", dest="member_role", default="member",
                   choices=["member", "admin"],
                   help="Role of the member being removed (default: member)")

    a = p.parse_args()
    {
        "token":         do_token,
        "spaces":        do_spaces,
        "get-space":     do_get_space,
        "nodes":         do_nodes,
        "get-node":      do_get_node,
        "create-node":   do_create_node,
        "move-node":     do_move_node,
        "rename-node":   do_rename_node,
        "add-member":    do_add_member,
        "remove-member": do_remove_member,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
