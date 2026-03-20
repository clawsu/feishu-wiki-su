---
name: feishu-wiki-su
description: Full Feishu knowledge base management via direct Feishu Open Platform API calls. Covers wiki spaces, nodes, members, bitable (multi-dimensional tables), spreadsheet (sheet) read/write, docx creation with chunked writing, and recursive folder summarization. Trigger on: mentions of Feishu wiki/knowledge base/wiki space/wiki nodes, feishu.cn/wiki/ URLs, requests to create docs/bitables/sheets inside a wiki, manage wiki members or permissions, scan a wiki and generate a summary report, read or write spreadsheet cells inside a wiki, or perform CRUD on bitable records inside a wiki.
author: clawsu
homepage: https://github.com/clawsu/feishu-wiki-su
metadata: {"openclaw":{"requires":{"env":["FEISHU_APP_ID","FEISHU_APP_SECRET"]},"primaryEnv":"FEISHU_APP_ID"}}
---

# Feishu Wiki Su

Calls Feishu Open Platform APIs directly. Does not rely on any OpenClaw built-in Feishu tools.
API quick reference: `references/api.md` — Report format: `references/report-format.md` — Templates & syntax: `references/templates.md`

Scripts (pure stdlib, no external dependencies):
| Script | Covers |
|--------|--------|
| `scripts/wiki.py` | spaces, nodes, members, token check |
| `scripts/docx.py` | read, write, append, write-md, blocks, delete-blocks, clear, rename, transfer-owner |
| `scripts/bitable.py` | tables, fields (CRUD), records (CRUD) |
| `scripts/sheet.py` | list, read, write, append, clear |
| `scripts/scan.py` | recursive wiki scan → Markdown report |
| `scripts/lib.py` | shared HTTP + auth (imported by all above) |

---

## SETUP

First-time setup for new users. Complete all steps before using any feature.

### Step A — Get credentials (reuse Feishu channel app if already configured)

**If you already have the Feishu channel running in OpenClaw**, you can reuse the same app —
no need to create a new one. Find your credentials in `openclaw.json`:

```json
"channels": {
  "feishu": {
    "appId": "cli_xxxxxxxx",
    "appSecret": "xxxxxxxx"
  }
}
```

**If you do not have a Feishu channel yet**, create a new app:
1. Go to https://open.feishu.cn/app → **Create App** → **Enterprise Self-Built App**
2. In the left sidebar → **Credentials & Basic Info** → copy **App ID** and **App Secret**

Either way, set the env vars for this skill:
```
openclaw config set skills.feishu-wiki-su.env.FEISHU_APP_ID     <App ID>
openclaw config set skills.feishu-wiki-su.env.FEISHU_APP_SECRET  <App Secret>
```

> Note: the Feishu channel stores credentials in `channels.feishu.appId` (config),
> while this skill reads them from env vars. They must be set separately even if the
> values are identical.

Optional defaults for a reusable business workflow:
```
openclaw config set skills.feishu-wiki-su.config.default_space_id <space_id>
openclaw config set skills.feishu-wiki-su.config.default_root_node_token <node_token>
openclaw config set skills.feishu-wiki-su.config.owner_openid <ou_xxx>
openclaw config set skills.feishu-wiki-su.config.targets_json '{"product":{"space_id":"<space_id>","root_node_token":"<node_token>"}}'
```

Resolution order:
1. Process env vars
2. `skills.feishu-wiki-su.env` / `skills.feishu-wiki-su.config`
3. `channels.feishu.appId` / `channels.feishu.appSecret` as credential fallback

### Step B — Enable required permissions

In the app console → **Permission Management** → **Enable Permissions**, search and enable:

| Permission scope | Required for |
|-----------------|--------------|
| `wiki:wiki` | All wiki operations (spaces, nodes, members) |
| `docx:document` | Writing content into docx nodes |
| `sheets:spreadsheet` | Reading and writing spreadsheet cells |
| `bitable:app` | Bitable CRUD (tables, records, fields) |
| `docs:permission.member:transfer` | ⚠️ Optional — ownership transfer after docx creation |

Enable at minimum the first four. The fifth is only needed if you want ownership transfer.

### Step C — Publish the app

