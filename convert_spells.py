"""
convert_spells.py — One-time DBC-to-JSON conversion for spell descriptions.

Takes the full Spell.dbc CSV export (~50MB, 49k rows, ~230 columns) and emits
a compact JSON file with just the columns the tooltip builder needs.

Optionally also takes a SpellDuration.dbc CSV export (~600 rows) — if
provided, each spell's duration is baked into the output JSON as durationMs.
This avoids needing the spellduration_dbc table populated in MySQL.

Usage:
    # With both files (recommended):
    python convert_spells.py

    # Just spell descriptions, no durations:
    python convert_spells.py --no-durations

    # Custom paths:
    python convert_spells.py --in Spell.csv --durations SpellDuration.csv \\
                             --out spell_descriptions.json

Once you have spell_descriptions.json, build_dungeons.py reads it automatically
and you don't need to run this again unless your client data changes.

Output schema:
    {
        "<spell_id>": {
            "name":        "Venom Shot",
            "description": "Chance to strike your ranged target with a Venom Shot for $s1 to $s2 Nature damage.",
            "auraDesc":    "",
            "basePoints":  [30, 0, 0],
            "dieSides":    [14, 0, 0],
            "procChance":  100,
            "effects":     [22, 0, 0],
            "durationIdx": 0,
            "durationMs":  0      // resolved duration in ms (0 if no duration)
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


def load_durations(path):
    """Read SpellDuration.csv → dict {DurationIndex: ms}.

    Expects columns ID and Duration. Other columns (DurationPerLevel,
    MaxDuration) are ignored — most item-proc effects have flat durations.

    Returns empty dict if the file is missing.
    """
    if not path or not os.path.exists(path):
        if path:
            print(f"  [info] {path} not found — durations will use durationIdx only")
        return {}

    durations = {}
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with open(path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            did = to_int(row.get('ID'))
            ms  = to_int(row.get('Duration'))
            if did > 0 and ms > 0:
                durations[did] = ms
    print(f"  [info] Loaded {len(durations)} duration entries from {path}")
    return durations


def convert(input_path, output_path, durations_path):
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    in_size = os.path.getsize(input_path)
    print(f"Reading {input_path} ({in_size / 1024 / 1024:.1f} MB)...")

    durations = load_durations(durations_path)

    spells = {}
    total_rows = 0
    skipped_no_text = 0
    spells_with_dur = 0

    # csv field size limit — some descriptions are long
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

    with open(input_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1

            sid = to_int(row.get('ID'))
            if sid <= 0:
                continue

            name = (row.get('Name_Lang_enUS') or '').strip()
            desc = (row.get('Description_Lang_enUS') or '').strip()
            aura_desc = (row.get('AuraDescription_Lang_enUS') or '').strip()

            # Skip spells with no descriptive text — pure auras / internal procs
            # we'd never display anyway. Saves ~18k entries (~36% of the file).
            if not desc and not aura_desc:
                skipped_no_text += 1
                continue

            duration_idx = to_int(row.get('DurationIndex'))
            duration_ms  = durations.get(duration_idx, 0) if duration_idx else 0
            if duration_ms > 0:
                spells_with_dur += 1

            spells[str(sid)] = {
                'name':        name,
                'description': desc,
                'auraDesc':    aura_desc,
                'basePoints':  [
                    to_int(row.get('EffectBasePoints_1')),
                    to_int(row.get('EffectBasePoints_2')),
                    to_int(row.get('EffectBasePoints_3')),
                ],
                'dieSides':    [
                    to_int(row.get('EffectDieSides_1')),
                    to_int(row.get('EffectDieSides_2')),
                    to_int(row.get('EffectDieSides_3')),
                ],
                'procChance':  to_int(row.get('ProcChance')),
                'effects':     [
                    to_int(row.get('Effect_1')),
                    to_int(row.get('Effect_2')),
                    to_int(row.get('Effect_3')),
                ],
                'durationIdx': duration_idx,
                'durationMs':  duration_ms,
            }

    print(f"  Processed {total_rows:>6} rows")
    print(f"  Skipped   {skipped_no_text:>6} rows (no description text)")
    print(f"  Kept      {len(spells):>6} spells")
    if durations:
        print(f"  With duration:  {spells_with_dur:>6} ({100*spells_with_dur/len(spells):.0f}%)")

    # Pretty-printed JSON would balloon the file; use compact output.
    print(f"Writing {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(spells, f, ensure_ascii=False, separators=(',', ':'))

    out_size = os.path.getsize(output_path)
    print(f"  Output: {out_size / 1024 / 1024:.1f} MB")
    print(f"  Compression: {in_size / out_size:.1f}x smaller")
    print()
    print("Done. build_dungeons.py will now pick up effect text automatically.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--in', dest='input', default='Spell.csv',
                    help='Input CSV (default: Spell.csv in current directory)')
    ap.add_argument('--out', dest='output', default='spell_descriptions.json',
                    help='Output JSON (default: spell_descriptions.json)')
    ap.add_argument('--durations', dest='durations', default='SpellDuration.csv',
                    help='Optional SpellDuration.csv to bake durations into '
                         'the output (default: SpellDuration.csv if present)')
    ap.add_argument('--no-durations', action='store_true',
                    help='Skip SpellDuration.csv lookup even if file exists')
    args = ap.parse_args()

    durations_path = None if args.no_durations else args.durations
    convert(args.input, args.output, durations_path)


if __name__ == '__main__':
    main()
