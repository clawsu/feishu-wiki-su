# Feishu API Quick Reference

Base URL: `https://open.feishu.cn`
All requests require: `Authorization: Bearer <tenant_access_token>`

---

## Authentication

| Operation | Method | Path |
|-----------|--------|------|
| Get tenant_access_token | POST | `/open-apis/auth/v3/tenant_access_token/internal` |

Request body: `{"app_id": "...", "app_secret": "..."}`
Read from response: `tenant_access_token` (valid 2 hours)

---

## Wiki API

| Operation | Method | Path |
|-----------|--------|------|
| List wiki spaces | GET | `/open-apis/wiki/v2/spaces` |
| Get wiki space info | GET | `/open-apis/wiki/v2/spaces/{space_id}` |
| *(delete node not in public API)* | — | — |
| Create wiki space | POST | `/open-apis/wiki/v2/spaces` |
| Update space settings | PUT | `/open-apis/wiki/v2/spaces/{space_id}/setting` |
| Add space member | POST | `/open-apis/wiki/v2/spaces/{space_id}/members` |
| Remove space member | DELETE | `/open-apis/wiki/v2/spaces/{space_id}/members/{member_id}` |
| Get node info (resolve obj_token) | GET | `/open-apis/wiki/v2/spaces/get_node?token={node_token}` |
| List child nodes | GET | `/open-apis/wiki/v2/spaces/{space_id}/nodes` |
| Create node | POST | `/open-apis/wiki/v2/spaces/{space_id}/nodes` |
| Move node | POST | `/open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}/move` |
| Rename node | PUT | `/open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}` |
| Move cloud doc into wiki | POST | `/open-apis/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki` |
| Poll async task | GET | `/open-apis/wiki/v2/tasks/{task_id}` |

### Supported obj_type values
`docx` / `doc` / `sheet` / `bitable` / `mindnote` / `slides` / `file`

### Token types — never confuse these

| Token | Source | Used for |
|-------|--------|----------|
| node_token | wiki URL or list-nodes response | wiki structure operations |
| obj_token | get_node response | content operations (read/write doc, bitable, etc.) |
| app_token | obj_token when obj_type = bitable | all bitable API calls |

---

## Bitable API

`app_token` must come from `get_node` response (`obj_token` where `obj_type = bitable`). Never read it directly from a wiki URL.

| Operation | Method | Path |
|-----------|--------|------|
| Get bitable metadata | GET | `/open-apis/bitable/v1/apps/{app_token}` |
| List tables | GET | `/open-apis/bitable/v1/apps/{app_token}/tables` |
| Create table | POST | `/open-apis/bitable/v1/apps/{app_token}/tables` |
| Delete table | DELETE | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}` |
| List fields | GET | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| Create field | POST | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| Update field | PUT | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}` |
| Delete field | DELETE | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}` |
| Get single record | GET | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}` |
| Query records | GET | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records` |
| Batch create records | POST | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create` |
| Update record | PUT | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}` |
| Batch update records | POST | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update` |
| Delete record | DELETE | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}` |
| Batch delete records | POST | `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete` |

### Field type codes

| Code | Type | Code | Type |
|------|------|------|------|
| 1 | Text | 11 | Person |
| 2 | Number | 13 | Phone |
| 3 | Single select | 15 | URL |
| 4 | Multi select | 17 | Attachment |
| 5 | Date | 18 | Link (one-way) |
| 7 | Checkbox | 20 | Formula |

### Limits
- Max records per table: 20,000
- Max records per batch_create call: 500
- Max records per batch_update call: 1,000
- Max records per batch_delete call: 500 (no hard limit stated; batched conservatively)
- Write operations: no concurrent calls on the same table; add 0.5s delay between requests

---

## Sheet (Spreadsheet) API

`spreadsheetToken` = `obj_token` from `get_node` (when `obj_type = "sheet"`).

### Step 1 — Get sheet list (required before read/write)

```
GET /open-apis/sheets/v3/spreadsheets/{spreadsheetToken}/sheets/query
→ Returns array of sheets; each has: sheet_id, title, row_count, column_count
```

`sheet_id` is required for all range operations.

### Step 2 — Read / Write

| Operation | Method | Path |
|-----------|--------|------|
| Read single range | GET | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values/{range}` |
| Read multiple ranges | GET | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values_batch_get?ranges=...` |
| Write single range | PUT | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values` |
| Write multiple ranges | POST | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values_batch_update` |
| Append rows | POST | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values_append` |

### Range format

```
{sheetId}!{startCell}:{endCell}     e.g.  Q7PlXT!A1:C10
{sheetId}!{startCol}:{endCol}       e.g.  Q7PlXT!A:C
{sheetId}                           e.g.  Q7PlXT   (entire sheet)
```

### Write body (single range)

```json
{
  "valueRange": {
    "range": "Q7PlXT!A1:C2",
    "values": [["col1", "col2", "col3"], ["val1", 2, "val3"]]
  }
}
```

### Write body (multiple ranges)

```json
{
  "valueRanges": [
    { "range": "Q7PlXT!A1:B2", "values": [["a", "b"]] },
    { "range": "Q7PlXT!D1:E1", "values": [["x", "y"]] }
  ]
}
```

### Limits

- Single write: max 5000 rows × 100 columns per call
- Each cell: max 40,000 characters (recommended)
- Rate: 100 req/sec; **single spreadsheet must be called serially** (no concurrent writes)
- Required permission: `sheets:spreadsheet` or `drive:drive`

---

## Docx Content API

Use `obj_token` from `get_node` (or from the create-node response) as `document_id`.

| Operation | Method | Path |
|-----------|--------|------|
| Get document blocks | GET | `/open-apis/docx/v1/documents/{document_id}/blocks` |
| Batch insert blocks | POST | `/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` |
| Delete block children | DELETE | `/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_delete` |
| Update block content | PATCH | `/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}` |
| Rename document (patch page block) | PATCH | `/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}` |

### Rename document title

`document_id` and `block_id` are both set to the document token (page block_id = document_id):

```json
{ "update_text_elements": { "elements": [{ "text_run": { "content": "New Title" } }] } }
```

### Chunked write workflow

The docx API has a per-call content limit (~4000 chars per batch). For long content:

1. Split content into chunks of ≤ 3000 characters (break at paragraph boundaries)
2. Call batch-insert for each chunk sequentially; use `parent_id = document_id` (root page block)
3. Each chunk becomes one or more paragraph blocks in the document

### Block structure (text block)

```json
{
  "index": -1,
  "children": [
    {
      "block_type": 2,
      "text": {
        "elements": [
          {
            "text_run": { "content": "<chunk text>" }
          }
        ],
        "style": {}
      }
    }
  ]
}
```

`index: -1` appends at the end. Key points:
- Field name is `text`, **not** `paragraph`
- `text_run` is used directly as a key, **no** `type` wrapper around it

### Required permissions for docx write

- `docx:document` — write content blocks
- `docs:permission.member:transfer` — ownership transfer (optional; requires app version publish)

---

## Common Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| 131005 | Resource not found | Verify space_id / node_token |
| 131006 | Permission denied | Add app as wiki space member or doc collaborator |
| 1254002 | Bitable operation failed | For wiki-hosted bitables, create via wiki node endpoint, not bitable endpoint |
| 1254003 | Wrong app_token | Resolve via get_node; obj_token ≠ node_token |
| 1254291 | Write conflict | Avoid concurrent writes; wait 0.5–1s between requests |
| 1254103 | Record limit exceeded | Max 20,000 records per table |