After enabling permissions:
1. In the app console → **App Release** → **Version Management** → **Create Version**
2. Fill in a version number (e.g. `1.0.0`) → click **Save** → click **Apply for Online Release**
3. Ask your Feishu workspace admin to approve the release

> Without publishing, permissions do not take effect for `tenant_access_token` calls.

### Step D — Add the app as a wiki space member

The app needs explicit membership in each wiki space it will operate on. Without this, all wiki API calls return 403.

1. Open the target wiki space in Feishu
2. Click **···** (top right) → **Settings** → **Members**
3. Click **Add Member** → search for your app name → select it → set role to **Member** (or **Admin** if node creation is needed)
4. Repeat for each wiki space

### Step E — (Optional) Configure ownership transfer

Only needed if you want docx nodes auto-transferred to your personal account after creation:

1. Confirm `docs:permission.member:transfer` is enabled and the app version is published (Step C)
2. Get your personal OpenID:
   - Go to https://open.feishu.cn → **API Debug Console** → search `im:message` → **Send Message**
   - Click **Quick Copy open_id** → select your account → copy the value (starts with `ou_`)
3. Save it:
   ```
   openclaw config set skills.feishu-wiki-su.config.owner_openid <ou_xxx>
   ```

### Setup checklist

- [ ] `FEISHU_APP_ID` and `FEISHU_APP_SECRET` set in OpenClaw config
- [ ] `default_space_id` and/or `default_root_node_token` set for the main wiki target
- [ ] 4 required permissions enabled
- [ ] App version published and approved by admin
- [ ] App added as member to all target wiki spaces
- [ ] (Optional) `owner_openid` configured for ownership transfer

---

## WHEN

Activate this skill when any of the following is true:

- User mentions "Feishu wiki", "knowledge base", "wiki space", "wiki node"
- User provides a `feishu.cn/wiki/` URL
- User wants to create a document, bitable, or any node inside a wiki space
- User wants to manage wiki space members or permissions
- User wants to recursively scan a wiki and generate a summary report
- User wants to read, create, or update records in a bitable that lives inside a wiki

---

## WHAT

Produce one of the following based on user intent:

| User intent | Expected output |
|-------------|-----------------|
| Query wiki spaces or nodes | Structured list with space_id / node_token / obj_type |
| Create a node | Confirm success; return node_token and obj_token |
| Manage members | Confirm operation result |
| Bitable CRUD | Return result: record IDs / count / field list |
| Sheet read / write | Return cell values / confirm rows written |
| Summary report | Full Markdown report per `references/report-format.md` |

Success criterion: after every operation, explicitly report the result and all key identifiers (token / ID / count) to the user.

---

## HOW

### Script quick reference

**Always use the scripts** — they encode all JSON correctly, handle auth/chunking/pagination automatically. Never hand-craft Feishu API JSON.

