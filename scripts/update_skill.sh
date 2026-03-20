#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/clawsu/feishu-wiki-su"
INSTALLER="/Users/su/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py"

TARGET="${1:-}"

if [[ ! -f "$INSTALLER" ]]; then
  echo "Skill installer not found: $INSTALLER" >&2
  exit 1
fi

if [[ -z "$TARGET" || "$TARGET" == "latest" ]]; then
  python3 "$INSTALLER" --url "$REPO_URL" --path .
  exit 0
fi

if [[ "$TARGET" =~ ^https:// ]]; then
  python3 "$INSTALLER" --url "$TARGET" --path .
  exit 0
fi

python3 "$INSTALLER" --url "$REPO_URL/tree/$TARGET" --path .
