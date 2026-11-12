"""Run with the wheel environment's Python, from outside the checkout."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

import hpctrack


def main():
    installed = Path(hpctrack.__file__).resolve()
    assert "site-packages" in installed.parts, f"Expected installed wheel, got {installed}"
    with tempfile.TemporaryDirectory(prefix="hpctrack-wheel-") as temporary:
        root = Path(temporary)
        home, workspace, unrelated = root / "user home", root / "demo workspace", root / "unrelated"
        home.mkdir()
        unrelated.mkdir()
        env = {
            **os.environ,
            "HOME": str(home),
            "HPCTRACK_HOME": str(workspace),
            "HPCTRACK_ACTOR": "agent",
            "HPCTRACK_AGENT": "wheel-smoke",
            "HPCTRACK_SESSION": "smoke",
        }
        env.pop("PYTHONPATH", None)
        executable = Path(sys.executable).parent / "hpctrack"

        def run(*args):
            completed = subprocess.run(
                [str(executable), *args],
                cwd=unrelated,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert completed.returncode == 0, (args, completed.stdout, completed.stderr)
            payload = json.loads(completed.stdout)
            assert payload["ok"]
            return payload["data"]

        assert list(home.iterdir()) == []
        assert all(d["status"] == "missing" for d in run("skills", "status")["destinations"])
        preview = run("skills", "install", "--agent", "all", "--dry-run")
        assert len(preview["destinations"]) == 2 and list(home.iterdir()) == []
        run("skills", "install", "--agent", "all")
        assert not workspace.exists()
        assert all(d["status"] == "current" for d in run("skills", "status")["destinations"])
        source = resources.files("hpctrack") / "templates"
        expected = {
            "SKILL.md": source / "skills/hpctrack/SKILL.md",
            "references/AGENTS.md": source / "workspace/AGENTS.md",
            "references/build-software.md": source / "workspace/skills/build-software/SKILL.md",
        }
        for relative in (".claude/skills/hpctrack", ".agents/skills/hpctrack"):
            destination = home / relative
            manifest = json.loads((destination / ".hpctrack-skill.json").read_text())
            assert manifest["version"] == hpctrack.__version__
            assert set(manifest["files"]) == set(expected)
            for name, resource in expected.items():
                data = (destination / name).read_bytes()
                assert data == resource.read_bytes()
                assert hashlib.sha256(data).hexdigest() == manifest["files"][name]
        run("init", "--machines", "demo", "--no-git")
        paths = run("workspace", "show")
        assert paths["workspace"] == str(workspace)
        assert paths["records"] == str(workspace / "records")
        assert not Path(paths["state"]).exists()
        run("sw", "init", "tiny", "--machine", "demo", "--template", "demo")
        check = run("sw", "check", "tiny", "--machine", "demo")
        assert check["next_action"] == "build" and check["pending_operations"] == []
        assert Path(check["record_path"]).is_dir()
        assert list(unrelated.iterdir()) == []
    print(f"Wheel smoke passed: hpctrack {hpctrack.__version__}; demo evidence is simulated")


if __name__ == "__main__":
    main()
