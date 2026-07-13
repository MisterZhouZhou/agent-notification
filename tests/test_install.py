from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    def test_install_warns_without_removing_legacy_notification_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            legacy = "~/.claude/hooks/notify-on-stop.sh"
            settings.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {"hooks": [{"type": "command", "command": legacy}]}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "install.py"),
                    "--home",
                    str(home),
                    "--source",
                    str(ROOT / "bin/agent-notify"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            after = json.loads(settings.read_text(encoding="utf-8"))
            self.assertIn("可能产生重复通知", result.stderr)
            self.assertEqual(after["hooks"]["Stop"][0]["hooks"][0]["command"], legacy)

    def test_install_preserves_existing_settings_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(
                json.dumps({"model": "sonnet", "hooks": {"Stop": []}}),
                encoding="utf-8",
            )

            command = [
                "python3",
                str(ROOT / "install.py"),
                "--home",
                str(home),
                "--source",
                str(ROOT / "bin/agent-notify"),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)

            claude = json.loads(settings.read_text(encoding="utf-8"))
            codex = json.loads((home / ".codex/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(claude["model"], "sonnet")
            self.assertEqual(len(claude["hooks"]["Stop"]), 1)
            self.assertEqual(len(claude["hooks"]["Notification"]), 1)
            self.assertEqual(len(codex["hooks"]["Stop"]), 1)
            self.assertEqual(len(codex["hooks"]["PermissionRequest"]), 1)
            self.assertTrue((home / ".local/bin/agent-notify").exists())
            icon_directory = home / ".local/share/agent-notify/icons"
            self.assertEqual(
                {path.name for path in icon_directory.iterdir()},
                {"claude.png", "codex.png"},
            )
            self.assertGreaterEqual(
                len(list(settings.parent.glob("settings.json.agent-notify-backup-*"))), 1
            )

    def test_install_can_target_only_one_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex/hooks.json"
            codex.parent.mkdir(parents=True)
            codex.write_text("", encoding="utf-8")

            subprocess.run(
                [
                    "python3",
                    str(ROOT / "install.py"),
                    "--home",
                    str(home),
                    "--source",
                    str(ROOT / "bin/agent-notify"),
                    "--agent",
                    "claude",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            claude = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(len(claude["hooks"]["Stop"]), 1)
            self.assertEqual(codex.read_text(encoding="utf-8"), "")

    def test_install_treats_empty_json_file_as_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex/hooks.json"
            codex.parent.mkdir(parents=True)
            codex.write_text("", encoding="utf-8")

            subprocess.run(
                [
                    "python3",
                    str(ROOT / "install.py"),
                    "--home",
                    str(home),
                    "--source",
                    str(ROOT / "bin/agent-notify"),
                    "--agent",
                    "codex",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            data = json.loads(codex.read_text(encoding="utf-8"))
            self.assertEqual(len(data["hooks"]["Stop"]), 1)

    def test_shell_installer_bootstraps_from_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            command = [
                "sh",
                str(ROOT / "install.sh"),
                "--home",
                str(home),
                "--base-url",
                ROOT.as_uri(),
                "--agent",
                "codex",
            ]

            result = subprocess.run(command, check=True, capture_output=True, text=True)

            self.assertIn("已安装", result.stdout)
            self.assertTrue((home / ".local/bin/agent-notify").exists())
            self.assertTrue((home / ".local/share/agent-notify/icons/codex.png").exists())
            self.assertTrue((home / ".local/share/agent-notify/icons/claude.png").exists())
            self.assertTrue((home / ".codex/hooks.json").exists())
            self.assertFalse((home / ".claude/settings.json").exists())

    def test_shell_installer_uses_local_checkout_when_run_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = subprocess.run(
                ["sh", "install.sh", "--home", str(home)],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )

            self.assertIn("已安装", result.stdout)
            self.assertTrue((home / ".local/bin/agent-notify").exists())
            self.assertTrue((home / ".local/share/agent-notify/icons/codex.png").exists())
            self.assertTrue((home / ".codex/hooks.json").exists())

    def test_uninstall_only_removes_own_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            install = [
                "python3",
                str(ROOT / "install.py"),
                "--home",
                str(home),
                "--source",
                str(ROOT / "bin/agent-notify"),
            ]
            subprocess.run(install, check=True, capture_output=True, text=True)
            settings = home / ".claude/settings.json"
            data = json.loads(settings.read_text(encoding="utf-8"))
            data["hooks"]["Stop"].append(
                {"hooks": [{"type": "command", "command": "echo keep"}]}
            )
            settings.write_text(json.dumps(data), encoding="utf-8")

            subprocess.run(
                ["python3", str(ROOT / "install.py"), "--home", str(home), "--uninstall"],
                check=True,
                capture_output=True,
                text=True,
            )
            after = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(after["hooks"]["Stop"][0]["hooks"][0]["command"], "echo keep")
            self.assertFalse((home / ".local/bin/agent-notify").exists())
            self.assertFalse((home / ".local/share/agent-notify").exists())


if __name__ == "__main__":
    unittest.main()
