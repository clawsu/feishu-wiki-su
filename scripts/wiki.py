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
from lib import (
    _api,
    _get_token,
    _out,
    _die,
    _get_credentials,
    _get_default_target,
    _get_owner_openid,
    _get_cached_permission_check,
    _set_cached_permission_check,
    _get_permission_failure,
    _set_permission_failure,
)
from docx import _do_write_impl, _transfer_owner_impl


# ── Credential check ──────────────────────────────────────────────────────────

def do_token(_a):
    app_id, app_secret, source = _get_credentials()
    if not app_id or not app_secret:
        _out({"ok": False, "error": "FEISHU_APP_ID and FEISHU_APP_SECRET must be set"})
        return
    from lib import _api as api
    resp = api("POST", "/open-apis/auth/v3/tenant_access_token/internal",
               body={"app_id": app_id, "app_secret": app_secret})
    code = resp.get("code", -1)
    if code == 0:
        _out({"ok": True, "tenant_access_token": resp["tenant_access_token"],
              "expire_seconds": resp.get("expire"), "credential_source": source})
    else:
        msgs = {
            10003: "App not found — check FEISHU_APP_ID",
            10014: "Invalid app secret — check FEISHU_APP_SECRET",
            10019: "App not activated — publish app version (SETUP Step C)",
        }
        _out({"ok": False, "code": code, "msg": msgs.get(code, resp.get("msg")), "credential_source": source})


def _resolve_target_inputs(target_name="", space_id="", node_token=""):
    default_target = _get_default_target(target_name or None)
    resolved_space_id = (space_id or default_target.get("space_id") or "").strip()
    resolved_node_token = (node_token or default_target.get("root_node_token") or "").strip()
    return {
        "target_name": target_name or default_target.get("target_name", ""),
        "space_id": resolved_space_id,
        "root_node_token": resolved_node_token,
    }


def _extract_node_token(raw):
    if not raw:
        return ""
    return raw.rstrip("/").split("/")[-1].split("?")[0]


def _resolve_node(tok, node_token):
    resp = _api("GET", "/open-apis/wiki/v2/spaces/get_node", token=tok, params={"token": node_token})
    if resp.get("code") != 0:
        return None, resp
    return resp.get("data", {}).get("node", {}), resp


def _resolve_space_id(tok, target_name="", space_id="", node_token=""):
    resolved = _resolve_target_inputs(target_name=target_name, space_id=space_id, node_token=node_token)
    node = None
    if resolved["root_node_token"]:
        node, resp = _resolve_node(tok, resolved["root_node_token"])
        if not node:
            _die(f"resolve target node failed: {resp}")
        if not resolved["space_id"]:
            resolved["space_id"] = node.get("space_id", "")
    if not resolved["space_id"]:
        _die("No space_id configured. Set default_space_id or provide --space-id/--target")
    return resolved, node


