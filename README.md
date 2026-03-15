# feishu-wiki-su

An [OpenClaw](https://github.com/openclaw/openclaw) skill for managing Feishu wiki spaces via the Feishu Open Platform API — no third-party dependencies, pure Python stdlib.

Covers wiki structure, docx content, bitable (multi-dimensional tables), and spreadsheets — all from a single AI conversation.

---

## What it does

| Area | Operations |
|------|-----------|
| **Wiki** | List/inspect spaces and nodes, create/move/rename nodes, manage space members |
| **Docx** | Read content, write/append (auto Markdown detection), rename title, clear, delete blocks, transfer ownership |
| **Bitable** | Full CRUD on tables, fields, and records; auto-splits large batches |
| **Sheet** | List sheets, read/write/append/clear cell ranges |
| **Scan** | Recursive wiki scan → Markdown summary report with status classification |

---

## Requirements

- Python 3.8+ (stdlib only — no pip install needed)
- A Feishu self-built app with `tenant_access_token` access
- OpenClaw installed (for skill routing); scripts can also be run standalone

---

## Setup

### 1. Create or reuse a Feishu app

Go to [open.feishu.cn/app](https://open.feishu.cn/app) → **Create App** → **Enterprise Self-Built App**.

Copy the **App ID** and **App Secret** from Credentials & Basic Info.

### 2. Enable permissions

In the app console → **Permission Management**, enable:

| Scope | Required for |
|-------|-------------|
| `wiki:wiki` | All wiki operations |
| `docx:document` | Docx read and write |
| `sheets:spreadsheet` | Sheet read and write |
| `bitable:app` | Bitable CRUD |
| `docs:permission.member:transfer` | Ownership transfer (optional) |

### 3. Publish the app

App Release → Version Management → Create Version → Apply for release → have your admin approve.

> Permissions do not take effect for `tenant_access_token` until the app is published.

### 4. Add the app as a wiki space member

Open the target wiki space in Feishu → ··· → Settings → Members → Add Member → search for your app name → set role to **Member** or **Admin**.

### 5. Set credentials

```bash
openclaw config set skills.feishu-wiki-su.env.FEISHU_APP_ID     <App ID>
openclaw config set skills.feishu-wiki-su.env.FEISHU_APP_SECRET  <App Secret>
```

Verify:

```bash
python3 scripts/wiki.py token
```

---

## Script reference

All scripts output JSON (except `scan.py` which outputs Markdown). Auth is handled automatically from env vars.

### wiki.py — Spaces, nodes, members

```bash
python3 scripts/wiki.py token
python3 scripts/wiki.py spaces
python3 scripts/wiki.py get-space <space_id>
python3 scripts/wiki.py nodes <space_id> [--parent <node_token>]
python3 scripts/wiki.py get-node <node_token>
python3 scripts/wiki.py create-node <space_id> --title "Title" [--type docx|bitable|sheet|mindnote|slides|file] [--parent <token>]
python3 scripts/wiki.py move-node <space_id> <node_token> --target-parent <token>
python3 scripts/wiki.py rename-node <space_id> <node_token> --title "New Title"
python3 scripts/wiki.py add-member <space_id> --email user@example.com [--role member|admin]
python3 scripts/wiki.py remove-member <space_id> --member-id <openid> [--member-role member|admin]
```

**Token chain**: wiki URL → `node_token` → `get-node` → `obj_token` → use for content APIs.

### docx.py — Document content

`document_id` = `obj_token` from `get-node` or `create-node` (when `obj_type == "docx"`).

```bash
python3 scripts/docx.py read <document_id>
python3 scripts/docx.py write <document_id> --content "..."              # auto-detects Markdown vs plain
python3 scripts/docx.py write <document_id> --content "..." --format md
python3 scripts/docx.py write <document_id> --content "..." --format plain
python3 scripts/docx.py append <document_id> --content "more..."
cat my-doc.md | python3 scripts/docx.py write <document_id>             # pipe from file
python3 scripts/docx.py rename <document_id> --title "New Title"
python3 scripts/docx.py blocks <document_id>
python3 scripts/docx.py delete-blocks <document_id> --start 0 --end 3  # range is [start, end)
python3 scripts/docx.py clear <document_id>
python3 scripts/docx.py transfer-owner <document_id> --openid ou_xxx [--old-owner-perm view|edit|full_access]
```

**Auto-format detection**: `write` checks for Markdown markers (`#`, `-`, ` ``` `, `**`, `>`) and converts automatically. Use `--format` to override.

**Overwrite pattern**: `clear` then `write`.

**Supported Markdown**: headings H1–H9, bullets, ordered lists, todo `- [ ]`/`- [x]`, blockquotes, fenced code blocks (with language), dividers, inline bold/italic/code. Tables, images, and nested lists are not supported.

### bitable.py — Multi-dimensional tables

`app_token` = `obj_token` from `get-node` (when `obj_type == "bitable"`). Never use a wiki URL token directly.

```bash
# Tables
python3 scripts/bitable.py tables <app_token>
python3 scripts/bitable.py create-table <app_token> --name "Name" \
  [--fields-json '[{"field_name":"Name","type":1}]'] [--default-view "Grid"]
python3 scripts/bitable.py delete-table <app_token> <table_id>

# Fields  (type: 1=Text 2=Number 3=SingleSelect 4=MultiSelect 5=Date
#                7=Checkbox 11=Person 13=Phone 15=URL 17=Attachment
#                18=Link 20=Formula)
python3 scripts/bitable.py fields <app_token> <table_id>
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Score" --type 2
python3 scripts/bitable.py create-field <app_token> <table_id> --name "Status" --type 3 \
  --property-json '{"options":[{"name":"Todo","color":0},{"name":"Done","color":1}]}'
python3 scripts/bitable.py update-field <app_token> <table_id> <field_id> --name "New Name" --type 2
python3 scripts/bitable.py delete-field <app_token> <table_id> <field_id>

# Records
python3 scripts/bitable.py get-record <app_token> <table_id> <record_id>
python3 scripts/bitable.py query <app_token> <table_id> [--filter 'CurrentValue.[Status]="Done"'] [--limit N]
python3 scripts/bitable.py add <app_token> <table_id> \
  --records-json '[{"fields":{"Name":"Alice","Score":90}}]'
python3 scripts/bitable.py update <app_token> <table_id> <record_id> \
  --fields-json '{"Score":95}'
python3 scripts/bitable.py batch-update <app_token> <table_id> \
  --records-json '[{"record_id":"recXXX","fields":{"Score":95}}]'
python3 scripts/bitable.py delete <app_token> <table_id> <record_id>
python3 scripts/bitable.py batch-delete <app_token> <table_id> \
  --record-ids-json '["recXXX","recYYY"]'
```

**Limits**: batch_create 500/call · batch_update 1000/call · batch_delete 500/call · max 20,000 records/table. All write commands enforce 0.5s inter-batch delay automatically.

**Important**: bitables inside a wiki must be created via `wiki.py create-node --type bitable`. Using the standalone bitable creation endpoint returns error 1254002.

### sheet.py — Spreadsheets

`spreadsheet_token` = `obj_token` from `get-node` (when `obj_type == "sheet"`). Always run `list` first to get `sheet_id`.

```bash
python3 scripts/sheet.py list <spreadsheet_token>
python3 scripts/sheet.py read <spreadsheet_token> "<sheetId>!A1:C10"
python3 scripts/sheet.py write <spreadsheet_token> "<sheetId>!A1:C2" \
  --values-json '[["col1","col2"],["val1",2]]'
python3 scripts/sheet.py append <spreadsheet_token> "<sheetId>!A:C" \
  --values-json '[["new","row"]]'
python3 scripts/sheet.py clear <spreadsheet_token> "<sheetId>!A1:C10"
```

Range format: `<sheetId>!<start>:<end>` e.g. `Q7PlXT!A1:C10`.

### scan.py — Recursive wiki scan

```bash
python3 scripts/scan.py https://xxx.feishu.cn/wiki/<node_token>
# or: python3 scripts/scan.py <node_token>
```

Recursively lists all descendant nodes, reads docx previews, and outputs a Markdown report with a directory tree, content summaries, and status statistics (Complete / In progress / Empty / No permission).

---

## Error reference

| Code | Meaning | Fix |
|------|---------|-----|
| 131005 | Not found | Verify space_id / node_token |
| 131006 | Permission denied | Add app as wiki space member (Setup step 4) |
| 1254002 | Bitable creation failed | Create bitable via `wiki.py create-node`, not the bitable API |
| 1254003 | Wrong app_token | Use `obj_token` from `get-node`, not the wiki URL token |
| 1254046 | Cannot delete primary field | The first/index field of a table cannot be deleted |
| 1254291 | Write conflict | Scripts add 0.5s delay between batches automatically |
| 1254103 | Record limit exceeded | Max 20,000 records per table |

---

## Project structure

```
feishu-wiki-su/
├── SKILL.md                  # OpenClaw skill definition (routing + full HOW guide)
├── README.md                 # This file
├── scripts/
│   ├── lib.py                # Shared HTTP client and auth
│   ├── wiki.py               # Wiki spaces, nodes, members
│   ├── docx.py               # Docx read/write/rename/transfer
│   ├── bitable.py            # Bitable tables, fields, records
│   ├── sheet.py              # Spreadsheet read/write
│   └── scan.py               # Recursive wiki scan → report
└── references/
    ├── api.md                # Feishu API quick reference
    ├── report-format.md      # Scan report format spec
    └── templates.md          # Markdown block syntax reference
```

---

## License

MIT