```bash
# ── wiki.py — spaces, nodes, members ────────────────────────────────────────
python3 scripts/wiki.py token                                           # verify credentials
python3 scripts/wiki.py check-connection                                # verify credentials + default target
python3 scripts/wiki.py check-permissions <wiki_url_or_node_token>      # probe wiki/content access and cache first success
python3 scripts/wiki.py spaces                                          # list all wiki spaces
python3 scripts/wiki.py resolve-target [--target product]               # resolve default target / alias
python3 scripts/wiki.py get-space <space_id>                            # get space details
python3 scripts/wiki.py nodes <space_id> [--parent <node_token>]       # list nodes
python3 scripts/wiki.py get-node <node_token>                           # resolve → obj_token
python3 scripts/wiki.py create-node [<space_id>] --title "T" [--type docx|bitable|sheet] [--parent <token>] [--target product]
python3 scripts/wiki.py create-doc [<space_id>] --title "T" --content "..." [--parent <token>] [--target product]
python3 scripts/wiki.py move-node <space_id> <node_token> --target-parent <token>
python3 scripts/wiki.py rename-node <space_id> <node_token> --title "New Title"
python3 scripts/wiki.py add-member <space_id> --email user@example.com [--role member|admin]
python3 scripts/wiki.py add-member <space_id> --member-type openid --member-id <open_id> [--role member|admin]
python3 scripts/wiki.py add-member <space_id> --member-type openid --member-id <open_id> --role admin --access-token <user_access_token>
python3 scripts/wiki.py remove-member <space_id> --member-id <id> [--member-role member|admin]

# ── docx.py — document content ───────────────────────────────────────────────
# document_id = obj_token from wiki.py get-node or create-node
python3 scripts/docx.py read <document_id>                                    # extract all text content
python3 scripts/docx.py write <document_id> --content "..."                  # auto-detect Markdown/plain
python3 scripts/docx.py write <document_id> --content "..." --format md      # force Markdown conversion
python3 scripts/docx.py write <document_id> --content "..." --format plain   # force plain text
python3 scripts/docx.py append <document_id> --content "more..." [--format auto|plain|md]
cat my-doc.md | python3 scripts/docx.py write <document_id>                  # pipe from file (auto-detect)
python3 scripts/docx.py rename <document_id> --title "New Title"             # update document title
python3 scripts/docx.py blocks <document_id>                                  # list all blocks + IDs
python3 scripts/docx.py delete-blocks <document_id> --start 0 --end 3        # delete blocks[0:3]
python3 scripts/docx.py clear <document_id>                                   # wipe all content (for overwrite)
python3 scripts/docx.py transfer-owner <document_id> --openid ou_xxx [--old-owner-perm view|edit|full_access]

# ── bitable.py — multi-dimensional tables ────────────────────────────────────
# app_token = obj_token from wiki.py get-node (obj_type must be "bitable")
python3 scripts/bitable.py tables <app_token>
python3 scripts/bitable.py create-table <app_token> --name "Name" [--fields-json '[{"field_name":"Name","type":1}]'] [--default-view "Grid"]
python3 scripts/bitable.py delete-table <app_token> <table_id>
python3 scripts/bitable.py fields <app_token> <table_id>
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Score" --type 2
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Status" --type 3 --property-json '{"options":[{"name":"Done","color":0}]}'
python3 scripts/bitable.py update-field <app_token> <table_id> <field_id> --name "New Name" --type 2
python3 scripts/bitable.py delete-field <app_token> <table_id> <field_id>
python3 scripts/bitable.py get-record <app_token> <table_id> <record_id>
python3 scripts/bitable.py query <app_token> <table_id> [--filter 'CurrentValue.[Name]="Alice"'] [--page-size 500] [--limit N]
python3 scripts/bitable.py add <app_token> <table_id> --records-json '[{"fields":{"Name":"Alice","Score":90}}]'
python3 scripts/bitable.py update <app_token> <table_id> <record_id> --fields-json '{"Name":"Bob"}'
python3 scripts/bitable.py batch-update <app_token> <table_id> --records-json '[{"record_id":"recXXX","fields":{"Name":"Bob"}}]'
python3 scripts/bitable.py delete <app_token> <table_id> <record_id>
python3 scripts/bitable.py batch-delete <app_token> <table_id> --record-ids-json '["recXXX","recYYY"]'

# ── sheet.py — spreadsheet read/write ────────────────────────────────────────
# spreadsheet_token = obj_token from wiki.py get-node (obj_type must be "sheet")
# always run 'list' first to get the sheet_id needed for range operations
python3 scripts/sheet.py list <spreadsheet_token>
python3 scripts/sheet.py read <spreadsheet_token> "<sheetId>!A1:C10"
python3 scripts/sheet.py write <spreadsheet_token> "<sheetId>!A1:C2" --values-json '[["a","b"],[1,2]]'
python3 scripts/sheet.py append <spreadsheet_token> "<sheetId>!A:C" --values-json '[["new","row"]]'
python3 scripts/sheet.py clear <spreadsheet_token> "<sheetId>!A1:C10"

# ── scan.py — recursive wiki scan → Markdown report ──────────────────────────
python3 scripts/scan.py https://xxx.feishu.cn/wiki/NodeToken
python3 scripts/scan.py                                                # use default_root_node_token if configured
```

All scripts output JSON (except `scan.py` which outputs Markdown). Credentials read from `FEISHU_APP_ID` and `FEISHU_APP_SECRET` env vars automatically.

---

### Fast routing rules

Follow this order unless the user explicitly asks for a different command:

