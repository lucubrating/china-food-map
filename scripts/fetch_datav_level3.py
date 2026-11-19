#!/usr/bin/env python3
"""Fetch third-level boundary files from DataV GeoAtlas.

One file per second-level unit that has a third level below it. Each file holds
the shapes, names and codes of that unit's third-level units.

Safe to re-run: files already on disk and readable are skipped, so an interrupted
run picks up where it stopped.

Ask before running. It downloads about 25 MB into research/downloads/,
which is kept private. Run it isolated, because it reads downloaded files:

    python3 -I scripts/fetch_datav_level3.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'research' / 'downloads' / 'datav-geoatlas'
SECOND_LEVEL = SOURCE / '100000_full_city.json'
TARGET = SOURCE / 'level-3'
BASE_URL = 'https://geo.datav.aliyun.com/areas_v3/bound'
PAUSE = 0.3  # seconds between requests, to go easy on the server


def parents():
    """Second-level units that the source says have units below them."""
    with open(SECOND_LEVEL, encoding='utf-8') as handle:
        features = json.load(handle)['features']
    found = []
    for feature in features:
        props = feature['properties']
        if props.get('level') == 'city' and props.get('childrenNum'):
            found.append((str(props['adcode']), str(props.get('name', ''))))
    return sorted(found)


def readable(path):
    """True if the file is a feature collection with at least one feature."""
    try:
        with open(path, encoding='utf-8') as handle:
            return len(json.load(handle)['features']) > 0
    except (OSError, ValueError, KeyError, TypeError):
        return False


def fetch(url, path):
    """Download to a temporary name, then rename, so a cut-off leaves no half file."""
    part = path.with_suffix('.part')
    result = subprocess.run(
        ['curl', '-sS', '--fail', '--compressed', '-m', '60', '-o', str(part), url],
        capture_output=True, text=True)
    if result.returncode != 0 or not readable(part):
        part.unlink(missing_ok=True)
        return result.stderr.strip() or 'not a readable feature collection'
    part.replace(path)
    return None


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    units = parents()
    fetched = skipped = 0
    failed = []
    for index, (code, name) in enumerate(units, 1):
        path = TARGET / f'{code}_full.json'
        if readable(path):
            skipped += 1
        else:
            error = None
            for attempt in range(3):
                error = fetch(f'{BASE_URL}/{code}_full.json', path)
                if error is None:
                    break
                time.sleep(2 * (attempt + 1))
            if error is None:
                fetched += 1
            else:
                failed.append((code, name, error))
            time.sleep(PAUSE)
        if index % 40 == 0:
            print(f'  {index} of {len(units)} checked', flush=True)

    size = sum(item.stat().st_size for item in TARGET.glob('*_full.json'))
    print(f'{len(units)} second-level units with a third level')
    print(f'fetched {fetched}, already there {skipped}, failed {len(failed)}')
    print(f'{size / 1e6:.1f} MB in {TARGET.relative_to(ROOT)}')
    for code, name, error in failed:
        print(f'  FAILED {code} {name}: {error}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
