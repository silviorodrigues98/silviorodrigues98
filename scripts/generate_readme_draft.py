#!/usr/bin/env python3
"""
Generate daily README draft for GitHub profile.
Reads: Todoist (completed today), Google Calendar (events today), Hermes session logs.
Writes: draft markdown to local file. No git push. You review, then run publish script.
"""

import os
import re
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

# ============================================================
# DATA COLLECTORS (Fixed)
# ============================================================

def collect_todoist_completed() -> List[Dict[str, str]]:
    """Return list of tasks completed today."""
    try:
        token = (Path.home() / '.hermes' / 'todoist_token.txt').read_text().strip()
        import urllib.request
        # Todoist v1 needs a timestamp. 400 error earlier suggests it might also want 'until' if 'since' is present? 
        # Actually v1 documentation says 'since' is the timestamp in seconds. Let's try omitting 'until'.
        # Re-reading: error was "Required argument is missing", "argument": "until".
        # Okay, let's include 'until' as current time.
        now = int(datetime.now().timestamp())
        since = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        url = f'https://api.todoist.com/api/v1/tasks/completed/by_completion_date?since={since}&until={now}&limit=50'
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        items = data.get('items', [])
        return [{'content': i.get('task', i).get('content', '')} for i in items]
    except: return []

def collect_calendar_events() -> List[Dict[str, str]]:
    try:
        gws = Path(os.environ['HERMES_HOME']) / 'skills' / 'productivity' / 'google-workspace' / 'scripts' / 'google_api.py'
        d = datetime.now().strftime('%Y-%m-%d')
        res = subprocess.run(['python', str(gws), 'calendar', 'list', '--start', d+'T00:00:00-03:00', '--end', d+'T23:59:59-03:00'], capture_output=True, text=True, timeout=30)
        return [{'summary': e.get('summary', 'Sem titulo')} for e in json.loads(res.stdout)]
    except: return []

def collect_hermes_activity() -> List[str]:
    """Return summary of last 24h Hermes cron activity."""
    ledger = Path(os.environ['HERMES_HOME']) / 'cron' / 'usage_audit.jsonl'
    if not ledger.exists(): return []

    # Map job_id -> friendly name
    names = {}
    try:
        data = json.loads((Path(os.environ['HERMES_HOME']) / 'cron' / 'jobs.json').read_text(encoding='utf-8'))
        jobs = data.get('jobs', data) if isinstance(data, dict) else data
        for j in jobs:
            names[j.get('id', '')] = j.get('name', j.get('label', ''))
    except: pass

    cutoff = datetime.utcnow() - timedelta(hours=24)
    agg = {}
    with open(ledger, 'r', encoding='utf-8') as f:
        for line in f.readlines()[-300:]:
            try:
                entry = json.loads(line)
                ts_str = entry.get('ts', '')
                if not ts_str: continue
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).replace(tzinfo=None)
                if ts <= cutoff: continue

                job = entry.get('job_id', '')
                if not job: continue
                # Short public label: drop parenthetical details, keep it readable
                label = names.get(job, '')
                if not label:
                    label = 'Automação'
                label = label.split('(')[0].strip()
                if len(label) > 34:
                    label = label[:31].rstrip() + '…'
                agg.setdefault(label, {'runs': 0, 'tokens': 0})
                agg[label]['runs'] += 1
                agg[label]['tokens'] += int(entry.get('total_tokens', 0))
            except: continue

    lines = []
    for label, v in sorted(agg.items(), key=lambda x: -x[1]['runs']):
        tok = v['tokens']
        tok_s = f"{tok/1000:.0f}K tokens" if tok else '—'
        desc = JOB_DESCRIPTIONS.get(label, '')
        desc_s = f" — {desc}" if desc else ''
        lines.append(f"- **{label}** · {v['runs']} exec · {tok_s}{desc_s}")
    return lines[:8]

# ============================================================
# DRAFT
# ============================================================

JOB_DESCRIPTIONS = {
    "LinkedIn Engajamento": "Interação orgânica para ampliar alcance de conteúdo.",
    "LinkedIn Engajamento Diario": "Interação orgânica para ampliar alcance de conteúdo.",
}

TEMPLATE = """*Log de atividades: {date}*

{body}
"""

def collect_github_commits() -> List[str]:
    """Commits pushed in the last 24h to public repos (GitHub public API)."""
    try:
        import urllib.request
        cutoff = datetime.utcnow() - timedelta(hours=24)
        req = urllib.request.Request(
            'https://api.github.com/users/silviorodrigues98/events/public?per_page=50',
            headers={'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=10) as r:
            events = json.load(r)
        out = []
        for ev in events:
            if ev.get('type') != 'PushEvent': continue
            ts = datetime.fromisoformat(ev.get('created_at', '1970-01-01').replace('Z', '+00:00')).replace(tzinfo=None)
            if ts <= cutoff: continue
            repo = ev.get('repo', {}).get('name', '').split('/')[-1]
            for c in ev.get('payload', {}).get('commits', []):
                msg = (c.get('message') or '').split('\n')[0][:70]
                if msg: out.append(f'- **`{repo}`** — {msg}')
        return out[:8]
    except: return []

def generate_draft() -> str:
    date_str = datetime.now().strftime('%d/%m/%Y')

    sections = []

    # 1. Commits (Tech focus)
    commits = collect_github_commits()
    if commits:
        sections.append('### 💻 Commits recentes\n' + '\n'.join(commits))

    # 2. Automation Activity (Hermes stats)
    hermes = collect_hermes_activity()
    if hermes:
        sections.append('### ⚙️ Automações ativas\n' + '\n'.join(hermes))

    if not sections:
        return '*Sem atividades significativas nas últimas 24h.*'

    return TEMPLATE.format(date=date_str, body='\n\n'.join(sections))

def main():
    out = Path(os.environ['HERMES_HOME']) / 'cron' / 'output' / f'readme_draft_{datetime.now().strftime("%Y-%m-%d")}.md'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_draft(), encoding='utf-8')
    print(f"Draft: {out}")

if __name__ == '__main__': main()