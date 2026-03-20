#!/usr/bin/env python3
"""
feishu-wiki-su — Bitable (multi-dimensional table) operations
Commands: tables, create-table, delete-table, bootstrap-table, fields, query,
          add, batch-update, delete, batch-delete, clean-empty-records

Usage: python3 scripts/bitable.py <command> [options]

IMPORTANT: app_token = obj_token from wiki.py get-node (when obj_type == "bitable")
           Never use the node_token from a wiki URL directly as app_token.

Limits (from Feishu API docs):
  batch_create : max 500 records/call  — script auto-splits with 0.5s delay
  batch_update : max 1000 records/call — script auto-splits with 0.5s delay
  batch_delete : no hard limit stated  — batched at 500 with 0.5s delay
  total records: 20,000 per table
  total tables : 100 per bitable app
  fields       : 300 per table (formula: max 100)
  write conflict (1254291): no concurrent writes to same table; 0.5s delay enforced
"""
import sys
import os
import json
import time
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import _api, _get_token, _out, _die

_WRITE_DELAY = 0.5   # seconds between consecutive write batches (avoids error 1254291)
_ADD_BATCH   = 500   # max records per batch_create call
_UPD_BATCH   = 1000  # max records per batch_update call
_DEL_BATCH   = 500   # batch size for batch_delete


def _is_empty_value(value):
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _is_empty_record(record):
    fields = record.get("fields", {})
    if not fields:
        return True
    return all(_is_empty_value(v) for v in fields.values())


# ── Pagination helper ─────────────────────────────────────────────────────────

def _paginate(tok, path, result_key, extra_params=None):
    """Fetch all pages from a list endpoint. Returns list of items."""
    params = {"page_size": 100}
    if extra_params:
        params.update(extra_params)
    items = []
    while True:
        resp = _api("GET", path, token=tok, params=params)
        if resp.get("code") != 0:
            _die(f"API error on {path}: {resp}")
        data = resp.get("data", {})
        items.extend(data.get(result_key, []))
        if not data.get("has_more"):
            break
        params["page_token"] = data["page_token"]
    return items


def _list_tables(tok, app_token):
    return _paginate(tok, f"/open-apis/bitable/v1/apps/{app_token}/tables", "items")


def _batch_delete_record_ids(tok, app_token, table_id, record_ids):
    all_deleted = []
    for start in range(0, len(record_ids), _DEL_BATCH):
        batch = record_ids[start:start + _DEL_BATCH]
        resp = _api("POST",
                    f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}"
                    "/records/batch_delete",
                    token=tok, body={"records": batch})
        if resp.get("code") != 0:
            _die(f"batch-delete failed at batch {start // _DEL_BATCH + 1}: {resp}")
        all_deleted.extend(resp.get("data", {}).get("records", []))
        if start + _DEL_BATCH < len(record_ids):
            time.sleep(_WRITE_DELAY)
    return all_deleted


# ── Table operations ──────────────────────────────────────────────────────────

def do_tables(a):
    """List all tables (all pages)."""
    tok = _get_token()
    items = _list_tables(tok, a.app_token)
    _out({"total": len(items), "items": items})


def do_create_table(a):
    """
    Create a table. First field must be type 1/2/5/13/15/20/22 (text/number/date/phone/url/formula/geo).
    Field type quick ref: 1=Text 2=Number 3=SingleSelect 4=MultiSelect 5=Date 7=Checkbox
                          11=Person 13=Phone 15=URL 17=Attachment 18=Link 20=Formula
    SingleSelect/MultiSelect fields need property.options: [{"name":"opt","color":0}]
    """
    tok = _get_token()
    table = {"name": a.name}
    if a.default_view:
        table["default_view_name"] = a.default_view
    if a.fields_json:
        table["fields"] = json.loads(a.fields_json)
    resp = _api("POST", f"/open-apis/bitable/v1/apps/{a.app_token}/tables",
                token=tok, body={"table": table})
    if resp.get("code") != 0:
        _die(f"create-table failed: {resp}")
    d = resp.get("data", {})
    _out({
        "ok": True,
        "table_id":       d.get("table_id"),
        "default_view_id": d.get("default_view_id"),
        "field_id_list":  d.get("field_id_list", []),
    })


