"""Refresh public event feeds and publish one native snapshot without logging secrets."""
import argparse
import json
from datetime import datetime
from pathlib import Path

from commutebar.snapshot import encode, upload
from commutebar.sources import TZ, refresh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--slot', choices=('a', 'b'), default='a')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    token = args.token_file.read_text().strip()
    if not token:
        raise SystemExit('Token file is empty')
    now = datetime.now(TZ)
    snapshot = refresh(now)
    upload(token, args.slot, encode(snapshot, now, config))
    print(json.dumps({'status': 'published', 'slot': args.slot, 'events': len(snapshot['events'])}))


if __name__ == '__main__':
    main()
