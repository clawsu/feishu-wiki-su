#!/usr/bin/env python3
"""
feishu-wiki-su — DEPRECATED entry point

This monolithic script has been split into focused modules.
Use the individual scripts instead:

  wiki.py     — spaces, nodes, members, token check
  docx.py     — write / append / write-md / transfer-owner
  bitable.py  — tables, fields, records (CRUD)
  sheet.py    — list, read, write, append
  scan.py     — recursive wiki scan → Markdown report

Examples:
  python3 scripts/wiki.py create-node <space_id> --title "Title" --type docx
  python3 scripts/docx.py write-md <document_id> --content "# Heading..."
  python3 scripts/bitable.py add <app_token> <table_id> --records-json '[...]'
  python3 scripts/sheet.py list <spreadsheet_token>
  python3 scripts/scan.py https://xxx.feishu.cn/wiki/NodeToken
"""
import sys
print(
    '{"error": "feishu.py is deprecated. Use wiki.py / docx.py / bitable.py / sheet.py / scan.py"}',
    file=sys.stderr,
)
sys.exit(1)