def do_delete_table(a):
    """Delete a table by table_id. IRREVERSIBLE."""
    tok = _get_token()
    resp = _api("DELETE",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"delete-table failed: {resp}")
    _out({"ok": True, "deleted_table_id": a.table_id})


def do_bootstrap_table(a):
    """
    Create a clean table with a caller-controlled primary field and optional schema.
    Optionally replace Feishu's single default table to avoid placeholder fields and
    empty example rows.
    """
    tok = _get_token()
    before = _list_tables(tok, a.app_token)

    if a.fields_json:
        fields = json.loads(a.fields_json)
        if not isinstance(fields, list) or not fields:
            _die("--fields-json must be a non-empty JSON array")
    else:
        fields = [{"field_name": a.primary_name, "type": 1}]

    table = {"name": a.name, "fields": fields}
    if a.default_view:
        table["default_view_name"] = a.default_view
    resp = _api("POST", f"/open-apis/bitable/v1/apps/{a.app_token}/tables",
                token=tok, body={"table": table})
    if resp.get("code") != 0:
        _die(f"bootstrap-table create failed: {resp}")

    data = resp.get("data", {})
    created_table_id = data.get("table_id")
    dropped_default_table_id = ""
    replace_note = ""

    if a.replace_single_default:
        if len(before) == 1 and before[0].get("name") in ("Table", "数据表"):
            default_id = before[0].get("table_id")
            del_resp = _api("DELETE",
                            f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{default_id}",
                            token=tok)
            if del_resp.get("code") == 0:
                dropped_default_table_id = default_id
            else:
                replace_note = f"created clean table but failed to delete default table: {del_resp}"
        elif len(before) == 1:
            replace_note = f"existing single table '{before[0].get('name')}' not treated as default"
        else:
            replace_note = "replace-single-default skipped because app had multiple tables before create"

    cleaned = {"records_deleted": 0, "deleted_ids": []}
    if a.clean_empty:
        items = _paginate(tok,
                          f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{created_table_id}/records",
                          "items")
        empty_ids = [item.get("record_id") for item in items if _is_empty_record(item) and item.get("record_id")]
        if empty_ids:
            deleted = _batch_delete_record_ids(tok, a.app_token, created_table_id, empty_ids)
            cleaned = {"records_deleted": len(deleted), "deleted_ids": deleted}

    _out({
        "ok": True,
        "table_id": created_table_id,
        "default_view_id": data.get("default_view_id"),
        "field_id_list": data.get("field_id_list", []),
        "dropped_default_table_id": dropped_default_table_id,
        "replace_note": replace_note,
        "clean_empty": cleaned,
    })


# ── Field operations ──────────────────────────────────────────────────────────

def do_fields(a):
    """List all fields in a table (all pages)."""
    tok = _get_token()
    items = _paginate(tok,
                      f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/fields",
                      "items")
    _out({"total": len(items), "items": items})


