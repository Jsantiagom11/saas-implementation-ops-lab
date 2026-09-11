from __future__ import annotations

import re
import subprocess
from pathlib import Path

SELF = "scripts/check_publication.py"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("unix home path", re.compile(r"/home/[A-Za-z0-9._-]+/")),
    (
        "windows user path",
        re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\r\n]+\\\\"),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    ),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    (
        "personal email",
        re.compile(
            r"\b[A-Z0-9._%+-]+@(gmail|hotmail|outlook|yahoo)\.[A-Z]{2,}\b",
            re.I,
        ),
    ),
    (
        "agent handoff context",
        re.compile(
            r"\b(?:authorized by the handoff|task-supplied|user-reported commit)\b",
            re.I,
        ),
    ),
    (
        "agent workspace context",
        re.compile(r"Applicable `?AGENTS\.md`?.*parent workspace", re.I),
    ),
)


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(item.decode()) for item in raw.split(b"\0") if item]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if path.as_posix() == SELF or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path}:{line_no}: {label}")

    if findings:
        print("Publication guard failed:")
        print("\n".join(f"- {item}" for item in findings))
        return 1

    print("Publication guard passed: no blocked privacy/secret patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
