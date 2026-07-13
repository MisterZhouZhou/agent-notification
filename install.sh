#!/bin/sh
set -eu

DEFAULT_REPO="MisterZhouZhou/agent-notification"
DEFAULT_REF="main"
REPO="${AGENT_NOTIFY_REPO:-$DEFAULT_REPO}"
REF="${AGENT_NOTIFY_REF:-$DEFAULT_REF}"
BASE_URL="${AGENT_NOTIFY_BASE_URL:-}"
INSTALL_HOME="$HOME"
UNINSTALL=0
FORCE_REMOTE=0
AGENT="${AGENT_NOTIFY_AGENT:-}"

usage() {
  cat <<'EOF'
Usage: install.sh [--uninstall] [--agent claude|codex|all] [--home PATH] [--repo OWNER/REPO] [--ref REF] [--base-url URL]

Environment:
  AGENT_NOTIFY_AGENT     Agent CLI hooks to install, one of: claude, codex, all.
  AGENT_NOTIFY_REPO      GitHub repository, default: MisterZhouZhou/agent-notification.
  AGENT_NOTIFY_REF       Git ref, branch, or tag, default: main.
  AGENT_NOTIFY_BASE_URL  Override the raw file base URL entirely.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    --home)
      if [ "$#" -lt 2 ]; then
        echo "install.sh: --home requires a path" >&2
        exit 2
      fi
      INSTALL_HOME="$2"
      shift 2
      ;;
    --agent)
      if [ "$#" -lt 2 ]; then
        echo "install.sh: --agent requires claude, codex, or all" >&2
        exit 2
      fi
      AGENT="$2"
      shift 2
      ;;
    --repo)
      if [ "$#" -lt 2 ]; then
        echo "install.sh: --repo requires OWNER/REPO" >&2
        exit 2
      fi
      REPO="$2"
      FORCE_REMOTE=1
      shift 2
      ;;
    --ref)
      if [ "$#" -lt 2 ]; then
        echo "install.sh: --ref requires a git ref" >&2
        exit 2
      fi
      REF="$2"
      FORCE_REMOTE=1
      shift 2
      ;;
    --base-url)
      if [ "$#" -lt 2 ]; then
        echo "install.sh: --base-url requires a URL" >&2
        exit 2
      fi
      BASE_URL="$2"
      FORCE_REMOTE=1
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install.sh: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh: python3 is required" >&2
  exit 1
fi

case "$AGENT" in
  ""|claude|codex|all)
    ;;
  *)
    echo "install.sh: --agent must be one of: claude, codex, all" >&2
    exit 2
    ;;
esac

SCRIPT_DIR=""
case "$0" in
  */*)
    SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    ;;
  *)
    if [ -f "$0" ]; then
      SCRIPT_DIR=$(pwd)
    fi
    ;;
esac

if [ "$FORCE_REMOTE" -eq 0 ] && [ -n "$SCRIPT_DIR" ] \
  && [ -f "$SCRIPT_DIR/install.py" ] \
  && [ -f "$SCRIPT_DIR/bin/agent-notify" ] \
  && [ -d "$SCRIPT_DIR/assets" ]; then
  if [ -z "$AGENT" ] && [ -t 0 ]; then
    printf '选择要安装的 Agent CLI：\n'
    printf '  1) Codex\n'
    printf '  2) Claude\n'
    printf '  3) Both\n'
    printf '请输入 1/2/3 [1]: '
    read -r choice || choice=""
    case "$choice" in
      ""|1) AGENT="codex" ;;
      2) AGENT="claude" ;;
      3) AGENT="all" ;;
      *)
        echo "install.sh: invalid selection: $choice" >&2
        exit 2
        ;;
    esac
  fi
  AGENT=${AGENT:-all}
  if [ "$UNINSTALL" -eq 1 ]; then
    python3 "$SCRIPT_DIR/install.py" --home "$INSTALL_HOME" --agent "$AGENT" --uninstall
  else
    python3 "$SCRIPT_DIR/install.py" \
      --home "$INSTALL_HOME" \
      --source "$SCRIPT_DIR/bin/agent-notify" \
      --assets "$SCRIPT_DIR/assets" \
      --agent "$AGENT"
  fi
  exit $?
fi

AGENT=${AGENT:-all}

if command -v curl >/dev/null 2>&1; then
  download() {
    curl -fsSL "$1" -o "$2"
  }
elif command -v wget >/dev/null 2>&1; then
  download() {
    wget -qO "$2" "$1"
  }
else
  echo "install.sh: curl or wget is required" >&2
  exit 1
fi

if [ -z "$BASE_URL" ]; then
  BASE_URL="https://raw.githubusercontent.com/$REPO/$REF"
fi
BASE_URL=${BASE_URL%/}
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify.XXXXXX")
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

download "$BASE_URL/install.py" "$TMP_DIR/install.py"

if [ "$UNINSTALL" -eq 1 ]; then
  python3 "$TMP_DIR/install.py" --home "$INSTALL_HOME" --agent "$AGENT" --uninstall
  exit $?
fi

mkdir -p "$TMP_DIR/bin" "$TMP_DIR/assets"
download "$BASE_URL/bin/agent-notify" "$TMP_DIR/bin/agent-notify"
download "$BASE_URL/assets/claude.png" "$TMP_DIR/assets/claude.png"
download "$BASE_URL/assets/codex.png" "$TMP_DIR/assets/codex.png"

python3 "$TMP_DIR/install.py" \
  --home "$INSTALL_HOME" \
  --source "$TMP_DIR/bin/agent-notify" \
  --assets "$TMP_DIR/assets" \
  --agent "$AGENT"
