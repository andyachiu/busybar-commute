import argparse
import json
import os
import sys
import subprocess
import time
import fcntl
import signal
from datetime import datetime
from pathlib import Path
from .sources import TZ, refresh
from .planner import plan
from .view import render

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description='Event-aware commute preview; no device writes by default.')
    parser.add_argument('--stop', action='store_true', help='Stop the watcher for this data directory')
    parser.add_argument('--watch', action='store_true', help='Run until stopped: refresh schedules every 15 minutes and update the USB bar every minute')
    parser.add_argument('--send', action='store_true', help='Send current advice to the USB BUSY Bar for two minutes')
    parser.add_argument('--device-test', action='store_true', help='Show a one-minute USB test, including outside commute hours')
    parser.add_argument('--refresh', action='store_true', help='Fetch public event sources')
    parser.add_argument('--traffic', action='store_true', help='Use GOOGLE_MAPS_API_KEY; billed Routes requests may apply')
    parser.add_argument('--at', help='Simulate a local ISO date/time using cached schedules; disables live traffic')
    parser.add_argument('--config', type=Path, default=ROOT/'config.local.json')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data')
    args = parser.parse_args()
    if args.stop:
        lock_path = args.data_dir/'watch.lock'
        if not lock_path.exists():
            print('Commute Bar is not running.')
            return
        with lock_path.open('r+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pid = int(lock.read().strip())
                os.kill(pid, signal.SIGINT)
                print('Stop requested. Device messages expire within two minutes.')
            else:
                print('Commute Bar is not running.')
        return
    if args.at and (args.refresh or args.traffic or args.send or args.device_test or args.watch):
        parser.error('--at is an offline simulation; cannot combine with live fetches, traffic or device writes')
    if args.watch:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        watch_lock = (args.data_dir/'watch.lock').open('a+')
        try:
            fcntl.flock(watch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Commute Bar is already monitoring this data directory')
        watch_lock.seek(0)
        watch_lock.truncate()
        watch_lock.write(str(os.getpid()))
        watch_lock.flush()
        if args.traffic or args.device_test:
            parser.error('--watch currently uses event advice only; traffic estimates and device tests are one-shot')
        command = [sys.executable, '-m', 'commutebar', '--send', '--config', str(args.config.resolve()), '--data-dir', str(args.data_dir.resolve())]
        print('Watching commute events. Refresh every 15 minutes; USB display every minute during weekday commute window. Ctrl-C to stop.', flush=True)
        last_refresh = 0
        try:
            while True:
                refresh_due = time.monotonic() - last_refresh >= 900 or not last_refresh
                subprocess.run(command + (['--refresh'] if refresh_due else []), cwd=ROOT, check=False)
                if refresh_due:
                    last_refresh = time.monotonic()
                time.sleep(60)
        except KeyboardInterrupt:
            print('Stopped. Device messages expire automatically within two minutes.')
        return
    config = json.loads(args.config.read_text())
    now = datetime.now(TZ)
    if args.at:
        now = datetime.fromisoformat(args.at)
        now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    cache = args.data_dir/'events.json'
    if args.refresh:
        snapshot = refresh(now)
        temporary = cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(snapshot, indent=2))
        temporary.replace(cache)
    elif cache.exists():
        snapshot = json.loads(cache.read_text())
    else:
        parser.error('No cached data. Run with --refresh first.')
    result = plan(snapshot, config, now)
    if args.traffic:
        key = os.environ.get('GOOGLE_MAPS_API_KEY')
        if not key:
            parser.error('--traffic requires GOOGLE_MAPS_API_KEY in the environment')
        from .traffic import enrich
        result = enrich(result, config, now, key)
    if args.at:
        result['title'] = 'SIMULATION · ' + result['title']
        result['mode'] = 'OFFLINE SIMULATION · ' + result['mode']
    output = args.data_dir/('simulation.html' if args.at else 'preview.html')
    render(result, output)
    print(result['title'])
    print(result['action'])
    print(result['mode'])
    for event in result['events']:
        print(f"  {event['title']} — {event['timing']}: {event['reason']}")
    print('Coverage gaps: ' + ', '.join(result['missing']))
    print(f'Preview: {output}')
    if args.send or args.device_test:
        from .device import send
        print('BUSY Bar: ' + send(result, test=args.device_test))


if __name__ == '__main__':
    main()
