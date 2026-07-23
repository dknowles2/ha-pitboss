#!/usr/bin/env python3
"""Sync the pinned `pytboss` version from requirements.txt into manifest.json.

Keeps custom_components/pitboss/manifest.json's "requirements" entry aligned
with requirements.txt so Dependabot bumps to one don't silently drift from
the other. Exits nonzero (and leaves files unchanged) if pytboss can't be
found in requirements.txt.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
MANIFEST = ROOT / "custom_components" / "pitboss" / "manifest.json"
PACKAGE = "pytboss"


def pinned_version(requirements_text: str, package: str) -> str:
    match = re.search(rf"^{re.escape(package)}==([^\s]+)$", requirements_text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find pinned '{package}==' line in {REQUIREMENTS}")
    return match.group(1)


def main() -> int:
    version = pinned_version(REQUIREMENTS.read_text(), PACKAGE)
    manifest = json.loads(MANIFEST.read_text())

    updated = [
        f"{PACKAGE}=={version}" if req.split("==")[0] == PACKAGE else req
        for req in manifest["requirements"]
    ]

    if updated == manifest["requirements"]:
        print(f"manifest.json already in sync ({PACKAGE}=={version})")
        return 0

    manifest["requirements"] = updated
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Updated manifest.json requirements to {PACKAGE}=={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
