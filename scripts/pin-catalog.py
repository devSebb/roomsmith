#!/usr/bin/env python3
"""Fill the catalog entry draft with a real commit and write the file to submit.

    scripts/pin-catalog.py [SHA] [--out plugin-catalog/roomsmith.yaml]

Default SHA = HEAD. Refuses a dirty tree, an unpushed HEAD, or a HEAD whose CI
run is not green (needs `gh`). The output is the one file the catalog PR adds to
NousResearch/hermes-agent. Re-pinning later = a new PR, so pin once, late.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sha", nargs="?", default=None)
    ap.add_argument("--out", default=str(ROOT / "dist" / "plugin-catalog" / "roomsmith.yaml"))
    ap.add_argument("--skip-ci-check", action="store_true")
    a = ap.parse_args()

    sha = sh("git", "rev-parse", a.sha or "HEAD")
    if len(sha) != 40:
        print("not a full SHA:", sha); return 2
    if sh("git", "status", "--porcelain"):
        print("working tree is dirty — commit or stash first"); return 2
    try:
        sh("git", "merge-base", "--is-ancestor", sha, "origin/main")
    except subprocess.CalledProcessError:
        sh("git", "fetch", "origin", "main")
        try:
            sh("git", "merge-base", "--is-ancestor", sha, "origin/main")
        except subprocess.CalledProcessError:
            print(f"{sha[:7]} is not on origin/main — push first"); return 2
    if not a.skip_ci_check:
        runs = json.loads(sh("gh", "run", "list", "-R", "devSebb/roomsmith", "--commit", sha, "--json", "status,conclusion,workflowName"))
        ok = [r for r in runs if r["workflowName"] == "validate" and r["status"] == "completed" and r["conclusion"] == "success"]
        if not ok:
            print(f"no green 'validate' run for {sha[:7]}: {runs}"); return 2

    draft = (ROOT / "catalog" / "roomsmith.yaml").read_text()
    body = "\n".join(l for l in draft.splitlines() if not l.startswith("#")).strip() + "\n"
    if "<SHA>" not in body:
        print("draft has no <SHA> placeholder"); return 2
    out_text = body.replace("<SHA>", sha)
    # every raw.githubusercontent URL must point at a file that exists at that commit
    for url in re.findall(r"https://raw\.githubusercontent\.com/devSebb/roomsmith/[0-9a-f]{40}/(\S+?)\"", out_text):
        try:
            sh("git", "cat-file", "-e", f"{sha}:{url}")
        except subprocess.CalledProcessError:
            print(f"referenced file missing at {sha[:7]}: {url}"); return 2
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_text)
    print(f"wrote {out} pinned to {sha}")
    print("next: copy it to <hermes-agent fork>/plugin-catalog/roomsmith.yaml and open the PR from devSebb (see docs/ROOMSMITH_PLAN.md §16)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