def do_create_field(a):
    """
    Create a field in a table.
    Type codes: 1=Text 2=Number 3=SingleSelect 4=MultiSelect 5=Date 7=Checkbox
                11=Person 13=Phone 15=URL 17=Attachment 18=Link 20=Formula
    For SingleSelect/MultiSelect: --property-json '{"options":[{"name":"A","color":0}]}'
    """
    tok = _get_token()
    body = {"field_name": a.name, "type": a.type}
    if a.property_json:
        body["property"] = json.loads(a.property_json)
    resp = _api("POST",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/fields",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"create-field failed: {resp}")
    field = resp.get("data", {}).get("field", {})
    _out({"ok": True, "field_id": field.get("field_id"),
          "field_name": field.get("field_name"), "type": field.get("type")})


def do_update_field(a):
    """
    Update a field (full overwrite — must supply both --name and --type).
    The primary/index field can be renamed but not have its type changed.
    """
    tok = _get_token()
    body = {"field_name": a.name, "type": a.type}
    if a.property_json:
        body["property"] = json.loads(a.property_json)
    resp = _api("PUT",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/fields/{a.field_id}",
                token=tok, body=body)
    if resp.get("code") != 0:
        _die(f"update-field failed: {resp}")
    field = resp.get("data", {}).get("field", {})
    _out({"ok": True, "field_id": field.get("field_id"),
          "field_name": field.get("field_name"), "type": field.get("type")})


def do_delete_field(a):
    """Delete a field. The primary/index field cannot be deleted (error 1254046)."""
    tok = _get_token()
    resp = _api("DELETE",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/fields/{a.field_id}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"delete-field failed: {resp}")
    _out({"ok": True, "deleted_field_id": a.field_id})


# ── Record operations ─────────────────────────────────────────────────────────

def do_get_record(a):
    """Get a single record by record_id."""
    tok = _get_token()
    resp = _api("GET",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records/{a.record_id}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"get-record failed: {resp}")
    _out(resp.get("data", {}).get("record", {}))


def do_query(a):
    """
    Query records with full auto-pagination.
    Returns ALL matching records by default.
    Use --limit N to cap the total returned.
    """
    tok = _get_token()
    params = {"page_size": min(a.page_size, 500)}
    if a.filter:
        params["filter"] = a.filter
    if a.view_id:
        params["view_id"] = a.view_id

    items = []
    while True:
        resp = _api("GET",
                    f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records",
                    token=tok, params=params)
        if resp.get("code") != 0:
            _die(f"query failed: {resp}")
        data = resp.get("data", {})
        batch = data.get("items", [])
        if a.skip_empty:
            batch = [item for item in batch if not _is_empty_record(item)]
        items.extend(batch)

        # honour --limit
        if a.limit and len(items) >= a.limit:
            items = items[:a.limit]
            break

        if not data.get("has_more"):
            break
        params["page_token"] = data["page_token"]

    _out({"total": len(items), "items": items})


# ── Record write operations ───────────────────────────────────────────────────

def do_add(a):
    """
    Batch create records. Auto-splits into chunks of 500 with 0.5s delay between
    batches to avoid write conflict (error 1254291).
    Input: [{"fields": {"FieldName": value, ...}}, ...]
    """
    tok = _get_token()
    records = json.loads(a.records_json)
    if not isinstance(records, list):
        _die("--records-json must be a JSON array: [{\"fields\":{...}}, ...]")

    all_created = []
    for start in range(0, len(records), _ADD_BATCH):
        batch = records[start:start + _ADD_BATCH]
        resp = _api("POST",
                    f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}"
                    "/records/batch_create",
                    token=tok, body={"records": batch})
        if resp.get("code") != 0:
            _die(f"add failed at batch {start // _ADD_BATCH + 1} "
                 f"(records {start + 1}–{start + len(batch)}): {resp}")
        all_created.extend(resp.get("data", {}).get("records", []))
        if start + _ADD_BATCH < len(records):
            time.sleep(_WRITE_DELAY)

    _out({"ok": True, "records_created": len(all_created), "records": all_created})


def do_update(a):
    """Update a single record (incremental — only specified fields are changed)."""
    tok = _get_token()
    fields = json.loads(a.fields_json)
    resp = _api("PUT",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}"
                f"/records/{a.record_id}",
                token=tok, body={"fields": fields})
    if resp.get("code") != 0:
        _die(f"update failed: {resp}")
    _out({"ok": True, "record": resp.get("data", {}).get("record", {})})


