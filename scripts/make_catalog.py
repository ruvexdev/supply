#!/usr/bin/env python3
"""Regenerate downloads/catalog.json, the list the Suite app reads.

Run it after you add or replace an .exe in downloads/. Keep this file in the repo
folder or in scripts/, then run:

    py make_catalog.py          (from the repo folder)
    py scripts\\make_catalog.py   (if it is inside scripts/)

Only tools whose .exe exists in downloads/ are listed. Locked boxes never appear.
Edit TOOLS (and bump the version) when you release something new.
"""
import hashlib
import json
import os
import sys
from datetime import date

SUITE_VERSION = "1.0"   # bump when you publish a new Suite.exe

TOOLS = [
    # id,     name,    what it does,        file,        version
    ("pull",  "Pull",  "yt-dlp downloader", "Pull.exe",  "1.0"),
    ("stash", "Stash", "folder backups",    "Stash.exe", "1.0"),
]

HERE = os.path.dirname(os.path.abspath(__file__))
# Works from the repo root or from scripts/: the root is the folder that holds index.html.
ROOT = HERE if os.path.isfile(os.path.join(HERE, "index.html")) else os.path.dirname(HERE)
DL = os.path.join(ROOT, "downloads")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.isfile(os.path.join(ROOT, "index.html")):
        print(f"Could not find the repo root (looked in {ROOT}). Put this file in the repo folder or in scripts/.")
        return 1
    os.makedirs(DL, exist_ok=True)
    tools = []
    for tid, name, job, fname, version in TOOLS:
        path = os.path.join(DL, fname)
        if not os.path.isfile(path):
            print(f"  skipped {name}: downloads/{fname} not found")
            continue
        tools.append({"id": tid, "name": name, "job": job, "file": fname, "version": version,
                      "size": os.path.getsize(path), "sha256": sha256(path)})
        print(f"  listed  {name} {version} ({os.path.getsize(path) / 1048576:.1f} MB)")
    if os.path.isfile(os.path.join(DL, "Suite.exe")):
        print("  Suite.exe found (the Suite app itself is not listed inside its own catalog)")
    data = {"updated": date.today().isoformat(), "suite": {"version": SUITE_VERSION}, "tools": tools}
    with open(os.path.join(DL, "catalog.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wrote downloads/catalog.json with {len(tools)} tool(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())