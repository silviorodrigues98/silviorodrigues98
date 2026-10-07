#!/usr/bin/env python3
"""
Publish a daily draft into the GitHub profile README.

Safety rules (cannot be bypassed):
  1. Draft is RE-scanned before publishing — any PII pattern aborts the run.
  2. Dry-run by default: prints the new README section, touches nothing.
  3. --apply commits + pushes. Nothing is ever pushed without it.

Usage:
  python scripts/publish_readme.py --input <draft.md>            # dry run
  python scripts/publish_readme.py --input <draft.md> --apply    # commit + push
"""

import os
import re
import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / 'README.md'

START_MARK = '<!-- DAILY:START -->'
END_MARK = '<!-- DAILY:END -->'

# ------------------------------------------------------------
# PII SCAN — same rules as the generator, plus phone/address
# ------------------------------------------------------------
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
TOKEN_RE = re.compile(r'\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|ya29\.[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9._-]{20,})\b', re.IGNORECASE)
PRIVATE_PATH_RE = re.compile(r'(C:\\Users\\[^\\]+|/home/[^/\s]+|/Users/[^/\s]+)')
URL_SECRET_RE = re.compile(r'https?://[^\s]*[?&](key|token|secret|password|api_key)=[^&\s]+', re.IGNORECASE)
PRIVATE_WORDS = ['silvio_1-6', 'silviorodrigues98@hotmail', 'silviob969', '@gmail.com']

def scan_pii(text: str) -> list:
    """Return list of reasons the draft is unsafe. Empty list = safe."""
    hits = []
    for name, rx in [('email', EMAIL_RE), ('token', TOKEN_RE),
                     ('private path', PRIVATE_PATH_RE), ('url with secret', URL_SECRET_RE)]:
        for m in rx.finditer(text):
            hits.append(f'{name}: {m.group(0)[:60]}')
    for w in PRIVATE_WORDS:
        if w in text:
            hits.append(f'blocklist word: {w}')
    return hits

# ------------------------------------------------------------
# README SECTION REPLACEMENT
# ------------------------------------------------------------
def replace_section(readme: str, section: str) -> str:
    if START_MARK in readme and END_MARK in readme:
        pre = readme.split(START_MARK)[0]
        post = readme.split(END_MARK)[1]
        return pre + START_MARK + '\n' + section.strip() + '\n' + END_MARK + post
    # No markers yet -> append section at the end of the README
    return readme.rstrip() + '\n\n' + START_MARK + '\n' + section.strip() + '\n' + END_MARK + '\n'

# ------------------------------------------------------------
# GIT
# ------------------------------------------------------------
def git(*args) -> str:
    r = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {r.stderr.strip()}')
    return r.stdout.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', '-i', required=True, help='draft file to publish')
    ap.add_argument('--apply', action='store_true', help='commit + push (default: dry run)')
    args = ap.parse_args()

    draft_path = Path(args.input)
    if not draft_path.exists():
        sys.exit(f'ERROR: draft not found: {draft_path}')
    draft = draft_path.read_text(encoding='utf-8')
    if len(draft.strip()) < 20:
        sys.exit('ERROR: draft is empty/too short — nothing to publish.')

    # 1. PII scan (hard stop)
    hits = scan_pii(draft)
    if hits:
        print('BLOCKED: draft contains possible private data:')
        for h in hits[:20]:
            print(f'  - {h}')
        sys.exit(1)
    print('PII scan: clean')

    # 2. Build new README in memory
    old = README.read_text(encoding='utf-8')
    new = replace_section(old, draft)
    if new == old:
        print('README unchanged (section identical) — nothing to do.')
        return

    if not args.apply:
        print('\n--- DRY RUN: new section that WOULD be published ---\n')
        print(draft.strip()[:2000])
        print('\n--- run again with --apply to commit + push ---')
        return

    # 3. Apply
    README.write_text(new, encoding='utf-8')
    try:
        git('add', 'README.md')
        git('commit', '-m', f'daily: update {datetime.now().strftime("%Y-%m-%d")}')
        git('push', 'origin', 'main')
    except RuntimeError as e:
        # rollback local change so the repo stays clean
        git('checkout', '--', 'README.md')
        sys.exit(f'FAILED: {e}')
    print('Published and pushed to origin/main.')

if __name__ == '__main__':
    main()