def do_check_connection(a):
    app_id, app_secret, source = _get_credentials()
    if not app_id or not app_secret:
        _out({
            "ok": False,
            "credential_source": source,
            "msg": "FEISHU_APP_ID and FEISHU_APP_SECRET must be set",
        })
        return

    resp = _api("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                body={"app_id": app_id, "app_secret": app_secret})
    if resp.get("code") != 0:
        _out({
            "ok": False,
            "credential_source": source,
            "code": resp.get("code"),
            "msg": resp.get("msg"),
        })
        return

    tok = resp["tenant_access_token"]
    resolved = _resolve_target_inputs(target_name=a.target, space_id=a.space_id, node_token=a.node_token)
    node = None
    space_status = {"configured": bool(resolved["space_id"])}
    node_status = {"configured": bool(resolved["root_node_token"])}

    if resolved["root_node_token"]:
        node, node_resp = _resolve_node(tok, resolved["root_node_token"])
        node_status.update({
            "ok": bool(node),
            "code": node_resp.get("code", 0 if node else -1),
            "msg": node_resp.get("msg", "ok" if node else "node resolve failed"),
            "node": node or {},
        })
        if node and not resolved["space_id"]:
            resolved["space_id"] = node.get("space_id", "")
            space_status["configured"] = bool(resolved["space_id"])

    if resolved["space_id"]:
        space_resp = _api("GET", f"/open-apis/wiki/v2/spaces/{resolved['space_id']}", token=tok)
        space_status.update({
            "ok": space_resp.get("code") == 0,
            "code": space_resp.get("code", 0),
            "msg": space_resp.get("msg", "ok"),
            "space": space_resp.get("data", {}).get("space", {}),
        })

    _out({
        "ok": True,
        "credential_source": source,
        "token_expires_in": resp.get("expire"),
        "resolved_target": resolved,
        "space_check": space_status,
        "root_node_check": node_status,
        "owner_openid": _get_owner_openid(),
    })


def do_resolve_target(a):
    tok = _get_token()
    resolved = _resolve_target_inputs(
        target_name=a.target,
        space_id=a.space_id,
        node_token=_extract_node_token(a.node_token),
    )
    node = None
    if resolved["root_node_token"]:
        node, resp = _resolve_node(tok, resolved["root_node_token"])
        if not node:
            _die(f"resolve target node failed: {resp}")
        if not resolved["space_id"]:
            resolved["space_id"] = node.get("space_id", "")
    _out({"ok": True, "resolved_target": resolved, "node": node or {}})


def _probe_docx(tok, document_id):
    resp = _api("GET", f"/open-apis/docx/v1/documents/{document_id}/blocks",
                token=tok, params={"page_size": 1})
    return {"ok": resp.get("code") == 0, "code": resp.get("code", 0), "msg": resp.get("msg", "ok")}


def _probe_bitable(tok, app_token):
    resp = _api("GET", f"/open-apis/bitable/v1/apps/{app_token}/tables",
                token=tok, params={"page_size": 1})
    return {"ok": resp.get("code") == 0, "code": resp.get("code", 0), "msg": resp.get("msg", "ok")}


def _probe_sheet(tok, spreadsheet_token):
    resp = _api("GET", f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query", token=tok)
    return {"ok": resp.get("code") == 0, "code": resp.get("code", 0), "msg": resp.get("msg", "ok")}


def do_check_permissions(a):
    tok = _get_token()
    app_id, _app_secret, source = _get_credentials()

    input_token = _extract_node_token(a.url_or_token)
    resolved = _resolve_target_inputs(target_name=a.target, space_id="", node_token=input_token)
    node_token = resolved.get("root_node_token", "")
    if not node_token:
        _die("Provide a wiki URL/node_token or configure default_root_node_token")

    node, node_resp = _resolve_node(tok, node_token)
    if not node:
        failure = {
            "ok": False,
            "credential_source": source,
            "stage": "get-node",
            "node_token": node_token,
            "code": node_resp.get("code", -1),
            "msg": node_resp.get("msg", "get-node failed"),
            "log_id": node_resp.get("log_id", ""),
        }
        _set_permission_failure(app_id, "", node_token, failure)
        _out(failure)
        return

    space_id = node.get("space_id", "")
    if not a.force:
        cached = _get_cached_permission_check(app_id, space_id, node_token)
        if cached and cached.get("ok"):
            _out({
                "ok": True,
                "cached": True,
                "credential_source": source,
                "node_token": node_token,
                "space_id": space_id,
                "cached_result": cached,
            })
            return
        failure = _get_permission_failure(app_id, space_id, node_token)
        if failure and a.show_last_failure:
            _out({
                "ok": False,
                "cached": True,
                "credential_source": source,
                "node_token": node_token,
                "space_id": space_id,
                "last_failure": failure,
            })
            return

    space_resp = _api("GET", f"/open-apis/wiki/v2/spaces/{space_id}", token=tok)
    probes = {
        "wiki_space": {
            "ok": space_resp.get("code") == 0,
            "code": space_resp.get("code", 0),
            "msg": space_resp.get("msg", "ok"),
            "log_id": space_resp.get("log_id", ""),
        },
        "wiki_node": {
            "ok": True,
            "code": 0,
            "msg": "ok",
        },
    }

    obj_type = node.get("obj_type", "")
    obj_token = node.get("obj_token", "")
    if obj_type in ("docx", "doc"):
        probes["content_access"] = _probe_docx(tok, obj_token)
    elif obj_type == "bitable":
        probes["content_access"] = _probe_bitable(tok, obj_token)
    elif obj_type == "sheet":
        probes["content_access"] = _probe_sheet(tok, obj_token)
    else:
        probes["content_access"] = {"ok": True, "code": 0, "msg": f"no extra probe for obj_type={obj_type}"}

    ok = all(v.get("ok") for v in probes.values())
    result = {
        "ok": ok,
        "cached": False,
        "credential_source": source,
        "node_token": node_token,
        "space_id": space_id,
        "obj_token": obj_token,
        "obj_type": obj_type,
        "title": node.get("title", ""),
        "probes": probes,
    }
    if ok:
        _set_cached_permission_check(app_id, space_id, node_token, result)
    else:
        _set_permission_failure(app_id, space_id, node_token, result)
    _out(result)


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
    resolved, _node = _resolve_space_id(tok, target_name=a.target, space_id=a.space_id, node_token="")
    parent = a.parent or resolved.get("root_node_token", "")
    body = {"obj_type": a.type, "title": a.title, "node_type": "origin"}
    if parent:
        body["parent_node_token"] = parent
    resp = _api("POST", f"/open-apis/wiki/v2/spaces/{resolved['space_id']}/nodes",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"create-node failed: {resp}")
    node = resp.get("data", {}).get("node", {})
    _out({
        "ok": True,
        "space_id": resolved["space_id"],
        "parent_node_token": parent,
        "node_token": node.get("node_token"),
        "obj_token": node.get("obj_token"),
        "obj_type": node.get("obj_type"),
        "title": node.get("title"),
    })


def do_create_doc(a):
    tok = _get_token()
    resolved, _node = _resolve_space_id(tok, target_name=a.target, space_id=a.space_id, node_token="")
    parent = a.parent or resolved.get("root_node_token", "")
    content = a.content if a.content else sys.stdin.read()
    if not content.strip():
        _die("No content — use --content or pipe via stdin")

    create_body = {"obj_type": "docx", "title": a.title, "node_type": "origin"}
    if parent:
        create_body["parent_node_token"] = parent
    resp = _api("POST", f"/open-apis/wiki/v2/spaces/{resolved['space_id']}/nodes",
                token=tok, body=create_body)
    if resp.get("code") != 0:
        _die(f"create-doc failed: {resp}")

    node = resp.get("data", {}).get("node", {})
    document_id = node.get("obj_token", "")
    write_result = _do_write_impl(tok, document_id, content, a.format)

    owner_openid = "" if a.no_transfer_owner else (a.owner_openid or _get_owner_openid())
    transfer_result = None
    if owner_openid:
        transfer_result = _transfer_owner_impl(tok, document_id, owner_openid, a.old_owner_perm)

    _out({
        "ok": True,
        "space_id": resolved["space_id"],
        "parent_node_token": parent,
        "node_token": node.get("node_token"),
        "document_id": document_id,
        "title": node.get("title"),
        "write_result": write_result,
        "owner_transfer": transfer_result,
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
    resp = _api("POST",
                f"/open-apis/wiki/v2/spaces/{a.space_id}/nodes/{a.node_token}/update_title",
                token=tok, body={"title": a.title})
    if resp.get("code") != 0:
        _die(f"rename-node failed: {resp}")
    _out({"ok": True, "space_id": a.space_id, "node_token": a.node_token, "title": a.title})


# ── Members ───────────────────────────────────────────────────────────────────

def do_add_member(a):
    """Add a member to a wiki space by email/openid/userid/unionid."""
    tok = a.access_token or _get_token()
    member_type = a.member_type or ("email" if a.email else "")
    member_id = a.member_id or a.email
    if not member_type or not member_id:
        _die("Provide --email or both --member-type and --member-id")
    resp = _api("POST", f"/open-apis/wiki/v2/spaces/{a.space_id}/members",
                token=tok,
                body={"member_type": member_type, "member_id": member_id, "member_role": a.role})
    if resp.get("code") != 0:
        _die(f"add-member failed: {resp}")
    member = resp.get("data", {}).get("member", {})
    _out({
        "ok": True,
        "member": member,
        "request": {"member_type": member_type, "member_id": member_id, "role": a.role},
        "note": "save member.member_id for use with remove-member",
    })


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
    c = sp.add_parser("check-connection", help="Verify credentials and the default/selected wiki target")
    c.add_argument("--target", default=None, help="Named target from targets_json")
    c.add_argument("--space-id", dest="space_id", default="", help="Override space_id")
    c.add_argument("--node-token", dest="node_token", default="", help="Override root node token")
    c = sp.add_parser("check-permissions", help="Probe wiki/content permissions and cache the first successful result")
    c.add_argument("url_or_token", nargs="?", help="Wiki URL or bare node_token; defaults to configured root node")
    c.add_argument("--target", default=None, help="Named target from targets_json")
    c.add_argument("--force", action="store_true", help="Ignore cached success and probe again")
    c.add_argument("--show-last-failure", action="store_true",
                   help="Return the last recorded failure from local state if success is not cached")
    sp.add_parser("spaces", help="List all wiki spaces")

    c = sp.add_parser("resolve-target", help="Resolve default target or a named target alias")
    c.add_argument("--target", default=None, help="Named target from targets_json")
    c.add_argument("--space-id", dest="space_id", default="", help="Override space_id")
    c.add_argument("--node-token", dest="node_token", default="", help="Override root node token")

    c = sp.add_parser("get-space", help="Get detailed info for a single wiki space")
    c.add_argument("space_id")

    c = sp.add_parser("nodes", help="List nodes in a wiki space")
    c.add_argument("space_id")
    c.add_argument("--parent", metavar="NODE_TOKEN")

    c = sp.add_parser("get-node", help="Resolve node_token → space_id + obj_token")
    c.add_argument("node_token")

    c = sp.add_parser("create-node", help="Create a wiki node")
    c.add_argument("space_id", nargs="?")
    c.add_argument("--title", required=True)
    c.add_argument("--type", default="docx",
                   choices=["docx", "bitable", "sheet", "mindnote", "slides", "file"])
    c.add_argument("--parent", metavar="NODE_TOKEN")
    c.add_argument("--target", default=None, help="Named target from targets_json; falls back to default target")

    c = sp.add_parser("create-doc", help="Create a docx node, write content, optionally transfer ownership")
    c.add_argument("space_id", nargs="?")
    c.add_argument("--title", required=True)
    c.add_argument("--content", help="Content to write (omit to read from stdin)")
    c.add_argument("--format", choices=["auto", "plain", "md"], default="auto")
    c.add_argument("--parent", metavar="NODE_TOKEN")
    c.add_argument("--target", default=None, help="Named target from targets_json; falls back to default target")
    c.add_argument("--owner-openid", dest="owner_openid", default="", help="Override configured owner openid")
    c.add_argument("--old-owner-perm", dest="old_owner_perm", default="view",
                   choices=["view", "edit", "full_access"])
    c.add_argument("--no-transfer-owner", action="store_true",
                   help="Skip automatic owner transfer even if owner_openid is configured")

    c = sp.add_parser("move-node", help="Move a node to a new parent")
    c.add_argument("space_id")
    c.add_argument("node_token")
    c.add_argument("--target-parent", required=True, dest="target_parent", metavar="TOKEN")

    c = sp.add_parser("rename-node", help="Rename a wiki node")
    c.add_argument("space_id")
    c.add_argument("node_token")
    c.add_argument("--title", required=True)

    c = sp.add_parser("add-member", help="Add a member to a wiki space")
    c.add_argument("space_id")
    c.add_argument("--email", help="Shortcut for --member-type email --member-id <email>")
    c.add_argument("--member-id", dest="member_id", default="",
                   help="Member identifier such as email/openid/userid/unionid")
    c.add_argument("--member-type", dest="member_type", default="",
                   choices=["openid", "unionid", "userid", "email"],
                   help="Type of member_id; defaults to email when --email is used")
    c.add_argument("--role", default="member", choices=["member", "admin"])
    c.add_argument("--access-token", dest="access_token", default="",
                   help="Optional access token override. Use a knowledge-space admin user_access_token when adding an app openid")

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
        "check-connection": do_check_connection,
        "check-permissions": do_check_permissions,
        "spaces":        do_spaces,
        "resolve-target": do_resolve_target,
        "get-space":     do_get_space,
        "nodes":         do_nodes,
        "get-node":      do_get_node,
        "create-node":   do_create_node,
        "create-doc":    do_create_doc,
        "move-node":     do_move_node,
        "rename-node":   do_rename_node,
        "add-member":    do_add_member,
        "remove-member": do_remove_member,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
