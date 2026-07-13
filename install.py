#!/usr/bin/env python3
"""Install agent-notify and merge its hooks into Claude Code and Codex."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any


COMMANDS = {
    "claude_stop": '"$HOME/.local/bin/agent-notify" claude stop',
    "claude_permission": '"$HOME/.local/bin/agent-notify" claude permission',
    "codex_stop": '"$HOME/.local/bin/agent-notify" codex stop',
    "codex_permission": '"$HOME/.local/bin/agent-notify" codex permission',
}

LEGACY_NOTIFICATION_MARKERS = ("notify-on-stop.sh", "notify-pretty.sh")

ICON_FILENAMES = ("claude.png", "codex.png")

PRODUCT_CONFIGS = {
    "claude": (Path(".claude/settings.json"), "claude"),
    "codex": (Path(".codex/hooks.json"), "codex"),
}


def selected_products(agent: str) -> tuple[tuple[Path, str], ...]:
    if agent == "all":
        return tuple(PRODUCT_CONFIGS.values())
    return (PRODUCT_CONFIGS[agent],)


def hook(command: str) -> dict[str, Any]:
    return {"hooks": [{"type": "command", "command": command, "timeout": 10}]}


def wanted_hooks(product: str) -> dict[str, list[dict[str, Any]]]:
    if product == "claude":
        permission = hook(COMMANDS["claude_permission"])
        permission["matcher"] = "permission_prompt"
        return {
            "Stop": [hook(COMMANDS["claude_stop"])],
            "Notification": [permission],
        }
    return {
        "Stop": [hook(COMMANDS["codex_stop"])],
        "PermissionRequest": [hook(COMMANDS["codex_permission"])],
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return {}
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 的根节点必须是 JSON 对象")
    return value


def command_in_group(group: Any, command: str) -> bool:
    if not isinstance(group, dict):
        return False
    handlers = group.get("hooks")
    if not isinstance(handlers, list):
        return False
    return any(
        isinstance(item, dict) and item.get("command") == command for item in handlers
    )


def legacy_notification_commands(data: dict[str, Any]) -> list[str]:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []
    commands: list[str] = []
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for handler in group["hooks"]:
                command = handler.get("command") if isinstance(handler, dict) else None
                if isinstance(command, str) and any(
                    marker in command for marker in LEGACY_NOTIFICATION_MARKERS
                ):
                    commands.append(command)
    return sorted(set(commands))


def merge_hooks(data: dict[str, Any], product: str) -> bool:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks 必须是 JSON 对象")

    changed = False
    for event, groups in wanted_hooks(product).items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError(f"hooks.{event} 必须是数组")
        for group in groups:
            command = group["hooks"][0]["command"]
            if not any(command_in_group(item, command) for item in current):
                current.append(group)
                changed = True
    return changed


def remove_hooks(data: dict[str, Any]) -> bool:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False

    changed = False
    commands = set(COMMANDS.values())
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        retained = []
        for group in groups:
            if any(command_in_group(group, command) for command in commands):
                changed = True
            else:
                retained.append(group)
        if retained:
            hooks[event] = retained
        elif len(retained) != len(groups):
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    return changed


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.agent-notify-backup-{timestamp}")
        shutil.copy2(path, backup)

    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(existing_mode)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def install(home: Path, source: Path, assets: Path, agent: str) -> None:
    target = home / ".local/bin/agent-notify"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    icon_directory = home / ".local/share/agent-notify/icons"
    icon_directory.mkdir(parents=True, exist_ok=True)
    for filename in ICON_FILENAMES:
        shutil.copy2(assets / filename, icon_directory / filename)

    for relative_path, product in selected_products(agent):
        path = home / relative_path
        data = load_json(path)
        for command in legacy_notification_commands(data):
            print(
                f"警告：{path} 仍包含旧通知 Hook，可能产生重复通知：{command}",
                file=sys.stderr,
            )
        if merge_hooks(data, product):
            write_json(path, data)
            print(f"已更新 {path}")
        else:
            print(f"已存在 {path}")
    print(f"已安装 {target}")
    print(f"已安装图标 {icon_directory}")


def uninstall(home: Path, agent: str) -> None:
    for relative_path, _product in selected_products(agent):
        path = home / relative_path
        if not path.exists():
            continue
        data = load_json(path)
        if remove_hooks(data):
            write_json(path, data)
            print(f"已移除 {path} 中的 agent-notify Hook")
    target = home / ".local/bin/agent-notify"
    if target.exists():
        target.unlink()
        print(f"已删除 {target}")
    share_directory = home / ".local/share/agent-notify"
    if share_directory.exists():
        shutil.rmtree(share_directory)
        print(f"已删除 {share_directory}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--assets", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--agent",
        choices=("claude", "codex", "all"),
        default="all",
        help="Agent CLI hooks to install or uninstall.",
    )
    args = parser.parse_args()

    try:
        if args.uninstall:
            uninstall(args.home.expanduser().resolve(), args.agent)
        else:
            source = args.source or Path(__file__).parent / "bin/agent-notify"
            assets = args.assets or Path(__file__).parent / "assets"
            install(
                args.home.expanduser().resolve(),
                source.resolve(),
                assets.resolve(),
                args.agent,
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"安装失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
