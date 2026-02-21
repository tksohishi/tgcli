"""Custom hatch build hook to embed the git commit hash."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        commit = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
        except Exception:  # noqa: S110
            pass

        out = Path(self.root) / "src" / "tgcli" / "_commit.py"
        out.write_text(f"COMMIT = {commit!r}\n")
