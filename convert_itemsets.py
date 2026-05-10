"""
convert_itemsets.py — One-time DBC-to-JSON conversion for item sets.

Takes ItemSet.dbc CSV export (~500 rows) and emits a compact JSON file with
just the columns build_dungeons.py needs to render set tooltips. Equivalent
to convert_spells.py but for sets.

Why: AzerothCore loads ItemSet.dbc straight into the worldserver and doesn't
always mirror it to the itemset_dbc MySQL table, so build_dungeons.py can't
query it. This script bakes the data once into JSON.

Usage:
    python convert_itemsets.py
    # or:
    python convert_itemsets.py --in ItemSet.csv --out itemsets.json

Run once after exporting fresh DBCs. build_dungeons.py picks it up
automatically.

Output schema:
    {
        "<set_id>": {
            "name":    "Defias Leather",
            "items":   [10399, 10403, 10402, 10401, 10400],
            "bonuses": [
                {"spellId": 41733, "pieces": 5},
                {"spellId": 41732, "pieces": 3},
                ...
            ]
        },
        ...
    }
"""

import argparse
import csv
import json
import os
import sys


def to_int(v):
    """Lenient int parse — empty / None / non-numeric → 0."""
    if v is None or v == '':
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0


def convert(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {input_path}...")
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

    sets = {}
    total_rows = 0
    skipped_no_name = 0

    with open(input_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            sid = to_int(row.get('ID'))
            if sid <= 0:
                continue

            name = (row.get('Name_Lang_enUS') or '').strip()
            if not name:
                skipped_no_name += 1
                continue

            # Pieces (up to 17 slots — most sets use 5–10)
            items = []
            for i in range(1, 18):
                iid = to_int(row.get(f'ItemID_{i}'))
                if iid > 0:
                    items.append(iid)

            # Bonuses — pair spell with threshold, drop empty slots
            bonuses = []
            for i in range(1, 9):
                spell_id  = to_int(row.get(f'SetSpellID_{i}'))
                threshold = to_int(row.get(f'SetThreshold_{i}'))
                if spell_id > 0 and threshold > 0:
                    bonuses.append({'spellId': spell_id, 'pieces': threshold})
            # Sort bonuses by piece count so consumers don't have to.
            bonuses.sort(key=lambda b: b['pieces'])

            sets[str(sid)] = {
                'name':    name,
                'items':   items,
                'bonuses': bonuses,
            }

    print(f"  Processed {total_rows:>5} rows")
    if skipped_no_name:
        print(f"  Skipped   {skipped_no_name:>5} rows (no English name)")
    print(f"  Kept      {len(sets):>5} sets")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sets, f, ensure_ascii=False, separators=(',', ':'))

    out_size = os.path.getsize(output_path)
    print(f"\n  Output: {output_path} ({out_size / 1024:.1f} KB)")
    print("\nDone. build_dungeons.py will now pick up set info automatically.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--in',  dest='input',  default='ItemSet.csv',
                    help='Input CSV (default: ItemSet.csv)')
    ap.add_argument('--out', dest='output', default='itemsets.json',
                    help='Output JSON (default: itemsets.json)')
    args = ap.parse_args()
    convert(args.input, args.output)


if __name__ == '__main__':
    main()