1. If the user provides a wiki URL:
   - extract `node_token`
   - run `python3 scripts/wiki.py get-node <node_token>`
   - branch on `obj_type`
2. Before the first real operation on a new wiki target:
   - run `python3 scripts/wiki.py check-permissions <wiki_url_or_node_token>`
   - reuse cached success on later runs unless `--force` is needed
3. If the user wants a new doc in the wiki:
   - prefer `python3 scripts/wiki.py create-doc ...`
   - do not split create + write unless there is a good reason
4. If the user wants a new bitable in the wiki:
   - use `python3 scripts/wiki.py create-node --type bitable`
   - never use standalone bitable creation to create the wiki node
5. If the user wants to operate on an existing docx/bitable/sheet:
   - resolve `obj_token` first via `wiki.py get-node`
   - then switch to `docx.py` / `bitable.py` / `sheet.py`
6. Do not claim support for deleting an entire wiki node.
   - This repository does not currently verify a public Feishu node-delete API.

### Verified ability boundary

Verified against a real Feishu wiki space:

- `wiki/docx`: `check-permissions`, `create-doc`, `read`, `append`, `rename`, `rename-node`, `delete-blocks`, `clear`
- `wiki/bitable`: `create-node --type bitable`, `tables`, `fields`, `create-field`, `add`, `update`, `get-record`, `delete`, `delete-field`, `create-table`, `delete-table`

Not yet claimed:

- whole `wiki node` deletion
- `sheet.py` live verification in this repository

---

### Step 0 — Credential errors

Every script command handles auth automatically. If a command fails with an auth error, run:

```bash
python3 scripts/wiki.py token
python3 scripts/wiki.py check-connection
python3 scripts/wiki.py check-permissions <wiki_url_or_node_token>
```

to diagnose — then stop and report to the user:

| Response code | Meaning | Action |
|---------------|---------|--------|
| `"ok": true` | ✅ Credentials valid | Problem is elsewhere |
| `10003` | ❌ Wrong App ID | Ask user to verify `FEISHU_APP_ID` |
| `10014` | ❌ Wrong App Secret | Ask user to verify `FEISHU_APP_SECRET` |
| `10019` | ❌ App not published | Ask user to complete SETUP Step C |
| Other | ❌ Unknown | Report raw code and message |

Do not run `token` as a mandatory pre-flight before every operation — only when an auth failure occurs.

---

### Step 1 — Identify intent and branch

Use this decision order:

1. If the user gives a wiki URL or `node_token`
   - run `python3 scripts/wiki.py get-node <node_token>`
   - inspect `obj_type`
2. If this is the first real operation on that wiki target
   - run `python3 scripts/wiki.py check-permissions <wiki_url_or_node_token>`
   - if it fails, inspect `.feishu-wiki-su-state.json` or rerun with `--show-last-failure`
3. If the user gives no target but the skill has a default target
   - run `python3 scripts/wiki.py resolve-target`
4. Then route by intent:
   - list wiki spaces → `python3 scripts/wiki.py spaces`
   - list nodes in a space → `python3 scripts/wiki.py nodes <space_id> [--parent <token>]`
   - create a new wiki node → Step 2A
   - manage members → Step 2B
   - operate on a bitable → Step 2C
   - summary report → Step 2D
   - read or write docx → Step 2E
   - read or write sheet → Step 2F
   - move or rename a node → Step 2G

---

### Step 2A — Create a node

```bash
python3 scripts/wiki.py create-node [<space_id>] --title "Title" --type docx [--parent <node_token>] [--target product]
```

**Critical constraint**: to create a bitable inside a wiki, you MUST use this command with `--type bitable`.
Never call the standalone bitable creation endpoint — it will fail with error 1254002.

The response includes `node_token` and `obj_token` — return both to the user.

If `<space_id>` is omitted, the command must use `default_space_id` or the `space_id` resolved from the selected default target.
If `--parent` is omitted, the command should use `default_root_node_token` when configured; otherwise create at the wiki root.

If `--type docx` and the user provides content to write → proceed to **Step 2E** using the returned `obj_token` as `document_id`.

---

### Step 2B — Manage members

