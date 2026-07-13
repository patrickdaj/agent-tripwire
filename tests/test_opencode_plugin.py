"""TypeScript typecheck of the OpenCode plugin, when a Bun toolchain is available;
skipped otherwise (the plugin's *protocol* behavior is covered by the neutral-mode
request-shape tests in test_hook_cli.py). Offline apart from the one-time type install,
which is itself skipped if the network/registry is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "integrations" / "opencode" / "agent-tripwire.ts"

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="bun not installed")


def test_plugin_typechecks(tmp_path):
    assert PLUGIN.exists()
    work = tmp_path / "tc"
    work.mkdir()
    (work / "agent-tripwire.ts").write_text(PLUGIN.read_text())
    (work / "package.json").write_text(
        '{"name":"tc","dependencies":{"@opencode-ai/plugin":"*","bun-types":"*"}}'
    )
    (work / "tsconfig.json").write_text(
        '{"compilerOptions":{"noEmit":true,"skipLibCheck":true,"strict":true,'
        '"moduleResolution":"bundler","module":"esnext","target":"esnext",'
        '"types":["bun-types"]}}'
    )
    install = subprocess.run(["bun", "install"], cwd=work, capture_output=True, text=True, timeout=180)
    if install.returncode != 0:
        pytest.skip(f"bun install unavailable (offline registry?): {install.stderr[:200]}")

    result = subprocess.run(["bunx", "tsc", "--noEmit"], cwd=work,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"tsc errors:\n{result.stdout}\n{result.stderr}"
