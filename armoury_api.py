"""KCraft Armoury API
==================

Read-only HTTPS service that exposes character data from your AzerothCore
server's MySQL database. Designed to run on the same box as the game server.

Endpoints:
    GET /healthz            -> {"ok": true}
    GET /armoury             -> list of {name, level, class, race} for whitelisted accounts
    GET /armoury/{name}      -> full data: char info, equipped, bags, bank

Auth: X-API-Key header. Single shared key, configurable via env var.

Run with self-signed cert:
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \\
        -keyout key.pem -out cert.pem -subj "/CN=kcraft-armoury"
    uvicorn armoury_api:app --host 0.0.0.0 --port 47291 \\
        --ssl-keyfile key.pem --ssl-certfile cert.pem
"""

import json
import os
import re
from typing import Optional, List, Dict, Any

import mysql.connector
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware


# ---------------------------------------------------------------------------
# Tooltip "effects" helpers — inlined from build_dungeons.py so this file is
# self-contained. Kept in sync with the loot builder.
# ---------------------------------------------------------------------------

# spelltrigger values from item_template
SPELL_TRIGGER_LABELS = {
    0: 'Use',           # ON_USE
    1: 'Equip',         # ON_EQUIP
    2: 'Chance on hit', # CHANCE_ON_HIT
    3: '',              # SOULSTONE — skip
    4: 'Use',           # ON_NO_DELAY_USE
    5: '',              # LEARN_SPELL_ID — skip
    6: '',              # alt LEARN_SPELL_ID — skip
}

_PLACEHOLDER_RE = re.compile(
    r'\$(?P<ref>\d*)(?:(?P<type>[sSmM])(?P<idx>[1-3])|(?P<dur>[dD]))'
)


def load_spell_descriptions(json_path: str) -> Dict[str, Any]:
    """Load spell_descriptions.json (produced by convert_spells.py).
    Returns {} if the file is missing — equip text just won't render."""
    if not os.path.exists(json_path):
        print(f"  [info] {json_path} not found — skipping equip/use effect text")
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"  [info] Loaded {len(data)} spell descriptions from {json_path}")
    return data


def fetch_durations(cnx) -> Dict[int, int]:
    """Pull spellduration_dbc into a {DurationIndex: ms} dict for $d substitution."""
    cur = cnx.cursor(dictionary=True)
    try:
        cur.execute("SELECT ID, Duration FROM spellduration_dbc")
        rows = cur.fetchall()
        durations = {row['ID']: row['Duration'] for row in rows}
        print(f"  [info] Loaded {len(durations)} duration entries from spellduration_dbc")
        return durations
    except mysql.connector.Error as e:
        print(f"  [info] Could not query spellduration_dbc: {e}")
        return {}
    finally:
        cur.close()