Add a member:
```bash
python3 scripts/wiki.py add-member <space_id> --email user@example.com --role member
python3 scripts/wiki.py add-member <space_id> --member-type openid --member-id <open_id> --role admin
```

Remove a member:
```bash
python3 scripts/wiki.py remove-member <space_id> --member-id <member_id>
```


---

### Step 2C — Bitable operations

**Resolve app_token first (mandatory)**:
```bash
python3 scripts/wiki.py get-node <node_token>
# Use obj_token from the response as app_token — only valid when obj_type == "bitable"
```

Then run the appropriate bitable command:

```bash
# List tables (auto-paginated)
python3 scripts/bitable.py tables <app_token>

# Create a table with optional field definitions; returns table_id + default_view_id + field_id_list
python3 scripts/bitable.py create-table <app_token> --name "Sprint Tracker"
python3 scripts/bitable.py create-table <app_token> --name "Sprint Tracker" \
  --fields-json '[{"field_name":"Name","type":1},{"field_name":"Score","type":2}]'

# Delete a table (IRREVERSIBLE)
python3 scripts/bitable.py delete-table <app_token> <table_id>

# List fields in a table (auto-paginated)
python3 scripts/bitable.py fields <app_token> <table_id>

# Create a field (type: 1=Text 2=Number 3=SingleSelect 4=MultiSelect 5=Date 7=Checkbox 11=Person 15=URL 20=Formula)
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Score" --type 2
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Status" --type 3 \
  --property-json '{"options":[{"name":"Todo","color":0},{"name":"Done","color":1}]}'

# Update a field (full overwrite — must supply both --name and --type; use fields to get field_id)
python3 scripts/bitable.py update-field <app_token> <table_id> <field_id> --name "New Name" --type 2

# Delete a field (primary/index field cannot be deleted — error 1254046)
python3 scripts/bitable.py delete-field <app_token> <table_id> <field_id>

# Get a single record by ID
python3 scripts/bitable.py get-record <app_token> <table_id> <record_id>

# Query records — fetches ALL pages by default; use --limit to cap total
python3 scripts/bitable.py query <app_token> <table_id>
python3 scripts/bitable.py query <app_token> <table_id> --filter 'CurrentValue.[Status]="Done"' --limit 50

# Add records — auto-splits at 500/batch, 0.5s delay between batches
python3 scripts/bitable.py add <app_token> <table_id> \
  --records-json '[{"fields":{"Name":"Alice","Score":90}},{"fields":{"Name":"Bob","Score":85}}]'

# Update a single record (incremental — only listed fields are changed)
python3 scripts/bitable.py update <app_token> <table_id> <record_id> \
  --fields-json '{"Name":"Alice Updated","Score":95}'

# Batch update records — auto-splits at 1000/batch, 0.5s delay between batches
python3 scripts/bitable.py batch-update <app_token> <table_id> \
  --records-json '[{"record_id":"recXXX","fields":{"Name":"Bob"}},{"record_id":"recYYY","fields":{"Score":100}}]'

# Delete a single record
python3 scripts/bitable.py delete <app_token> <table_id> <record_id>

# Batch delete records — auto-splits at 500/batch, 0.5s delay between batches
python3 scripts/bitable.py batch-delete <app_token> <table_id> \
  --record-ids-json '["recXXX","recYYY","recZZZ"]'
```

All write commands enforce a 0.5s inter-batch delay automatically (avoids write conflict error 1254291).
Read commands (`tables`, `fields`, `query`) auto-paginate with no extra flags needed.

---

### Step 2E — Write content into a wiki-hosted docx

**Default: for a new doc, use `create-doc` to close the flow in one command.**

```bash
python3 scripts/wiki.py create-doc --title "Onboarding Guide" --content "# Title" [--target product]
```

This command:
1. Resolves `space_id` from the explicit arg or configured default target
2. Uses `default_root_node_token` as parent when `--parent` is omitted
3. Creates the docx node
4. Writes the content
5. Transfers ownership automatically if `owner_openid` is configured and transfer is not disabled

**For existing docs, use `docx.py write` — it auto-detects format.**

```bash
# Auto-detect (default) — detects # headings, - bullets, ``` fences, **bold**, etc.
# If Markdown markers found → converts to Feishu blocks; otherwise writes as plain text
python3 scripts/docx.py write <document_id> --content "# Title

