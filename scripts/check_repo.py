"""Check that this folder is ready to be its own public GitHub repo, WITHOUT creating or pushing one.

    python scripts/check_repo.py [--export /tmp/fresh/leaselens]

It copies the project to a temporary folder, runs `git init` + `git add -A` THERE (so .gitignore decides what is included),
then reports: what is included, whether anything that must stay private got in, and any key or private path found in an
included file. With --export it also copies exactly the included files to the given folder (used for the fresh-clone dry run).
Secret values are read from your .env files only to search for them: they are never printed.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUST_BE_IGNORED = [".env", ".venv/x", ".cache/x", "__pycache__/x.pyc", "tests/__pycache__/x.pyc", ".pytest_cache/x", ".DS_Store", ".streamlit/secrets.toml"]
MUST_BE_INCLUDED = [".env.example", ".gitignore", "README.md", "CLAUDE.md", "requirements.txt", "app.py", "data/samples/core", "data/samples/ct",
                    "data/samples/agents", "data/prices.json", "output/data_check.md", "output/tokenomics.md", "output/speed.md", "tests/test_app.py"]
PRIVATE_PATTERNS = [r"/Users/[A-Za-z0-9_.-]+", r"C:\\Users\\", r"YALE MBA", r"Documents/YALE", r"/private/tmp/", r"/home/[a-z]+/"]
KEY_PATTERNS = [r"(?<![A-Za-z])sk-[A-Za-z0-9_-]{20,}", r"(?<![A-Za-z])pk-[A-Za-z0-9_-]{20,}", r"Bearer [A-Za-z0-9._-]{20,}", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{30,}"]
TEXT_SUFFIX = {".py", ".md", ".json", ".toml", ".txt", ".cfg", ".yml", ".yaml", ".example", ".gitignore", ".csv", ".html", ".js", ".css", ""}


def secret_values() -> list[str]:
    """Values of key/token-like variables in the .env files around this project (never printed)."""
    vals = []
    for env in (ROOT / ".env", ROOT.parent / ".env", ROOT.parent.parent / ".env"):
        if env.exists():
            for line in env.read_text(errors="ignore").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip().strip("'\"")
                    if re.search(r"KEY|TOKEN|SECRET|PASSWORD|CLIENT_ID|TENANT", k, re.I) and len(v) >= 8:
                        vals.append(v)
    return vals


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default=None)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="leaselens-repo-check-"))
    work = tmp / "leaselens"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".venv", "node_modules", ".git"))     # .venv is huge; its rule is tested below
    git(work, "init", "-q")
    git(work, "config", "user.email", "check@example.com")
    git(work, "config", "user.name", "check")
    git(work, "add", "-A")
    included = [p for p in git(work, "ls-files").splitlines() if p]
    problems: list[str] = []

    for probe in MUST_BE_IGNORED:
        (work / probe).parent.mkdir(parents=True, exist_ok=True)
        (work / probe).write_text("x")
        if subprocess.run(["git", "check-ignore", "-q", probe], cwd=work).returncode != 0:
            problems.append(f"NOT ignored by .gitignore: {probe}")
    for item in MUST_BE_INCLUDED:
        if not any(p == item or p.startswith(item.rstrip("/") + "/") for p in included):
            problems.append(f"missing from the repo: {item}")
    for p in included:
        if re.search(r"(^|/)(\.env|\.venv|\.cache|__pycache__|\.pytest_cache|\.DS_Store)(/|$)", p) and p != ".env.example":
            problems.append(f"must not be included: {p}")

    secrets = secret_values()
    private = [re.compile(x) for x in PRIVATE_PATTERNS]
    keys = [re.compile(x) for x in KEY_PATTERNS]
    emails: dict[str, int] = {}
    total = 0
    for rel in included:
        f = work / rel
        total += f.stat().st_size
        if f.suffix.lower() not in TEXT_SUFFIX:
            continue
        text = f.read_text(errors="ignore")
        if any(s in text for s in secrets):
            problems.append(f"a secret value from your .env appears in: {rel}")
        for rx in keys:
            if rx.search(text):
                problems.append(f"key-like string in: {rel}")
        for rx in private:
            if rx.search(text) and rel != "scripts/check_repo.py":
                problems.append(f"private path ({rx.pattern}) in: {rel}")
        for m in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", text):
            if not m.endswith(("example.com", "noreply.github.com")):
                emails[m] = emails.get(m, 0) + 1

    print(f"files that would be in the repo: {len(included)} ({total / 1e6:.1f} MB)")
    top = sorted({p.split('/')[0] for p in included})
    print("top level:", ", ".join(top))
    if emails:
        print("e-mail addresses found in included files (public once pushed):", {k: v for k, v in emails.items()})
    print("PROBLEMS:" if problems else "no problems found")
    for p in problems:
        print("  -", p)
    if args.export:
        dest = Path(args.export)
        if dest.exists():
            shutil.rmtree(dest)
        for rel in included:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work / rel, dest / rel)
        print(f"exported {len(included)} files to {dest}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
