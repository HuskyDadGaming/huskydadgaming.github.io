"""
inspect_set.py — Diagnostic for Defias Leather (set 161) bonuses.

Writes its findings to inspect_set_output.txt in the same folder, so it
doesn't matter if the console window closes. Just open the .txt file
afterwards.
"""
import json, os, sys, traceback
from pathlib import Path

OUT_PATH = Path('inspect_set_output.txt')

# Open output file first so we can capture errors too. tee to stdout for
# the case where the user IS watching.
out = open(OUT_PATH, 'w', encoding='utf-8')
def log(msg=''):
    out.write(str(msg) + '\n')
    out.flush()
    try:
        print(msg)
    except Exception:
        pass

try:
    import mysql.connector

    DB_CONFIG = {
        'host':     os.environ.get('AC_DB_HOST', '127.0.0.1'),
        'port':     int(os.environ.get('AC_DB_PORT', '3306')),
        'user':     os.environ.get('AC_DB_USER', 'acore'),
        'password': os.environ['AC_DB_PASS'],
        'database': os.environ.get('AC_DB_WORLD', 'acore_world'),
    }

    sd_path = Path('spell_descriptions.json')
    if not sd_path.exists():
        log(f"ERROR: spell_descriptions.json not found in {Path('.').resolve()}")
        log("Run this script from C:\\KCraftDungeons\\")
        sys.exit(1)

    sd = json.loads(sd_path.read_text(encoding='utf-8'))
    log(f"Loaded {len(sd):,} spell descriptions")

    cnx = mysql.connector.connect(**DB_CONFIG)
    cur = cnx.cursor(dictionary=True)
    cur.execute("""
        SELECT Name_Lang_enUS,
               SetSpellID_1, SetSpellID_2, SetSpellID_3, SetSpellID_4,
               SetSpellID_5, SetSpellID_6, SetSpellID_7, SetSpellID_8,
               SetThreshold_1, SetThreshold_2, SetThreshold_3, SetThreshold_4,
               SetThreshold_5, SetThreshold_6, SetThreshold_7, SetThreshold_8
        FROM itemset_dbc WHERE ID = 161
    """)
    row = cur.fetchone()
    if not row:
        log("Set 161 not found in itemset_dbc")
    else:
        log(f"\nSet name: {row['Name_Lang_enUS']!r}")
        found_any = False
        for i in range(1, 9):
            sid = row[f'SetSpellID_{i}']
            thr = row[f'SetThreshold_{i}']
            if not sid or not thr:
                continue
            found_any = True
            log(f"\n  Bonus {i}: spell {sid}, requires {thr} pieces")
            s = sd.get(str(sid))
            if not s:
                log(f"    NOT IN spell_descriptions.json")
            else:
                desc = s.get('description', '') or ''
                aura = s.get('auraDesc', '') or ''
                bp = s.get('basePoints')
                log(f"    description: {desc[:120]!r}{'...' if len(desc) > 120 else ''}")
                log(f"    auraDesc:    {aura[:120]!r}{'...' if len(aura) > 120 else ''}")
                log(f"    basePoints:  {bp}")
        if not found_any:
            log("  (No bonus slots populated.)")
    cnx.close()
    log("\nDone.")
except Exception as e:
    log(f"\nERROR: {e}")
    log(traceback.format_exc())
finally:
    out.close()
    print(f"\nOutput written to: {OUT_PATH.resolve()}")