## Section

- Bullet
- **Bold item**

\`\`\`python
print('hello')
\`\`\`"

# Pipe from a file (auto-detect applies)
cat my-doc.md | python3 scripts/docx.py write <document_id>

# Force a specific format if auto-detection is wrong
python3 scripts/docx.py write <document_id> --format md    --content "..."
python3 scripts/docx.py write <document_id> --format plain --content "..."
```

`document_id` = `obj_token` from the `create-node` or `get-node` response.

**Read before writing** (to check existing content):
```bash
python3 scripts/docx.py read <document_id>
# Returns: {"total_blocks": N, "text_blocks": M, "content": [{"block_type":2,"text":"..."},...]}
```

**Overwrite pattern** (clear first, then write):
```bash
python3 scripts/docx.py clear <document_id>
python3 scripts/docx.py write <document_id> --content "new content..."
```

- `write`/`append` both append at index=-1; they are functionally identical — use either
- Auto-detection checks for `#`/`-`/`>`/` ``` `/`**`/`` ` `` markers; plain prose without these stays plain
- Unsupported in Markdown mode: tables, image embeds, nested lists, hyperlinks — see `references/templates.md`
- `write-md` kept as an alias for `write --format md`

**Optional: ownership transfer**

If `owner_openid` is configured (format `ou_xxx`), `create-doc` transfers ownership automatically unless `--no-transfer-owner` is set.
For existing docs, after docx-write succeeds:

```bash
python3 scripts/docx.py transfer-owner <document_id> --openid <owner_openid>
# --old-owner-perm defaults to "view"; use "edit" or "full_access" if needed
```

Requires `docs:permission.member:transfer` scope and the app version must be published (SETUP Steps B–C).
On `"ok": false`: skip transfer silently; report the message to user; do not abort.

**Optional: local index update**

After successful creation, append one row to `memory/feishu-wiki-su-index.md`:

```
| {n} | {title} | docx | https://...feishu.cn/docx/{document_id} | {one-line summary} | ✅ Complete | {space_id} |
```

---

### Step 2F — Sheet (spreadsheet) read / write

```bash
# Step 1: resolve spreadsheetToken from wiki URL or create-node response
python3 scripts/wiki.py get-node <node_token>
# Use obj_token as spreadsheetToken

# Step 2: get sheet list (mandatory — needed for sheetId)
python3 scripts/sheet.py list <spreadsheetToken>
# Note the sheet_id of the target sheet

# Step 3: read data
python3 scripts/sheet.py read <spreadsheetToken> "<sheetId>!A1:Z100"

# Step 4: write data (overwrites the specified range)
python3 scripts/sheet.py write <spreadsheetToken> "<sheetId>!A1:C2" \
  --values-json '[["col1","col2","col3"],["val1",2,"val3"]]'

# Step 5: append rows below existing data
python3 scripts/sheet.py append <spreadsheetToken> "<sheetId>!A:C" \
  --values-json '[["new","row","data"]]'
```

**Constraints**: serial writes only (no concurrent calls on the same spreadsheet); max 5000 rows × 100 cols per write call.

---

### Step 2G — Move or rename a node

```bash
# Move a node to a new parent
python3 scripts/wiki.py move-node <space_id> <node_token> --target-parent <new_parent_token>

# Rename a node
python3 scripts/wiki.py rename-node <space_id> <node_token> --title "New Title"
```

---

### Step 2D — Recursive scan and summary report

```bash
python3 scripts/scan.py https://xxx.feishu.cn/wiki/NodeToken
```

The script:
1. Resolves the node → space_id via `get-node`
2. Recursively lists all descendant nodes with pagination
3. Reads docx content for each node to extract preview and status
4. Outputs a full Markdown report per `references/report-format.md`

On 403 for any individual node: marks it as "🔒 No permission" and continues — does not abort the scan.

---

## REFERENCE

### ✅ Good: create a bitable inside a wiki

**User**: "Create a bitable named 'Project Tracker' at the root of wiki space 7034502641455497244."