def do_batch_update(a):
    """
    Batch update records. Auto-splits into chunks of 1000 with 0.5s delay.
    Input: [{"record_id": "recXXX", "fields": {...}}, ...]
    """
    tok = _get_token()
    records = json.loads(a.records_json)
    if not isinstance(records, list):
        _die("--records-json must be a JSON array: [{\"record_id\":\"...\",\"fields\":{...}}, ...]")

    all_updated = []
    for start in range(0, len(records), _UPD_BATCH):
        batch = records[start:start + _UPD_BATCH]
        resp = _api("POST",
                    f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}"
                    "/records/batch_update",
                    token=tok, body={"records": batch})
        if resp.get("code") != 0:
            _die(f"batch-update failed at batch {start // _UPD_BATCH + 1}: {resp}")
        all_updated.extend(resp.get("data", {}).get("records", []))
        if start + _UPD_BATCH < len(records):
            time.sleep(_WRITE_DELAY)

    _out({"ok": True, "records_updated": len(all_updated), "records": all_updated})


def do_delete(a):
    """Delete a single record."""
    tok = _get_token()
    resp = _api("DELETE",
                f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}"
                f"/records/{a.record_id}",
                token=tok)
    if resp.get("code") != 0:
        _die(f"delete failed: {resp}")
    _out({"ok": True, "deleted": a.record_id})


def do_batch_delete(a):
    """
    Batch delete records by record_id list. Auto-splits at 500 with 0.5s delay.
    Input: ["recXXX", "recYYY", ...]
    """
    tok = _get_token()
    record_ids = json.loads(a.record_ids_json)
    if not isinstance(record_ids, list):
        _die("--record-ids-json must be a JSON array: [\"recXXX\", \"recYYY\"]")

    all_deleted = _batch_delete_record_ids(tok, a.app_token, a.table_id, record_ids)
    _out({"ok": True, "records_deleted": len(all_deleted), "deleted_ids": all_deleted})


