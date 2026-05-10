# KCraft dungeon builder

Reads `build_config.yaml` + queries your AzerothCore database to produce
`loot-data.json` for the Find Loot tab on `index.html`.

## Setup (one time)

1. **Install Python dependencies** (you already have `mysql-connector-python` from `armoury_api.py`; you just need PyYAML):
   ```
   pip install pyyaml
   ```

2. **Set environment variables** (same as `armoury_api.py`):
   ```
   set AC_DB_HOST=127.0.0.1
   set AC_DB_PORT=3306
   set AC_DB_USER=acore
   set AC_DB_PASS=<your password>
   set AC_DB_WORLD=acore_world
   ```
   On a Windows server, you can use `setx VAR value` to make them persistent.

3. **Place files together**:
   - `build_dungeons.py`
   - `build_config.yaml`
   They should live in the same folder (or pass `--config path/to/yaml`).

## First run — Shadowfang Keep only (validation)

```
python build_dungeons.py --dungeon shadowfang-keep --dry-run
```

This connects to your DB, processes only SFK, and prints a summary **without writing files**.
Expected output:

```
Connecting to acore@127.0.0.1:3306/acore_world ...

[shadowfang-keep] map=33 quality_floor=2 bosses=9
  9 bosses, ~25-35 items

============================================================
Total: ~25-35 items across 9 bosses in 1 dungeons

(--dry-run: not writing output file)
```

If you see this, the pipeline is working. If it fails, the most likely
issues are:
- **DB connection refused**: check env vars
- **`mysql.connector` not found**: `pip install mysql-connector-python`
- **`yaml` not found**: `pip install pyyaml`

## Generate the full data

```
python build_dungeons.py
```

Processes all 9 dungeons, writes `loot-data.json` (~80-150 KB).

## Compare to existing data

To verify the output is sensible, compare against your current site:

```
python build_dungeons.py --dungeon shadowfang-keep
```

Then in another file (e.g. `extract_old.py`) extract the SFK section of
the existing JSON from `index.html` and diff. Items shown should be similar
but **typically more correct** in the new output (e.g. proper `data-roles`
tags from smart filter rules, cleaner class lists).

## Update the website

The output JSON goes into `index.html` between
`<script id="loot-data" type="application/json">` and `</script>`.

For now, that's a manual paste. A future improvement is adding a flag to
`build_dungeons.py` that updates `index.html` directly.

(HTML page generation for the 9 dungeon pages is a future iteration —
this MVP just produces the JSON for the Find Loot tab.)

## CLI options

| Flag | Purpose |
|---|---|
| `--config PATH` | Path to YAML config (default `build_config.yaml`) |
| `--out PATH` | Output JSON path (default `loot-data.json`) |
| `--dungeon SLUG` | Process only this dungeon (e.g. `--dungeon shadowfang-keep`) |
| `--dry-run` | Print summary, write nothing |

## What it does

For each boss in `build_config.yaml`:

1. Looks up the boss in `creature_template`
2. Pulls all items from `creature_loot_template` joined to `item_template`
3. Filters by `quality_floor` (default 2 = greens and above)
4. Computes:
   - **slot** — e.g. "Chest (Plate)" with armor type
   - **stats** — formatted strings like "+10 Stamina", "+471 Armor"
   - **classes** — list of class slugs that can use the item (armor proficiency + AllowableClass bitmask)
   - **roles** — which roles (tank/heal/melee/ranged) the item supports, using the same logic as `smart_filter_block.js`
5. Outputs an item record matching the existing JSON format

## What this MVP does NOT do (yet)

- Generate the 9 dungeon HTML pages — only the JSON for `index.html`'s Find Loot tab. Pages still need their inline data refreshed manually.
- Update `index.html` automatically — you paste the JSON yourself.
- Handle Death Knight starting zone restrictions or special loot edge cases.
- Use `reference_loot_template` (some bosses' loot tables reference shared pools — those references aren't followed yet, may cause some items to be missing).

These are all next iterations.

## Iteration roadmap

1. **Iteration 1 (this MVP)**: Generate JSON for one dungeon, validate
2. **Iteration 2**: Generate JSON for all 9, drop into `index.html`
3. **Iteration 3**: Generate the 9 dungeon HTML pages from a template
4. **Iteration 4**: Add `reference_loot_template` resolution if items are missing
5. **Iteration 5**: Add curation features (item exclusions, stat overrides)