**Execution**:
```bash
python3 scripts/wiki.py create-node 7034502641455497244 --title "Project Tracker" --type bitable
# → returns node_token: wikcnXXX, obj_token: AW3QXXX  (obj_token = app_token)

python3 scripts/bitable.py create-table AW3QXXX --name "Sheet1" \
  --fields-json '[{"field_name":"Name","type":1},{"field_name":"Status","type":3}]'
# → returns table_id: tblXXX
```

Report back: "✅ Created. node_token: wikcnXXX, app_token: AW3QXXX, table_id: tblXXX"

---

### ✅ Good: recursive wiki scan

**User**: "Scan https://xxx.feishu.cn/wiki/BzslwD3Nei1D and generate a summary report."

**Execution**:
```bash
python3 scripts/scan.py https://xxx.feishu.cn/wiki/BzslwD3Nei1D
```

Output the Markdown report directly to the user. No manual steps needed.

---

### ✅ Good: create a docx node with long content (chunked write)

**User**: "Create a doc titled 'Onboarding Guide' under node wikXXX in space 7034502641455497244 with this 8000-char content: ..."

**Execution**:
```bash
python3 scripts/wiki.py create-node 7034502641455497244 \
  --title "Onboarding Guide" --type docx --parent wikXXX
# → returns obj_token: doxcnXXX (= document_id)

python3 scripts/docx.py write doxcnXXX --content "<8000-char content>"
# script auto-splits into ≤3000-char chunks and writes sequentially

# Optional: transfer ownership if owner_openid configured
python3 scripts/docx.py transfer-owner doxcnXXX --openid ou_xxx
```

Report: "✅ Created. node_token: wikcnXXX, document_id: doxcnXXX, 3 chunks written"

---

### ❌ Bad: using the standalone bitable creation endpoint inside a wiki

**User**: "Use the bitable create API to add a table inside the wiki."

**Correct handling**: Reject this approach. Explain that bitables inside a wiki must be created via the wiki node creation endpoint (`POST /open-apis/wiki/v2/spaces/{space_id}/nodes` with `obj_type: "bitable"`). Using the standalone bitable create endpoint will return error 1254002. Route to Step 2A instead.

---

### ❌ Bad: using the wiki URL token directly as app_token

**User**: "The link is feishu.cn/wiki/AbcToken — use AbcToken to query the bitable."

**Correct handling**: Explain that `AbcToken` in a wiki URL is a `node_token`, not an `app_token`. Call `get_node` first to retrieve `obj_token`, then use that as `app_token` for all bitable API calls.

---

## LIMITS

### Out of scope

- **Sheet formula computation** — API returns raw formula strings by default (use `valueRenderOption=FormattedValue` to get computed values, but cross-sheet references and array formulas are not supported)
- **Mindnote / Slides** content editing — Feishu Open Platform has no public API for reading or writing mindnote / slides content; only node-level wiki operations (create, move, rename) are supported
- **Creating a wiki space** — requires `user_access_token`; ask the user to create it manually and provide the space_id
- **Bulk node deletion** — destructive operation; do not execute
- **Document search / list across all docs** — out of scope; feishu-wiki-su operates on wiki spaces and nodes only

### Ownership transfer prerequisites

Before using ownership transfer (Step 2E optional):
1. App must have `docs:permission.member:transfer` scope enabled
2. A new app version must be published after adding the scope
3. User must provide `owner_openid` (format: `ou_xxx`; obtain from Feishu Open Platform → API Debug Console → "Quick Copy open_id")

If transfer fails with 403: report the error and the two prerequisite steps; do not retry automatically.

### Error handling

| Error | Action |
|-------|--------|
| 403 permission denied | Tell user to: (1) add the app as a wiki space member (SETUP Step D), or (2) verify the required permission scope is enabled and app version is published (SETUP Steps B–C) |
| 131005 not found | Ask user to verify space_id / node_token |
| 1254291 write conflict | Wait 1 second and retry once; if it fails again, report to user |
| Ambiguous token type | Always call get_node first to resolve — never guess the token type |

### Default behavior when input is incomplete

| Missing input | Default behavior |
|---------------|-----------------|
| No space_id | Call list-spaces and ask user to pick one |
| No parent_node_token | Create node at root level |
| No obj_type specified | Default to `docx` |
| No page_size specified | Use 50 |