def do_clean_empty_records(a):
    """
    Delete records whose fields are fully empty.
    Useful right after creating a new Feishu bitable when the default table
    contains placeholder/example rows with no actual values.
    """
    tok = _get_token()
    items = _paginate(tok,
                      f"/open-apis/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records",
                      "items")
    empty_ids = [item.get("record_id") for item in items if _is_empty_record(item) and item.get("record_id")]
    if not empty_ids:
        _out({"ok": True, "records_deleted": 0, "deleted_ids": [], "message": "no empty records found"})
        return

    all_deleted = _batch_delete_record_ids(tok, a.app_token, a.table_id, empty_ids)
    _out({"ok": True, "records_deleted": len(all_deleted), "deleted_ids": all_deleted})


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="bitable",
        description="Feishu bitable CRUD — auto-paginates reads, auto-splits writes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp = p.add_subparsers(dest="cmd", required=True)

    # tables
    c = sp.add_parser("tables", help="List all tables (auto-paginated)")
    c.add_argument("app_token", help="obj_token from wiki.py get-node (obj_type=bitable)")

    # create-table
    c = sp.add_parser("create-table", help="Create a table")
    c.add_argument("app_token")
    c.add_argument("--name", required=True)
    c.add_argument("--default-view", dest="default_view", default=None,
                   help="Default view name (requires --fields-json)")
    c.add_argument("--fields-json", dest="fields_json", default=None,
                   help='[{"field_name":"Name","type":1},{"field_name":"Status","type":3,'
                        '"property":{"options":[{"name":"Done","color":0}]}}]')

    c = sp.add_parser("bootstrap-table", help="Create a clean table and optionally replace Feishu's default table")
    c.add_argument("app_token")
    c.add_argument("--name", required=True, help="Table name")
    c.add_argument("--primary-name", dest="primary_name", default="Name",
                   help="Primary field name when --fields-json is omitted (default: Name)")
    c.add_argument("--fields-json", dest="fields_json", default=None,
                   help='Full clean schema. First field becomes the primary field.')
    c.add_argument("--default-view", dest="default_view", default=None)
    c.add_argument("--replace-single-default", action="store_true",
                   help="If the app only has one default table named Table/数据表, delete it after creating the clean table")
    c.add_argument("--clean-empty", action="store_true",
                   help="Clean fully empty records in the new table after creation")

    # delete-table
    c = sp.add_parser("delete-table", help="Delete a table (IRREVERSIBLE)")
    c.add_argument("app_token")
    c.add_argument("table_id")

    # fields
    c = sp.add_parser("fields", help="List all fields in a table (auto-paginated)")
    c.add_argument("app_token")
    c.add_argument("table_id")

    # create-field
    c = sp.add_parser("create-field", help="Create a field in a table")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("--name", required=True, help="Field display name")
    c.add_argument("--type", required=True, type=int,
                   help="Field type code: 1=Text 2=Number 3=SingleSelect 4=MultiSelect "
                        "5=Date 7=Checkbox 11=Person 13=Phone 15=URL 17=Attachment "
                        "18=Link 20=Formula")
    c.add_argument("--property-json", dest="property_json", default=None,
                   help='Field properties JSON, e.g. \'{"options":[{"name":"A","color":0}]}\' '
                        'for select fields')

    # update-field
    c = sp.add_parser("update-field",
                      help="Update a field — full overwrite, must supply --name and --type")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("field_id")
    c.add_argument("--name", required=True, help="New field name")
    c.add_argument("--type", required=True, type=int, help="Field type code (same as create-field)")
    c.add_argument("--property-json", dest="property_json", default=None,
                   help="Updated field properties JSON")

    # delete-field
    c = sp.add_parser("delete-field", help="Delete a field (primary field cannot be deleted)")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("field_id")

    # get-record
    c = sp.add_parser("get-record", help="Get a single record by record_id")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("record_id")

    # query
    c = sp.add_parser("query", help="Query records — fetches ALL pages by default")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("--filter", help='e.g. CurrentValue.[Status]="Done"')
    c.add_argument("--view-id", dest="view_id", default=None)
    c.add_argument("--page-size", type=int, default=500, dest="page_size",
                   help="Records per API call (max 500, default 500)")
    c.add_argument("--limit", type=int, default=0,
                   help="Stop after N total records (0 = fetch all)")
    c.add_argument("--skip-empty", action="store_true",
                   help="Filter out records whose fields are fully empty")

    # add
    c = sp.add_parser("add", help="Batch create records (auto-splits at 500, 0.5s delay)")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("--records-json", required=True, dest="records_json",
                   help='[{"fields":{"Name":"Alice","Score":90}}]')

    # update
    c = sp.add_parser("update", help="Update a single record (incremental)")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("record_id")
    c.add_argument("--fields-json", required=True, dest="fields_json",
                   help='{"Name":"Bob"}  — only listed fields are changed')

    # batch-update
    c = sp.add_parser("batch-update", help="Batch update records (auto-splits at 1000)")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("--records-json", required=True, dest="records_json",
                   help='[{"record_id":"recXXX","fields":{"Name":"Bob"}}]')

    # delete
    c = sp.add_parser("delete", help="Delete a single record")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("record_id")

    # batch-delete
    c = sp.add_parser("batch-delete", help="Batch delete records (auto-splits at 500)")
    c.add_argument("app_token")
    c.add_argument("table_id")
    c.add_argument("--record-ids-json", required=True, dest="record_ids_json",
                   help='["recXXX","recYYY"]')

    c = sp.add_parser("clean-empty-records", help="Delete all fully empty records in a table")
    c.add_argument("app_token")
    c.add_argument("table_id")

    a = p.parse_args()
    {
        "tables":        do_tables,
        "create-table":  do_create_table,
        "delete-table":  do_delete_table,
        "bootstrap-table": do_bootstrap_table,
        "fields":        do_fields,
        "create-field":  do_create_field,
        "update-field":  do_update_field,
        "delete-field":  do_delete_field,
        "get-record":    do_get_record,
        "query":         do_query,
        "add":           do_add,
        "update":        do_update,
        "batch-update":  do_batch_update,
        "delete":        do_delete,
        "batch-delete":  do_batch_delete,
        "clean-empty-records": do_clean_empty_records,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
