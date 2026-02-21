"""Custom hatch build hook to embed the git commit hash."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        commit = None
        pkg_version = self.metadata.version
        try:
            # If this version is tagged, it's a release; no commit suffix.
            tag = subprocess.run(
                ["git", "tag", "-l", f"v{pkg_version}"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=2,
            )
            if tag.returncode == 0 and tag.stdout.strip():
                pass  # tagged release, keep commit = None
            else:
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
        build_data["force_include"][str(out)] = "tgcli/_commit.py"
