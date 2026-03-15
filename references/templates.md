# Feishu Docx — Markdown Format Reference

Use with `python3 scripts/feishu.py docx-write-md`.

---

## Syntax → Block type mapping

Every line is converted to exactly one Feishu block. The table below is authoritative — do not guess or invent syntax.

| Markdown syntax | Feishu block_type | Field name | Notes |
|-----------------|-------------------|------------|-------|
| `# Heading` | 3 | `heading1` | |
| `## Heading` | 4 | `heading2` | |
| `### Heading` | 5 | `heading3` | up to `######` → heading6 (bt 8) |
| `- item` or `* item` | 12 | `bullet` | unordered list |
| `1. item` or `1) item` | 13 | `ordered` | any leading number |
| `- [ ] task` | 17 | `todo` | `done: false` |
| `- [x] task` | 17 | `todo` | `done: true` |
| `> text` | 15 | `quote` | blockquote |
| ` ```lang … ``` ` | 14 | `code` | fenced code block, see language table |
| `---` or `***` or `___` | 22 | `divider` | 3+ identical chars on a line |
| plain text | 2 | `text` | anything else |
| *(empty line)* | *(skipped)* | — | does not produce a block |

---

## Inline styles (inside any text block)

| Markdown | Style applied | JSON field |
|----------|---------------|------------|
| `**bold**` or `__bold__` | Bold | `"bold": true` |
| `*italic*` or `_italic_` | Italic | `"italic": true` |
| `` `code` `` | Inline code (monospace) | `"inline_code": true` |

Styles can combine in a single line. Only the matching segment is styled; the rest is unstyled `text_run`.

---

## Code block language values

The `language` integer is embedded in `code.style.language`. Use the exact identifier in the fenced block opening line.

| Identifier(s) | language int | Rendered as |
|---------------|-------------|-------------|
| *(empty)* / `text` / `plain` | 1 | PlainText |
| `bash` | 7 | Bash |
| `shell` / `sh` / `zsh` | 60 | Shell |
| `python` / `py` | 49 | Python |
| `javascript` / `js` | 30 | JavaScript |
| `typescript` / `ts` | 63 | TypeScript |
| `json` | 28 | JSON |
| `go` | 22 | Go |
| `rust` | 53 | Rust |
| `sql` | 56 | SQL |
| `yaml` / `yml` | 67 | YAML |
| `java` | 29 | Java |
| `c` | 10 | C |
| `cpp` / `c++` | 9 | C++ |
| `xml` | 66 | XML |
| `ruby` / `rb` | 52 | Ruby |
| `swift` | 61 | Swift |
| `php` | 43 | PHP |
| `markdown` / `md` | 39 | Markdown |
| `r` | 50 | R |
| `dockerfile` | 18 | Dockerfile |
| `powershell` / `ps1` | 46 | PowerShell |
| `toml` | 75 | TOML |
| *(anything else)* | 1 | PlainText (fallback) |

---

## What is NOT supported

The following Markdown constructs are silently skipped or rendered as plain text — do not use them:

| Markdown | Reason |
|----------|--------|
| `| table |` Markdown tables | Feishu table blocks cannot be created via the children API (error 1770029) |
| `![img](url)` images | Image upload requires a separate file-upload API; not supported here |
| `[link](url)` hyperlinks | Not yet implemented in `_parse_inline`; renders as plain text |
| Nested lists (indented `  - `) | Feishu nesting requires parent-child block IDs; flattened to same level |
| Setext headings (`===` underline) | Not supported; use ATX style (`# Heading`) |
| HTML tags `<b>text</b>` | Ignored |

---

## Templates

### Template 1 — Meeting Notes

```markdown
# Meeting: <Topic>

**Date:** YYYY-MM-DD  **Time:** HH:MM–HH:MM
**Attendees:** Alice, Bob, Carol

---

## Agenda

1. Review last week's action items
2. Q2 planning update
3. Open questions

---

## Notes

### Review last week

- Action item 1 — **closed** by Alice
- Action item 2 — still in progress

### Q2 planning

> Key decision: ship feature X by end of April.

- Goal: increase retention by 10%
- Owner: Bob

---

## Decisions

- Approved Q2 roadmap
- Deferred feature Y to Q3

---

## Action items

- [ ] Alice — draft RFC for feature X — 2026-03-20
- [ ] Bob — set up tracking dashboard — 2026-03-18
- [x] Carol — send onboarding doc to new hires — done
```

---

### Template 2 — Technical Spec / Proposal

```markdown
# Proposal: <Title>

**Author:** <name>  **Status:** Draft  **Date:** YYYY-MM-DD

---

## Context

Describe the background and why this is needed.

## Problem

What specific problem are we solving?

## Goals

- Goal 1
- Goal 2

## Non-goals

- Not in scope: X
- Not in scope: Y

---

## Proposed approach

Brief description of the solution.

### Key design decisions

1. Decision A — rationale
2. Decision B — rationale

### Example

```python
def process(items: list[str]) -> dict:
    return {item: len(item) for item in items}
```

---

## Alternatives considered

| Option | Pros | Cons |
|--------|------|------|

> Note: Markdown tables are not supported by the block API — replace the table above with a bullet list.

- **Option A** — faster but harder to maintain
- **Option B** — current choice; balances speed and clarity

---

## Risks

- Risk 1 — mitigation: X
- Risk 2 — mitigation: Y

---

## Rollout plan

1. Internal testing — Week 1
2. Beta rollout — Week 2
3. Full release — Week 3

## Open questions

- [ ] Question 1 — owner: Alice
- [ ] Question 2 — owner: Bob
```

---

### Template 3 — Wiki Knowledge Page

```markdown
# <Page Title>

**Last updated:** YYYY-MM-DD  **Owner:** <name>

---

## Overview

One paragraph summary of what this page covers.

---

## Quick reference

- **Key term A:** definition
- **Key term B:** definition
- **Key term C:** definition

---

## Setup

### Prerequisites

- Requirement 1
- Requirement 2

### Steps

1. Install the tool

```bash
npm install -g my-tool
```

2. Configure credentials

```bash
export MY_TOKEN=xxx
my-tool config set token $MY_TOKEN
```

3. Verify

```bash
my-tool ping
# → {"ok": true}
```

---

## Usage examples

### Example A — basic

```python
from my_tool import Client

client = Client(token="xxx")
result = client.get("resource_id")
print(result)
```

### Example B — advanced

Description of the advanced use case.

---

## Troubleshooting

> If you see a `403` error, check that the app is added as a space member (SETUP Step D).

| Error code | Meaning | Fix |
|------------|---------|-----|

> Note: replace this table with bullets — Markdown tables are not supported.

- **Error 403** — permission denied → add app as wiki member
- **Error 10003** — wrong App ID → check FEISHU_APP_ID

---

## Related pages

- See also: page A
- See also: page B
```

---

## Usage

```bash
# Write from a string
python3 scripts/feishu.py docx-write-md <document_id> --content "# Title

## Section

- Bullet item
- Another item

\`\`\`python
print('hello')
\`\`\`"

# Write from a file
python3 scripts/feishu.py docx-write-md <document_id> < my-document.md

# Pipe from cat
cat my-document.md | python3 scripts/feishu.py docx-write-md <document_id>
```

Output on success:
```json
{
  "ok": true,
  "document_id": "doxcnXXXXXX",
  "blocks_written": 24
}
```
