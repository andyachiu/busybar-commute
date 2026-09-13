"""Escaped, standalone HTML preview; no external assets or exposed credentials."""
from html import escape
from pathlib import Path
import json
from .details import event_details


def render(plan, path):
    esc = lambda x: escape(str(x), quote=True)
    def link(url, label):
        if not url.startswith('https://'):
            return esc(label)
        return f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(label)} ↗</a>'
    def details(event):
        return '<br>'.join(esc(row) for row in event_details(event, plan['fetched_at'], plan['stale'], plan.get('show_scores', True)))
    event_rows = ''.join(f'<article><span class="pill">{esc(e["venue"])}</span><h3>{link(e["url"],e["title"])}</h3><p>{details(e)}</p><p class="muted">{esc(e["reason"])}</p></article>' for e in plan['events']) or '<p class="muted">No events found in connected feeds for this day. This is not an all-clear.</p>'
    source_rows = ''.join(f'<div class="source"><div>{link(s["url"],s["name"])}<span class="pill {esc(s["status"])}">{esc(s["status"])}</span></div><p class="muted">{esc(s["detail"])}</p></div>' for s in plan['sources'])
    upcoming = ''.join(f'<div class="upcoming"><span>{esc(e["date"])}</span><div>{link(e["url"], e["title"])}<small>{esc(e["venue"])}</small></div></div>' for e in plan['upcoming']) or '<p class="muted">No upcoming events returned.</p>'
    front = plan['front_action']
    back = (plan['events'][0]['title'] if plan['events'] else 'Check live traffic')
    doc = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Home by five · Commute Bar</title><style>
:root{color-scheme:dark;--bg:#0e1418;--panel:#172127;--line:#2b3b42;--muted:#a3b6bf;--accent:#a9efcb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f4f8fa;font:16px/1.5 system-ui,sans-serif}main{max-width:1100px;margin:0 auto;padding:44px 24px}header{display:flex;justify-content:space-between;gap:24px;align-items:center}.eyebrow{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:2px}h1{font-size:clamp(30px,5vw,48px);letter-spacing:-2px;margin:8px 0}h2{font-size:21px;margin-top:0}h3{font-size:18px;margin:12px 0}p{margin:8px 0 16px}a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}.muted,small{color:var(--muted)}.grid{display:grid;grid-template-columns:1.35fr 1fr;gap:22px;margin:24px 0}.panel,article{padding:24px;border:1px solid var(--line);border-radius:16px;background:var(--panel)}.hero{border-top:3px solid #eab65c}.hero h2{font-size:28px}.stats{display:flex;gap:30px;padding:20px 0;flex-wrap:wrap}.stats strong{display:block;font-size:26px}.stats small{display:block}.pill{font-size:11px;letter-spacing:.4px;border:1px solid var(--line);border-radius:20px;padding:4px 9px;display:inline-block;color:var(--muted)}.ok{color:var(--accent)}.error,.review,.unavailable{color:#eab65c}.source{padding:14px 0;border-bottom:1px solid var(--line)}.source .pill{float:right}.source p{font-size:13px;margin:8px 0}.source:last-child{border:0}.bar{background:#050808;border:8px solid #252d30;border-radius:16px;padding:28px 16px;color:#ffd073;letter-spacing:5px;text-align:center;font:700 24px ui-monospace,monospace;box-shadow:0 10px 25px #0005}.device small{display:block;margin:16px 0}.events{display:grid;gap:14px}.upcoming{display:grid;grid-template-columns:100px 1fr;gap:15px;padding:14px 0;border-bottom:1px solid var(--line);font-size:14px}.upcoming small{display:block}.notice{color:#ffce7a;background:#302719;border-radius:8px;padding:12px 16px;font-size:13px}.foot{font-size:12px;color:var(--muted);margin-top:24px}button{background:#a9efcb;color:#102219;border:0;border-radius:8px;padding:10px 16px;cursor:pointer;font:inherit}body.demo header:before{content:'DEMO';color:#ffce7a}#aged{display:none}@media(max-width:740px){.grid{grid-template-columns:1fr}header{display:block}.stats{gap:18px}main{padding:24px 16px}.bar{font-size:20px}h1{letter-spacing:-1px}}
</style><body><main><header><div><div class="eyebrow">Commute Bar / San Francisco</div><h1>Home by five.</h1><p class="muted">Office → Potrero Hill · Driving</p></div><div><span class="pill">LOCAL PREVIEW</span><p class="muted">DAY</p></div></header>
<div id="aged" class="notice">This preview is no longer current. Refresh the app and check live traffic.</div>
<div class="grid"><section class="panel hero"><div class="eyebrow">Departure outlook</div><h2 id="headline">TITLE</h2><p id="advice">ACTION</p><div class="stats"><div><small>Usual departure</small><strong>DEPARTURE</strong></div><div><small>Proposed target</small><strong>TARGET</strong></div><div><small>Must be home</small><strong>DEADLINE</strong></div></div><p class="muted" id="mode">MODE</p><div class="notice">Partial event coverage. Timing buffers are assumptions; route-specific event impact has not been verified.</div></section>
<section class="panel device"><div class="eyebrow">BUSY Bar concept</div><p class="muted">Message preview · USB display tested</p><div class="bar" id="bar">FRONT</div><small>BACK</small><p class="muted">Event detail stays here; the physical display will use short labels.</p><button onclick="location.reload()">Reload preview</button></section></div>
<div class="grid"><section><h2>Events on this day</h2><div class="events">EVENTS</div><h2 style="margin-top:28px">Looking ahead</h2>UPCOMING</section><aside class="panel"><h2>Source coverage</h2>SOURCES</aside></div><p class="foot">Schedules fetched FETCHED · Preview generated RENDERED. Re-run the app to fetch new data. This page does not refresh feeds itself.</p></main><script>
const generated = new Date(STAMP);function ageCheck(){const age=Date.now()-generated.getTime();if(age>10*60*1000||age< -5*60*1000){document.getElementById('aged').style.display='block';document.getElementById('advice').textContent='Run a fresh preview and check maps before leaving.';document.getElementById('headline').textContent='Preview needs refresh';document.getElementById('bar').textContent='CHECK DATA';}}ageCheck();setInterval(ageCheck,30000);
</script></body></html>'''
    values = dict(DAY=plan['rendered_at'][:10], TITLE=plan['title'], ACTION=plan['action'], DEPARTURE=plan['departure'], TARGET=plan['target'], DEADLINE=plan['deadline'], MODE=plan['mode'], FRONT=front, BACK=back, FETCHED=plan['fetched_at'], RENDERED=plan['rendered_at'])
    # Single pass prevents user-controlled event strings from being treated as template tokens.
    import re
    values = {k:esc(v) for k,v in values.items()}
    values.update(EVENTS=event_rows, SOURCES=source_rows, UPCOMING=upcoming, STAMP=json.dumps(plan['rendered_at']))
    doc = re.sub(r'\b('+'|'.join(values)+r')\b', lambda m:values[m[0]], doc)
    Path(path).write_text(doc)