def _format_duration(ms: int) -> str:
    """Render a millisecond duration as 'X sec', 'Y min', 'Z hour(s)'."""
    if ms <= 0:
        return ''
    sec = ms / 1000.0
    if sec < 1:
        return f"{int(ms)} ms"
    if sec == int(sec):
        sec = int(sec)
    if sec < 60:
        return f"{sec} sec"
    if sec < 3600:
        mins = int(sec // 60)
        rem  = int(sec % 60)
        return f"{mins} min" if rem == 0 else f"{mins} min {rem} sec"
    hrs = int(sec // 3600)
    return f"{hrs} hour" if hrs == 1 else f"{hrs} hours"


def _expand_placeholders(text: str, spell_data: dict, all_spells: dict,
                         durations: Optional[dict] = None) -> str:
    """Substitute $sN, $mN, $d (and $<spellID>...) placeholders in spell description."""
    if not text:
        return text
    durations = durations or {}
    base_points = spell_data.get('basePoints', [0, 0, 0])
    die_sides   = spell_data.get('dieSides', [0, 0, 0])

    # Idiom: "$s1 to $s2" with no effect 2 → range of effect 1
    if base_points[1] == 0 and die_sides[1] == 0:
        bp, ds = base_points[0], die_sides[0]
        if ds > 1:
            range_str = f"{bp + 1} to {bp + ds}"
            text = text.replace('$s1 to $s2', range_str)
            text = text.replace('$S1 to $S2', range_str)

    def replace_match(m):
        ref_id = m.group('ref')
        target = all_spells.get(ref_id) if ref_id else spell_data
        if not target:
            return m.group(0)

        if m.group('dur'):
            dur_ms = target.get('durationMs', 0)
            if not dur_ms:
                idx = target.get('durationIdx', 0)
                if idx:
                    dur_ms = durations.get(idx, 0)
            if dur_ms <= 0:
                return m.group(0)
            return _format_duration(dur_ms)

        ptype = m.group('type').lower()
        idx   = int(m.group('idx')) - 1
        target_bp = target.get('basePoints', [0, 0, 0])
        target_ds = target.get('dieSides', [0, 0, 0])
        if idx < 0 or idx >= len(target_bp):
            return m.group(0)
        bp = target_bp[idx]
        ds = target_ds[idx]
        if ptype == 'm':
            return str(abs(bp))
        val_min, val_max = bp + 1, bp + ds
        if ds > 1 and val_max != val_min:
            lo, hi = sorted((abs(val_min), abs(val_max)))
            return f"{lo} to {hi}"
        return str(abs(val_min))

    return _PLACEHOLDER_RE.sub(replace_match, text)


def build_effects(item: Dict[str, Any], spell_descriptions: Dict[str, Any],
                  durations: Optional[Dict[int, int]] = None) -> List[Dict[str, str]]:
    """Build [{trigger, text}] list from item_template.spellid_1..5 + spelltrigger_1..5."""
    if not spell_descriptions:
        return []
    effects = []
    for slot in range(1, 6):
        spell_id = item.get(f'spellid_{slot}', 0) or 0
        trigger  = item.get(f'spelltrigger_{slot}', 0) or 0
        if spell_id <= 0:
            continue
        trigger_label = SPELL_TRIGGER_LABELS.get(trigger, '')
        if not trigger_label:
            continue
        spell_data = spell_descriptions.get(str(spell_id))
        if not spell_data:
            continue
        raw_text = spell_data.get('description') or spell_data.get('auraDesc') or ''
        if not raw_text:
            continue
        text = _expand_placeholders(raw_text, spell_data, spell_descriptions, durations)
        effects.append({'trigger': trigger_label, 'text': text})
    return effects


# ---------------------------------------------------------------------------
# Config — all from env vars so credentials don't live in source
# ---------------------------------------------------------------------------

DB_CHARS = {
    'host':     os.environ.get('AC_DB_HOST', '127.0.0.1'),
    'port':     int(os.environ.get('AC_DB_PORT', '3306')),
    'user':     os.environ.get('AC_DB_USER', 'acore'),
    'password': os.environ['AC_DB_PASS'],
    'database': os.environ.get('AC_DB_CHARACTERS', 'acore_characters'),
}
DB_WORLD = dict(DB_CHARS, database=os.environ.get('AC_DB_WORLD', 'acore_world'))

API_KEY = os.environ.get('KCRAFT_API_KEY', '')
ACCOUNT_IDS = [int(x) for x in os.environ.get('KCRAFT_ACCOUNT_IDS', '').split(',') if x.strip()]
ALLOWED_ORIGIN = os.environ.get('KCRAFT_ORIGIN', '*')  # set to https://you.github.io in prod

if not API_KEY:
    raise SystemExit("KCRAFT_API_KEY env var is required")
if not ACCOUNT_IDS:
    raise SystemExit("KCRAFT_ACCOUNT_IDS env var is required (comma-separated integers)")


# ---------------------------------------------------------------------------
# Tooltip "effects" data — Equip:/Use:/Chance-on-hit text
#
# We need spell_descriptions.json (produced by convert_spells.py) plus the
# spellduration_dbc table (for $d placeholders). Loaded once at startup;
# silently degrades to empty if either is missing.
# ---------------------------------------------------------------------------

SPELL_DESCRIPTIONS_PATH = os.environ.get(
    'KCRAFT_SPELL_DESCRIPTIONS', 'spell_descriptions.json'
)
_SPELL_DESCRIPTIONS = load_spell_descriptions(SPELL_DESCRIPTIONS_PATH)
_DURATIONS: Dict[int, int] = {}

# itemsets.json (produced by convert_itemsets.py) — same data the dungeon
# pages and Find Loot use. Loaded once. Silently empty if file is missing,
# which just means set tooltips don't render in the armoury (everything
# else still works).
ITEMSETS_PATH = os.environ.get('KCRAFT_ITEMSETS', 'itemsets.json')
_ITEMSETS_RAW: Dict[str, Any] = {}
try:
    with open(ITEMSETS_PATH, 'r', encoding='utf-8') as _f:
        _ITEMSETS_RAW = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError):
    _ITEMSETS_RAW = {}

def _load_durations_once():
    """Pull spellduration_dbc once; cached for the life of the process."""
    global _DURATIONS
    if _DURATIONS:
        return _DURATIONS
    try:
        cnx = mysql.connector.connect(**DB_WORLD)
        try:
            _DURATIONS = fetch_durations(cnx) or {}
        finally:
            cnx.close()
    except mysql.connector.Error:
        _DURATIONS = {}
    return _DURATIONS


def _resolve_sets(cur, set_ids):
    """For a list of itemset IDs (from item_template.itemset), return a dict
    of {set_id: {name, items: [{id, name}], bonuses: [{pieces, text}]}} ready
    to attach to item payloads for the tooltip.

    Mirrors what build_dungeons.py's fetch_item_sets produces, so the
    armoury tooltip renders identically to dungeon/find-loot tooltips.
    Piece names are batch-fetched via `cur` in one query; bonus spell text
    is resolved via the existing _SPELL_DESCRIPTIONS pipeline.
    """
    if not set_ids or not _ITEMSETS_RAW:
        return {}

    requested = {sid: _ITEMSETS_RAW.get(str(sid))
                 for sid in set_ids if str(sid) in _ITEMSETS_RAW}
    requested = {k: v for k, v in requested.items() if v}
    if not requested:
        return {}

    # Batch lookup of all piece names across all needed sets in one query.
    needed_item_ids = set()
    for sd in requested.values():
        needed_item_ids.update(sd.get('items', []))
    item_names: Dict[int, str] = {}
    if needed_item_ids:
        ids_csv = ','.join(str(int(i)) for i in needed_item_ids)
        try:
            cur.execute(
                f"SELECT entry, name FROM {DB_WORLD['database']}.item_template "
                f"WHERE entry IN ({ids_csv})"
            )
            item_names = {r['entry']: r['name'] for r in cur.fetchall()}
        except mysql.connector.Error:
            pass

    out = {}
    durations = _load_durations_once()
    for sid, sd in requested.items():
        pieces = [{'id': iid, 'name': item_names.get(iid, f'Item {iid}')}
                  for iid in sd.get('items', [])]
        bonuses = []
        for b in sd.get('bonuses', []):
            spell_id = b['spellId']
            sp = _SPELL_DESCRIPTIONS.get(str(spell_id))
            if not sp:
                continue
            text = sp.get('description') or sp.get('auraDesc') or ''
            if not text:
                continue
            text = _expand_placeholders(text, sp, _SPELL_DESCRIPTIONS, durations)
            bonuses.append({'pieces': b['pieces'], 'text': text})
        bonuses.sort(key=lambda x: x['pieces'])
        out[sid] = {'name': sd['name'], 'items': pieces, 'bonuses': bonuses}
    return out


# ---------------------------------------------------------------------------
# WoW reference tables
# ---------------------------------------------------------------------------

CLASS_NAMES = {
    1: 'Warrior', 2: 'Paladin', 3: 'Hunter', 4: 'Rogue', 5: 'Priest',
    6: 'Death Knight', 7: 'Shaman', 8: 'Mage', 9: 'Warlock', 11: 'Druid',
}
RACE_NAMES = {
    1: 'Human', 2: 'Orc', 3: 'Dwarf', 4: 'Night Elf', 5: 'Undead',
    6: 'Tauren', 7: 'Gnome', 8: 'Troll', 10: 'Blood Elf', 11: 'Draenei',
}
GENDER_NAMES = {0: 'Male', 1: 'Female'}

# Character_inventory.bag is the GUID of the bag holding the item, OR 0 if
# the item is in the player's main grid (equipped + backpack + bank).
# In bag=0, the slot field tells us where:
#   slots 0-18    : equipped slots
#   slots 19-22   : bag slots (the bags themselves, not what's IN them)
#   slots 23-38   : backpack (16 slots)
#   slots 39-66   : bank (28 slots)
#   slots 67-73   : bank-bag slots (the bank bags themselves)
# Items inside a bag have bag=<bag_guid> and slot=0..N inside that bag.

EQUIPPED_SLOTS = {
    0: 'Head', 1: 'Neck', 2: 'Shoulder', 3: 'Shirt', 4: 'Chest',
    5: 'Waist', 6: 'Legs', 7: 'Feet', 8: 'Wrist', 9: 'Hands',
    10: 'Finger 1', 11: 'Finger 2', 12: 'Trinket 1', 13: 'Trinket 2',
    14: 'Back', 15: 'Main Hand', 16: 'Off Hand', 17: 'Ranged',
    18: 'Tabard',
}

QUALITY_NAMES = {0:'Poor', 1:'Common', 2:'Uncommon', 3:'Rare', 4:'Epic', 5:'Legendary'}
QUALITY_COLOR = {
    0: '#9d9d9d', 1: '#ffffff', 2: '#1eff00',
    3: '#0070dd', 4: '#a335ee', 5: '#ff8000',
}

# bonding column in item_template:
#   0 = no binding, 1 = BoP, 2 = BoE, 3 = BoU, 4 = Quest item, 5 = Account-bound
BONDING_NAMES = {
    0: '', 1: 'Soulbound', 2: 'Binds when equipped',
    3: 'Binds when used', 4: 'Quest Item', 5: 'Account Bound',
}

STAT_NAMES = {
    0: 'Mana', 1: 'Health', 3: 'Agility', 4: 'Strength', 5: 'Intellect',
    6: 'Spirit', 7: 'Stamina',
    12: 'Defense', 13: 'Dodge', 14: 'Parry', 15: 'Block',
    31: 'Hit', 32: 'Crit', 35: 'Resilience', 36: 'Haste', 37: 'Expertise',
    38: 'Attack Power', 43: 'MP5', 44: 'Armor Pen', 45: 'Spell Power', 49: 'MP5',
}

# Stat types shown as a bare "+N Stat" bonus line in tooltips.
# Everything else is a secondary/rating stat and renders as a green
# "Equip: ..." line, matching the in-game client's behavior.
PRIMARY_STAT_TYPES = {0, 1, 3, 4, 5, 6, 7}

# Format strings for rating/secondary stats. Used to build "Equip:" effect
# lines like "Equip: Improves hit rating by 2." Sprintf-style {v} = value.
STAT_RATING_TEXTS = {
    12: 'Increases defense rating by {v}',
    13: 'Increases your dodge rating by {v}',
    14: 'Increases your parry rating by {v}',
    15: 'Increases the block rating of your shield by {v}',
    16: 'Improves melee hit rating by {v}',
    17: 'Improves ranged hit rating by {v}',
    18: 'Improves spell hit rating by {v}',
    19: 'Improves melee critical strike rating by {v}',
    20: 'Improves ranged critical strike rating by {v}',
    21: 'Improves spell critical strike rating by {v}',
    28: 'Improves melee haste rating by {v}',
    29: 'Improves ranged haste rating by {v}',
    30: 'Improves spell haste rating by {v}',
    31: 'Improves hit rating by {v}',
    32: 'Improves critical strike rating by {v}',
    35: 'Increases your resilience rating by {v}',
    36: 'Improves haste rating by {v}',
    37: 'Increases your expertise rating by {v}',
    38: 'Increases attack power by {v}',
    39: 'Increases ranged attack power by {v}',
    43: 'Restores {v} mana per 5 sec',
    44: 'Increases your armor penetration rating by {v}',
    45: 'Increases spell power by {v}',
    46: 'Restores {v} health per 5 sec',
    47: 'Increases spell penetration by {v}',
    48: 'Increases the block value of your shield by {v}',
}

INVENTORY_TYPES = {
    1: 'Head', 2: 'Neck', 3: 'Shoulder', 4: 'Shirt', 5: 'Chest', 6: 'Waist',
    7: 'Legs', 8: 'Feet', 9: 'Wrist', 10: 'Hands', 11: 'Finger', 12: 'Trinket',
    13: 'One-Hand', 14: 'Off-Hand', 15: 'Ranged', 16: 'Back', 17: 'Two-Hand',
    18: 'Bag', 20: 'Robe', 21: 'Main Hand', 22: 'Off-Hand', 23: 'Held',
    25: 'Thrown', 26: 'Ranged', 28: 'Relic',
}

# Armor subclass (class=4 in item_template). Used to display "Cloth"/"Leather" etc.
# in the right column of the in-game style tooltip.
ARMOR_SUBCLASS = {
    0: 'Misc', 1: 'Cloth', 2: 'Leather', 3: 'Mail', 4: 'Plate',
    6: 'Shield', 7: 'Libram', 8: 'Idol', 9: 'Totem', 10: 'Sigil',
}
# Weapon subclass (class=2). Less commonly shown but useful for completeness.
WEAPON_SUBCLASS = {
    0: 'Axe', 1: 'Axe', 2: 'Bow', 3: 'Gun', 4: 'Mace', 5: 'Mace',
    6: 'Polearm', 7: 'Sword', 8: 'Sword', 10: 'Staff', 13: 'Fist',
    15: 'Dagger', 16: 'Thrown', 18: 'Crossbow', 19: 'Wand', 20: 'Fishing Pole',
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(db_config):
    return mysql.connector.connect(**db_config, connection_timeout=5)


def _stat_summary(item: Dict[str, Any]) -> List[str]:
    """Build ['+8 Strength', '+5 Stamina', '+12 Armor'] list of PRIMARY stats only.

    Secondary/rating stats (Hit, Crit, Defense, Attack Power, etc.) are NOT
    included here — they render as green "Equip: ..." effect lines instead,
    matching the in-game client. Weapon damage is also omitted; it has its
    own `damage` field.
    """
    parts = []
    armor = item.get('armor') or 0
    if armor:
        parts.append(f'+{armor} Armor')
    for i in range(1, 11):
        s = item.get(f'stat_type{i}', -1)
        v = item.get(f'stat_value{i}', 0)
        if s is None or v is None or s < 0 or v == 0:
            continue
        if s not in PRIMARY_STAT_TYPES:
            continue
        sign = '+' if v > 0 else ''
        parts.append(f'{sign}{v} {STAT_NAMES.get(s, f"Stat{s}")}')
    return parts


def _stat_effects(item: Dict[str, Any]) -> List[Dict[str, str]]:
    """Convert SECONDARY stat slots into [{trigger:'Equip', text:'Improves ... by N'}].

    These render alongside spell-based effects in the tooltip's green Equip
    section, just like the in-game client renders them.
    """
    out = []
    for i in range(1, 11):
        s = item.get(f'stat_type{i}', -1)
        v = item.get(f'stat_value{i}', 0)
        if s is None or v is None or s < 0 or v == 0:
            continue
        if s in PRIMARY_STAT_TYPES:
            continue
        fmt = STAT_RATING_TEXTS.get(s)
        if fmt:
            text = fmt.format(v=v)
        else:
            # Generic fallback for unmapped rating types
            text = f'Increases {STAT_NAMES.get(s, f"stat {s}").lower()} by {v}'
        # Trailing period to match in-game tooltip phrasing
        if not text.endswith('.'):
            text += '.'
        out.append({'trigger': 'Equip', 'text': text})
    return out


def _format_damage(item: Dict[str, Any]) -> str:
    """Return '12-23 Damage' for weapons, '' for non-weapons."""
    if (item.get('item_class') or 0) != 2:
        return ''
    dmg_min = item.get('dmg_min1') or 0
    dmg_max = item.get('dmg_max1') or 0
    if not (dmg_min and dmg_max):
        return ''
    return f'{int(dmg_min)}\u2013{int(dmg_max)} Damage'


def _weapon_speed_dps(item: Dict[str, Any]):
    """Return (speed, dps) tuple for weapons; (None, None) for everything else.
    Speed is a float in seconds (e.g. 1.90), DPS is float damage per second."""
    if (item.get('item_class') or 0) != 2:
        return None, None
    delay_ms = item.get('delay') or 0
    dmg_min = item.get('dmg_min1') or 0
    dmg_max = item.get('dmg_max1') or 0
    if not (delay_ms and dmg_min and dmg_max):
        return None, None
    speed = delay_ms / 1000.0
    dps = (dmg_min + dmg_max) / 2.0 / speed
    return round(speed, 2), round(dps, 1)


def _item_payload(row: Dict[str, Any], resolved_sets: Optional[Dict[int, Any]] = None) -> Dict[str, Any]:
    """Convert a joined character_inventory + item_template row to JSON-ready dict.

    `resolved_sets` is an optional {set_id: {name, items, bonuses}} dict; when
    the item belongs to a known set, that block is attached to the payload
    so the tooltip renders the same set info shown on dungeon pages."""
    quality = row.get('Quality', 1)
    dur_cur = row.get('durability') or 0
    dur_max = row.get('MaxDurability') or 0
    sell = row.get('SellPrice') or 0
    bonding = row.get('bonding') or 0
    item_class = row.get('item_class', 0)
    subclass = row.get('subclass', 0)
    # Surface armor type for the in-game tooltip (Cloth/Leather/Mail/Plate/Shield).
    # Only applies to armor items (class=4); weapons get the weapon subclass instead.
    if item_class == 4:
        armor_type = ARMOR_SUBCLASS.get(subclass, '')
    elif item_class == 2:
        armor_type = WEAPON_SUBCLASS.get(subclass, '')
    else:
        armor_type = ''
    speed, dps = _weapon_speed_dps(row)

    payload = {
        'id':       row.get('item_template'),
        'name':     row.get('iname', ''),
        'quality':  quality,
        'color':    QUALITY_COLOR.get(quality, '#fff'),
        'qualityName': QUALITY_NAMES.get(quality, 'Common'),
        'ilvl':     row.get('ItemLevel', 0),
        'reqLevel': row.get('RequiredLevel', 0),
        'invType':  INVENTORY_TYPES.get(row.get('InventoryType', 0), ''),
        'armorType': armor_type,
        'damage':   _format_damage(row),
        'speed':    speed,
        'dps':      dps,
        'stats':    _stat_summary(row),
        # Spell-based effects (Equip:/Use:/Chance-on-hit:) combined with
        # stat-based "Equip: Improves X by N" lines from rating stats.
        'effects':  build_effects(row, _SPELL_DESCRIPTIONS, _load_durations_once())
                    + _stat_effects(row),
        'count':    row.get('count', 1),
        'durability':    dur_cur,
        'maxDurability': dur_max,
        'sellPrice': sell,
        'sellGold': sell // 10000,
        'sellSilver': (sell % 10000) // 100,
        'sellCopper': sell % 100,
        'bonding':   bonding,
        'bondingName': BONDING_NAMES.get(bonding, ''),
    }

    # Attach set info if the item belongs to a known set. The tooltip
    # renders the yellow set heading + green bonus lines from this block,
    # matching what dungeon pages and Find Loot show.
    set_id = row.get('itemset') or 0
    if set_id and resolved_sets and set_id in resolved_sets:
        payload['set'] = resolved_sets[set_id]
    return payload


# ---------------------------------------------------------------------------
# Core queries
# ---------------------------------------------------------------------------

def _list_characters() -> List[Dict[str, Any]]:
    """Return a brief list of all characters owned by whitelisted accounts."""
    placeholders = ','.join(['%s'] * len(ACCOUNT_IDS))
    # Cross-DB join: characters live in acore_characters, account names in acore_auth.
    sql = f"""
        SELECT c.guid, c.name, c.race, c.class, c.gender, c.level, c.online,
               c.account AS account_id,
               a.username AS account_name
        FROM characters c
        LEFT JOIN acore_auth.account a ON a.id = c.account
        WHERE c.account IN ({placeholders})
        ORDER BY c.account, c.level DESC, c.name
    """
    conn = _connect(DB_CHARS)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, ACCOUNT_IDS)
        rows = cur.fetchall()
    finally:
        conn.close()

    return [{
        'name': r['name'],
        'level': r['level'],
        'class': CLASS_NAMES.get(r['class'], f'Class{r["class"]}'),
        'classId': r['class'],
        'race': RACE_NAMES.get(r['race'], f'Race{r["race"]}'),
        'gender': GENDER_NAMES.get(r['gender'], 'Unknown'),
        'online': bool(r['online']),
        'accountId': r['account_id'],
        'accountName': (r['account_name'] or 'Unknown').title(),
    } for r in rows]


def _get_character(name: str) -> Optional[Dict[str, Any]]:
    """Return full character payload or None if not found / not whitelisted."""
    conn = _connect(DB_CHARS)
    try:
        cur = conn.cursor(dictionary=True)

        # 1. Find the character. Must belong to a whitelisted account.
        placeholders = ','.join(['%s'] * len(ACCOUNT_IDS))
        cur.execute(f"""
            SELECT guid, name, race, class, gender, level, money,
                   totaltime, leveltime, online, totalKills
            FROM characters
            WHERE name = %s AND account IN ({placeholders})
        """, (name, *ACCOUNT_IDS))
        char = cur.fetchone()
        if not char:
            return None

        # 2. Pull every inventory row joined with item_template.
        # Note: item_template is in acore_world, characters_inventory in acore_characters.
        # We use a fully-qualified name for the join.
        cur.execute(f"""
            SELECT ci.bag, ci.slot,
                   ii.itemEntry AS item_template,
                   ii.count,
                   ii.durability,
                   it.name AS iname, it.Quality, it.ItemLevel,
                   it.RequiredLevel, it.InventoryType,
                   it.class AS item_class, it.subclass,
                   it.dmg_min1, it.dmg_max1,
                   it.dmg_min2, it.dmg_max2,
                   it.delay,
                   it.armor,
                   it.MaxDurability,
                   it.SellPrice, it.bonding,
                   it.stat_type1,  it.stat_value1,
                   it.stat_type2,  it.stat_value2,
                   it.stat_type3,  it.stat_value3,
                   it.stat_type4,  it.stat_value4,
                   it.stat_type5,  it.stat_value5,
                   it.stat_type6,  it.stat_value6,
                   it.stat_type7,  it.stat_value7,
                   it.stat_type8,  it.stat_value8,
                   it.stat_type9,  it.stat_value9,
                   it.stat_type10, it.stat_value10,
                   it.spellid_1, it.spelltrigger_1,
                   it.spellid_2, it.spelltrigger_2,
                   it.spellid_3, it.spelltrigger_3,
                   it.spellid_4, it.spelltrigger_4,
                   it.spellid_5, it.spelltrigger_5,
                   it.itemset
            FROM character_inventory ci
            JOIN item_instance ii ON ii.guid = ci.item
            LEFT JOIN {DB_WORLD['database']}.item_template it
                ON ii.itemEntry = it.entry
            WHERE ci.guid = %s
            ORDER BY ci.bag, ci.slot
        """, (char['guid'],))
        inventory_rows = cur.fetchall()

        # Pre-resolve item-set definitions for any items in this character's
        # inventory that belong to a set. Done while the cursor is still
        # open so we can issue the batched piece-name lookup without
        # opening a second connection.
        set_ids = {r.get('itemset') for r in inventory_rows if r.get('itemset')}
        resolved_sets = _resolve_sets(cur, set_ids)
    finally:
        conn.close()

    # 3. Bucket items.
    equipped: Dict[int, Dict[str, Any]] = {}  # slot 0-18
    backpack: List[Optional[Dict[str, Any]]] = [None] * 16  # slots 23-38
    bank: List[Optional[Dict[str, Any]]] = [None] * 28      # slots 39-66
    bag_items: Dict[int, List[Dict[str, Any]]] = {}         # bag_guid -> items
    bag_meta: Dict[int, Dict[str, Any]] = {}                # bag_guid -> bag info

    for r in inventory_rows:
        bag = r['bag']
        slot = r['slot']
        payload = _item_payload(r, resolved_sets)

        if bag == 0:
            # Items in main grid (equipped/backpack/bank/bagslots)
            if 0 <= slot <= 18:
                payload['slotName'] = EQUIPPED_SLOTS.get(slot, f'Slot{slot}')
                equipped[slot] = payload
            elif 19 <= slot <= 22:
                # These are backpack-bag slots (the bags themselves)
                bag_meta[r['item_template']] = {**payload, 'bagSlot': slot - 19}
            elif 23 <= slot <= 38:
                backpack[slot - 23] = payload
            elif 39 <= slot <= 66:
                bank[slot - 39] = payload
            elif 67 <= slot <= 73:
                # Bank-bag slots
                bag_meta[r['item_template']] = {**payload, 'bankBagSlot': slot - 67}
        else:
            # Item is inside a bag (bag = bag's guid)
            bag_items.setdefault(bag, []).append({**payload, 'bagSlot': slot})

    return {
        'name': char['name'],
        'level': char['level'],
        'race': RACE_NAMES.get(char['race'], 'Unknown'),
        'class': CLASS_NAMES.get(char['class'], 'Unknown'),
        'classId': char['class'],
        'gender': GENDER_NAMES.get(char['gender'], 'Unknown'),
        'gold': (char['money'] or 0) // 10000,
        'silver': ((char['money'] or 0) % 10000) // 100,
        'copper': (char['money'] or 0) % 100,
        'totalPlayedHours': round((char['totaltime'] or 0) / 3600, 1),
        'levelPlayedHours': round((char['leveltime'] or 0) / 3600, 1),
        'online': bool(char['online']),
        'kills': char['totalKills'] or 0,
        'equipped': equipped,
        'backpack': backpack,
        'bank': bank,
        'bagItems': bag_items,
        'bagMeta': list(bag_meta.values()),
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="KCraft Armoury", version="1.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != '*' else ['*'],
    allow_methods=['GET'],
    allow_headers=['X-API-Key', 'Content-Type'],
)


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Bad or missing X-API-Key header")


@app.get("/healthz")
def healthz():
    """No auth — just confirms the service is running."""
    return {"ok": True}


@app.get("/armoury", dependencies=[Depends(verify_key)])
def list_characters():
    try:
        return {"characters": _list_characters()}
    except mysql.connector.Error as e:
        raise HTTPException(503, f"Database error {e.errno}: {e.msg}")


@app.get("/armoury/{name}", dependencies=[Depends(verify_key)])
def get_character(name: str):
    if not name or len(name) > 12 or not name.isalpha():
        raise HTTPException(400, "Invalid character name")
    try:
        data = _get_character(name)
    except mysql.connector.Error as e:
        raise HTTPException(503, f"Database error {e.errno}: {e.msg}")
    if not data:
        raise HTTPException(404, f"Character '{name}' not found or not in whitelist")
    return data
