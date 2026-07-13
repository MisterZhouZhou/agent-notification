from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/agent-notify"


def dry_run(
    source: str,
    event: str,
    payload: dict,
    extra_env: dict[str, str] | None = None,
) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "AGENT_NOTIFY_DRY_RUN": "1",
            "AGENT_NOTIFY_BIN": "/bin/echo",
            "AGENT_NOTIFY_PERMISSION_REMINDER": "0",
            "TERM_PROGRAM": "WarpTerminal",
        }
    )
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [str(SCRIPT), source, event],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    return json.loads(result.stdout)


class AgentNotifyTest(unittest.TestCase):
    def test_each_source_uses_its_installed_icon_as_file_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            icon_directory = Path(directory)
            (icon_directory / "claude.png").write_bytes(b"claude")
            (icon_directory / "codex.png").write_bytes(b"codex")
            environment = {"AGENT_NOTIFY_ICON_DIR": str(icon_directory)}

            claude = dry_run("claude", "stop", {}, environment)
            codex = dry_run("codex", "stop", {}, environment)

            claude_icon = claude["command"][claude["command"].index("-appIcon") + 1]
            codex_icon = codex["command"][codex["command"].index("-appIcon") + 1]
            claude_content_image = claude["command"][
                claude["command"].index("-contentImage") + 1
            ]
            codex_content_image = codex["command"][
                codex["command"].index("-contentImage") + 1
            ]
            self.assertEqual(
                claude_icon, (icon_directory / "claude.png").resolve().as_uri()
            )
            self.assertEqual(
                codex_icon, (icon_directory / "codex.png").resolve().as_uri()
            )
            self.assertEqual(claude_content_image, claude_icon)
            self.assertEqual(codex_content_image, codex_icon)

    def test_configured_icon_overrides_source_icon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "custom icon.png"
            override.write_bytes(b"custom")
            output = dry_run(
                "codex",
                "stop",
                {},
                {"AGENT_NOTIFY_ICON": str(override)},
            )
            icon = output["command"][output["command"].index("-appIcon") + 1]
            content_image = output["command"][
                output["command"].index("-contentImage") + 1
            ]
            self.assertEqual(icon, override.resolve().as_uri())
            self.assertEqual(content_image, icon)

    def test_disabled_permission_reminds_once_per_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = root / "com.apple.ncprefs.plist"
            state = root / "state"
            with preferences.open("wb") as file:
                plistlib.dump(
                    {
                        "apps": [
                            {
                                "bundle-id": "fr.julienxx.oss.terminal-notifier",
                                "auth": 7,
                                "flags": 0x0080200E,
                            }
                        ]
                    },
                    file,
                )
            env = os.environ.copy()
            env.update(
                {
                    "AGENT_NOTIFY_BIN": "/bin/echo",
                    "AGENT_NOTIFY_BUNDLE_ID": "fr.julienxx.oss.terminal-notifier",
                    "AGENT_NOTIFY_PREFS_PATH": str(preferences),
                    "AGENT_NOTIFY_STATE_DIR": str(state),
                    "AGENT_NOTIFY_DRY_RUN": "1",
                }
            )
            command = [str(SCRIPT), "codex", "stop"]
            subprocess.run(
                command,
                input='{"session_id":"session-a"}',
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            state_file = state / "permission-reminder.json"
            first = state_file.read_text(encoding="utf-8")
            subprocess.run(
                command,
                input='{"session_id":"session-a"}',
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            self.assertEqual(state_file.read_text(encoding="utf-8"), first)

            subprocess.run(
                command,
                input='{"session_id":"session-b"}',
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(set(state_data["sessions"]), {"session-a", "session-b"})

    def test_doctor_detects_disabled_notification_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preferences = Path(directory) / "com.apple.ncprefs.plist"
            with preferences.open("wb") as file:
                plistlib.dump(
                    {
                        "apps": [
                            {
                                "bundle-id": "fr.julienxx.oss.terminal-notifier",
                                "auth": 7,
                                "flags": 0x0080200E,
                            }
                        ]
                    },
                    file,
                )
            env = os.environ.copy()
            env.update(
                {
                    "AGENT_NOTIFY_BIN": "/bin/echo",
                    "AGENT_NOTIFY_BUNDLE_ID": "fr.julienxx.oss.terminal-notifier",
                    "AGENT_NOTIFY_PREFS_PATH": str(preferences),
                }
            )
            result = subprocess.run(
                [str(SCRIPT), "doctor"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("通知已在 macOS 系统设置中关闭", result.stderr)
            self.assertIn("不会再次弹出授权框", result.stderr)

    def test_doctor_does_not_treat_auth_seven_as_disabled_when_flag_is_on(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preferences = Path(directory) / "com.apple.ncprefs.plist"
            with preferences.open("wb") as file:
                plistlib.dump(
                    {
                        "apps": [
                            {
                                "bundle-id": "fr.julienxx.oss.terminal-notifier",
                                "auth": 7,
                                "flags": 0x0280200E,
                            }
                        ]
                    },
                    file,
                )
            env = os.environ.copy()
            env.update(
                {
                    "AGENT_NOTIFY_BIN": "/bin/echo",
                    "AGENT_NOTIFY_BUNDLE_ID": "fr.julienxx.oss.terminal-notifier",
                    "AGENT_NOTIFY_PREFS_PATH": str(preferences),
                }
            )
            result = subprocess.run(
                [str(SCRIPT), "doctor"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("通知开关已开启", result.stdout)

    def test_codex_stop_uses_final_message_and_warp_activation(self) -> None:
        output = dry_run(
            "codex",
            "stop",
            {
                "cwd": "/tmp/notification",
                "last_assistant_message": "第一行\n第二行",
            },
        )
        self.assertEqual(output["title"], "Codex · 回复完成")
        self.assertEqual(output["subtitle"], "notification")
        self.assertEqual(output["message"], "第一行 第二行")
        self.assertIn("-activate", output["command"])
        self.assertIn("dev.warp.Warp-Stable", output["command"])
        self.assertTrue(output["remove_group"].endswith(":permission"))

    def test_claude_permission_prefers_notification_message(self) -> None:
        output = dry_run(
            "claude",
            "permission",
            {
                "cwd": "/tmp/project-a",
                "message": "Claude 需要授权执行 Bash",
                "notification_type": "permission_prompt",
            },
        )
        self.assertEqual(output["title"], "Claude Code · 需要授权")
        self.assertEqual(output["message"], "Claude 需要授权执行 Bash")
        self.assertIsNone(output["remove_group"])

    def test_permission_does_not_expose_tool_input(self) -> None:
        output = dry_run(
            "codex",
            "permission",
            {
                "cwd": "/tmp/private",
                "tool_name": "Bash",
                "tool_input": {"command": "curl -H 'Authorization: secret'"},
            },
        )
        self.assertEqual(output["message"], "Bash 正在等待你的确认")
        self.assertNotIn("secret", json.dumps(output, ensure_ascii=False))

    def test_same_project_has_stable_group(self) -> None:
        first = dry_run("codex", "stop", {"cwd": "/tmp/a/shared"})
        second = dry_run("codex", "stop", {"cwd": "/var/a/shared"})
        self.assertNotEqual(first["group"], second["group"])


if __name__ == "__main__":
    unittest.main()
