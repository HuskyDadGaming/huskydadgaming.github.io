"""
KCraft dungeon builder
======================

Reads build_config.yaml + queries the AzerothCore database to produce
loot-data.json that matches the format of index.html's <script id="loot-data">.

Usage:
    # All dungeons in config
    python build_dungeons.py

    # Just one dungeon (for iteration)
    python build_dungeons.py --dungeon shadowfang-keep

    # Dry-run: print summary without writing files
    python build_dungeons.py --dry-run

Environment variables (same as armoury_api.py):
    AC_DB_HOST     default 127.0.0.1
    AC_DB_PORT     default 3306
    AC_DB_USER     default acore
    AC_DB_PASS     default acore
    AC_DB_WORLD    default acore_world

Output:
    loot-data.json  -- the full data blob, ready to drop into index.html
                       between <script id="loot-data" ...> and </script>
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import mysql.connector
import yaml


# ============================================================================
# Configuration & lookup tables
# ============================================================================

DB_CONFIG = {
    'host':     os.environ.get('AC_DB_HOST', '127.0.0.1'),
    'port':     int(os.environ.get('AC_DB_PORT', '3306')),
    'user':     os.environ.get('AC_DB_USER', 'acore'),
    'password': os.environ['AC_DB_PASS'],
    'database': os.environ.get('AC_DB_WORLD', 'acore_world'),
}

# Quality color codes (matches WoW client)
QUALITY_COLORS = {
    0: '#9d9d9d',  # Gray (Poor)
    1: '#ffffff',  # White (Common)
    2: '#1eff00',  # Green (Uncommon)
    3: '#0070dd',  # Blue (Rare)
    4: '#a335ee',  # Purple (Epic)
    5: '#ff8000',  # Orange (Legendary)
    6: '#e6cc80',  # Heirloom
    7: '#00ccff',  # Artifact
}

# Quality names (matches armoury_api.py for tooltip parity)
QUALITY_NAMES = {
    0: 'Poor', 1: 'Common', 2: 'Uncommon', 3: 'Rare',
    4: 'Epic', 5: 'Legendary', 6: 'Heirloom', 7: 'Artifact',
}

# Bonding names (matches armoury_api.py)
# bonding column: 0=none 1=BoP 2=BoE 3=BoU 4=Quest 5=Account-bound
BONDING_NAMES = {
    0: '', 1: 'Soulbound', 2: 'Binds when equipped',
    3: 'Binds when used', 4: 'Quest Item', 5: 'Account Bound',
}

# Item spell trigger types (item_template.spelltrigger_N column).
# Empty string = trigger we don't surface in tooltips (soulstone, learning).
SPELL_TRIGGER_LABELS = {
    0: 'Use',           # ON_USE: triggers when player right-clicks item
    1: 'Equip',         # ON_EQUIP: passive aura while equipped
    2: 'Chance on hit', # CHANCE_ON_HIT: random proc on melee/ranged attack
    3: '',              # SOULSTONE: warlock soulstone resurrect (skip)
    4: 'Use',           # ON_NO_DELAY_USE: like Use but no GCD
    5: '',              # LEARN_SPELL_ID: tradeskill recipes (skip)
    6: '',              # LEARN_SPELL_ID alt (skip)
}

# InventoryType -> human-readable slot
# This is the "slotFilter" field — the broad slot type
SLOT_NAMES = {
    1:  'Head',
    2:  'Neck',
    3:  'Shoulder',
    4:  'Shirt',
    5:  'Chest',
    6:  'Waist',
    7:  'Legs',
    8:  'Feet',
    9:  'Wrist',
    10: 'Hands',
    11: 'Finger',
    12: 'Trinket',
    13: 'One-Hand',
    14: 'Off-Hand',     # shields
    15: 'Ranged',       # bows
    16: 'Back',
    17: 'Two-Hand',
    18: 'Bag',
    19: 'Tabard',
    20: 'Chest',        # Robe (alt chest)
    21: 'Main Hand',
    22: 'Off-Hand',     # off-hand weapon
    23: 'Held',         # held in off-hand (non-weapon)
    24: 'Ammo',
    25: 'Thrown',
    26: 'Ranged',       # wand/gun/crossbow
    27: 'Quiver',
    28: 'Relic',
}

# Item class for armor (item_template.class)
ITEM_CLASS_ARMOR = 4
ITEM_CLASS_WEAPON = 2

# Armor subclass -> name (for armor items)
ARMOR_SUBCLASS_NAMES = {
    1: 'Cloth',
    2: 'Leather',
    3: 'Mail',
    4: 'Plate',
    6: 'Shield',
    7: 'Libram',
    8: 'Idol',
    9: 'Totem',
    10: 'Sigil',
}

# Weapon subclass -> display name (for armoury-style tooltip armorType field)
WEAPON_SUBCLASS_NAMES = {
    0: 'Axe', 1: 'Axe', 2: 'Bow', 3: 'Gun', 4: 'Mace', 5: 'Mace',
    6: 'Polearm', 7: 'Sword', 8: 'Sword', 10: 'Staff', 13: 'Fist',
    15: 'Dagger', 16: 'Thrown', 18: 'Crossbow', 19: 'Wand',
}

# Stat ID -> short name (matches existing JSON formatting)
STAT_NAMES = {
    0:  'Mana',
    1:  'Health',
    3:  'Agility',
    4:  'Strength',
    5:  'Intellect',
    6:  'Spirit',
    7:  'Stamina',
    12: 'Defense',       # Defense Skill Rating
    13: 'Dodge',         # Dodge Rating
    14: 'Parry',         # Parry Rating
    15: 'Block',         # Block Rating
    16: 'Hit',           # Hit Rating (Melee)
    17: 'Hit',           # Hit Rating (Ranged)
    18: 'Hit',           # Hit Rating (Spell)
    19: 'Crit',          # Crit Rating (Melee)
    20: 'Crit',          # Crit Rating (Ranged)
    21: 'Crit',          # Crit Rating (Spell)
    28: 'Avoid Hit',     # Hit Taken Melee
    29: 'Avoid Hit',     # Hit Taken Ranged
    30: 'Avoid Hit',     # Hit Taken Spell
    31: 'Hit',           # Hit Rating (general)
    32: 'Crit',          # Crit Rating (general)
    35: 'Resilience',    # Resilience Rating
    36: 'Haste',         # Haste Rating
    37: 'Expertise',     # Expertise Rating
    38: 'Attack Power',
    43: 'Mana Regen',
    44: 'MP5',           # Mana Per 5 sec
    45: 'Spell Power',
    47: 'Spell Pen',     # Spell Penetration
    48: 'Block Value',
    50: 'Armor Pen',     # Armor Penetration Rating
    51: 'Armor Pen',     # Armor Penetration Rating (alt)
}

# Stat types shown as a bare "+N Stat" bonus line in tooltips.
# Everything else is a secondary/rating stat and renders as a green
# "Equip: ..." line, matching the in-game client's behavior.
PRIMARY_STAT_TYPES = {0, 1, 3, 4, 5, 6, 7}

# Format strings for rating/secondary stats. Used to build "Equip:" effect
# lines like "Equip: Improves hit rating by 2." {v} = the stat value.
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
    50: 'Increases your armor penetration rating by {v}',
    51: 'Increases your armor penetration rating by {v}',
}

# Class ID -> slug (matches smart_filter_block.js)
CLASS_SLUGS = {
    1:  'warrior',
    2:  'paladin',
    3:  'hunter',
    4:  'rogue',
    5:  'priest',
    6:  'dk',
    7:  'shaman',
    8:  'mage',
    9:  'warlock',
    11: 'druid',
}

# All classes in canonical order (matches smart_filter_block.js ROLE_CLASSES[''])
ALL_CLASSES = ['warrior', 'paladin', 'hunter', 'rogue', 'priest', 'dk',
               'shaman', 'mage', 'warlock', 'druid']

# Class bitmask in item_template.AllowableClass (1<<0 = warrior, etc.)
# Note: WoW uses 1-indexed class IDs, so warrior is bit (1-1)=0 -> mask=1
CLASS_BITMASKS = {
    1:  1 << 0,   # warrior
    2:  1 << 1,   # paladin
    3:  1 << 2,   # hunter
    4:  1 << 3,   # rogue
    5:  1 << 4,   # priest
    6:  1 << 5,   # dk
    7:  1 << 6,   # shaman
    8:  1 << 7,   # mage
    9:  1 << 8,   # warlock
    11: 1 << 10,  # druid
}

# Mirror smart_filter_block.js ROLE_CLASSES
ROLE_CLASSES = {
    '':       ALL_CLASSES,
    'tank':   ['warrior', 'paladin', 'dk', 'druid'],
    'heal':   ['priest', 'paladin', 'druid', 'shaman'],
    'melee':  ['warrior', 'paladin', 'dk', 'rogue', 'druid', 'shaman'],
    'ranged': ['hunter', 'mage', 'warlock', 'priest', 'druid', 'shaman', 'paladin'],
}

# Mirror smart_filter_block.js CLASS_ARMOR_FLOOR
CLASS_ARMOR_FLOOR = {
    'warrior': ['Plate', 'Mail'],
    'paladin': ['Plate', 'Mail'],
    'dk':      ['Plate'],
    'hunter':  ['Mail', 'Leather'],
    'shaman':  ['Mail', 'Leather'],
    'rogue':   ['Leather'],
    'druid':   ['Leather'],
    'priest':  ['Cloth'],
    'mage':    ['Cloth'],
    'warlock': ['Cloth'],
}

ARMOR_SLOTS = {'Head', 'Shoulder', 'Chest', 'Wrist', 'Hands', 'Waist', 'Legs', 'Feet'}
WEAPON_SLOTS = {'One-Hand', 'Two-Hand', 'Main Hand', 'Off-Hand', 'Ranged', 'Held', 'Thrown'}

# Weapon proficiency by item_template.subclass (when item.class = 2 = Weapon).
# AzerothCore 3.3.5a / WotLK proficiencies. AllowableClass alone isn't enough
# because WoW restricts most weapons via skill (not the item's bitmask), so we
# encode the rules ourselves.
WEAPON_PROFICIENCY = {
    0:  {'warrior', 'paladin', 'hunter', 'rogue', 'dk', 'shaman'},                    # 1H Axe
    1:  {'warrior', 'paladin', 'hunter', 'dk', 'shaman'},                              # 2H Axe
    2:  {'warrior', 'hunter', 'rogue'},                                                # Bow
    3:  {'warrior', 'hunter', 'rogue'},                                                # Gun
    4:  {'warrior', 'paladin', 'rogue', 'priest', 'dk', 'shaman', 'druid'},           # 1H Mace
    5:  {'warrior', 'paladin', 'dk', 'shaman', 'druid'},                              # 2H Mace
    6:  {'warrior', 'paladin', 'hunter', 'dk', 'druid'},                              # Polearm
    7:  {'warrior', 'paladin', 'hunter', 'rogue', 'dk', 'mage', 'warlock'},           # 1H Sword
    8:  {'warrior', 'paladin', 'hunter', 'dk'},                                        # 2H Sword
    10: {'warrior', 'hunter', 'priest', 'shaman', 'mage', 'warlock', 'druid'},        # Staff
    13: {'warrior', 'hunter', 'rogue', 'shaman', 'druid'},                            # Fist
    15: {'warrior', 'hunter', 'rogue', 'priest', 'shaman', 'mage', 'warlock', 'druid'}, # Dagger
    16: {'warrior', 'rogue'},                                                          # Thrown
    18: {'warrior', 'hunter', 'rogue'},                                                # Crossbow
    19: {'priest', 'mage', 'warlock'},                                                 # Wand
}

# Class restrictions for armor items by subclass (when item.class = 4 = Armor).
# Cloth/Leather/Mail/Plate are handled by CLASS_ARMOR_FLOOR. These are the
# special off-hand armor types: shields and class-specific relics.
ARMOR_CLASS_RESTRICTIONS = {
    6:  {'warrior', 'paladin', 'shaman'},  # Shield
    7:  {'paladin'},                        # Libram (paladin relic)
    8:  {'druid'},                          # Idol (druid relic)
    9:  {'shaman'},                         # Totem (shaman relic)
    10: {'dk'},                             # Sigil (death knight relic)
}


# ============================================================================
# Item processing
# ============================================================================

def format_slot(item):
    """
    Build the 'slot' field — the slot label, with armor type appended for armor.
    Mirrors what the existing JSON does: "Chest (Plate)", "Two-Hand", "Neck".
    """
    slot_name = SLOT_NAMES.get(item['InventoryType'], f"Slot{item['InventoryType']}")
    if item['class'] == ITEM_CLASS_ARMOR and slot_name in ARMOR_SLOTS:
        armor_type = ARMOR_SUBCLASS_NAMES.get(item['subclass'])
        if armor_type:
            return f"{slot_name} ({armor_type})"
    elif item['class'] == ITEM_CLASS_ARMOR and slot_name == 'Off-Hand' and item['subclass'] == 6:
        return "Off-Hand (Shield)"
    return slot_name


def slot_filter(item):
    """The clean slot type without armor suffix. Used for filter logic."""
    return SLOT_NAMES.get(item['InventoryType'], f"Slot{item['InventoryType']}")


def parse_stats(item):
    """
    Extract PRIMARY stat strings from item_template, plus armor.

    Returns a list like ["+15 Stamina", "+10 Strength", "+471 Armor"].
    Secondary/rating stats (Hit, Crit, Defense, Attack Power, etc.) are
    NOT included here — they render as green "Equip: ..." effect lines via
    parse_stat_effects(), matching the in-game client's behavior.

    Note: weapon damage ranges are not included here either — they're surfaced
    separately in the tooltip data (damage field on the item record).
    """
    stats = []

    # 10 stat slots in WotLK
    for i in range(1, 11):
        stype = item.get(f'stat_type{i}')
        sval = item.get(f'stat_value{i}')
        if stype is None or sval is None or sval == 0:
            continue
        if stype not in PRIMARY_STAT_TYPES:
            continue
        name = STAT_NAMES.get(stype, f'Stat{stype}')
        sign = '+' if sval > 0 else ''
        stats.append(f"{sign}{sval} {name}")

    # Armor (separate column from stat slots)
    armor = item.get('armor', 0) or 0
    if armor > 0:
        stats.append(f"+{armor} Armor")

    return stats


def parse_stat_effects(item):
    """Convert SECONDARY stat slots into [{trigger:'Equip', text:'Improves ... by N'}].

    These are appended to the spell-based effects list so the tooltip renders
    them in the green Equip section, matching how the in-game client displays
    rating-based stats.
    """
    out = []
    for i in range(1, 11):
        stype = item.get(f'stat_type{i}')
        sval = item.get(f'stat_value{i}')
        if stype is None or sval is None or sval == 0:
            continue
        if stype in PRIMARY_STAT_TYPES:
            continue
        fmt = STAT_RATING_TEXTS.get(stype)
        if fmt:
            text = fmt.format(v=sval)
        else:
            # Generic fallback for unmapped rating types
            generic = STAT_NAMES.get(stype, f"stat {stype}").lower()
            text = f"Increases {generic} by {sval}"
        if not text.endswith('.'):
            text += '.'
        out.append({'trigger': 'Equip', 'text': text})
    return out


def weapon_speed_dps(item):
    """Return (speed, dps) tuple for weapons; (None, None) for non-weapons.
    Speed is float seconds (e.g. 1.90), DPS is float damage per second.
    """
    if item.get('class') != ITEM_CLASS_WEAPON:
        return None, None
    delay_ms = item.get('delay') or 0
    dmin = item.get('dmg_min1') or 0
    dmax = item.get('dmg_max1') or 0
    if not (delay_ms and dmin and dmax):
        return None, None
    speed = delay_ms / 1000.0
    dps = (dmin + dmax) / 2.0 / speed
    return round(speed, 2), round(dps, 1)


def passes_class_armor(item, cls, role):
    """Mirror smart_filter_block.js passesClassArmor."""
    allowed = CLASS_ARMOR_FLOOR.get(cls)
    if not allowed:
        return True

    slot = item['slot']  # e.g. "Chest (Plate)"
    sf = item['slotFilter']

    # Parse out armor type from slot string
    m = re.search(r'\((Cloth|Leather|Mail|Plate)\)', slot)
    if not m:
        return True  # not an armor-tier item (cloak, jewelry, weapon, shield)
    if sf not in ARMOR_SLOTS:
        return True  # back/neck/finger/trinket pass through
    return m.group(1) in allowed


def class_fills_role(item, cls, role):
    """Mirror smart_filter_block.js classFillsRole."""
    if not passes_class_armor(item, cls, role):
        return False

    slot = item['slotFilter']
    ic = item['slot']  # contains "(Plate)" etc.
    stats_text = ' '.join(item.get('stats', []))
    has_stat = lambda n: n in stats_text

    is_shield = slot == 'Off-Hand' and 'Shield' in ic
    is_plate = '(Plate)' in ic
    is_mail = '(Mail)' in ic
    is_leather = '(Leather)' in ic
    is_cloth = '(Cloth)' in ic
    is_weapon = slot in WEAPON_SLOTS
    # Detect wand by subclass directly (subclass 19 in item.class=2). Stat-less
    # wands fail the Intellect/Spell Power checks but should still be ranged for
    # caster classes — match by item type, not stat-name string parsing.
    is_wand = item.get('class') == ITEM_CLASS_WEAPON and item.get('subclass') == 19

    # Class proficiency. The WEAPON_PROFICIENCY (item.class=2) and
    # ARMOR_CLASS_RESTRICTIONS (item.class=4) tables encode which classes
    # can physically equip an item, regardless of its stats. A "Strength
    # bow" is still not paladin loot; an "Intellect 2H sword" is still
    # not warlock loot (1H swords are warlock-OK, 2H aren't); a "Stamina
    # shield" is still not mage loot. These restrictions cannot be
    # overridden by stat-based role logic.
    sub = item.get('subclass')
    icat = item.get('class')
    if icat == ITEM_CLASS_WEAPON and sub in WEAPON_PROFICIENCY:
        if cls not in WEAPON_PROFICIENCY[sub]:
            return False
    elif icat == ITEM_CLASS_ARMOR and sub in ARMOR_CLASS_RESTRICTIONS:
        if cls not in ARMOR_CLASS_RESTRICTIONS[sub]:
            return False

    if role == 'tank':
        if cls not in ('warrior', 'paladin', 'dk', 'druid'):
            return False
        if (has_stat('Defense') or has_stat('Dodge') or has_stat('Parry') or
                has_stat('Block') or has_stat('Resilience')):
            return True
        has_caster_stat = (has_stat('Spirit') or has_stat('Spell Power') or
                          has_stat('MP5') or has_stat('Intellect'))
        if cls in ('warrior', 'paladin', 'dk'):
            if is_shield:
                return True
            if is_plate and not has_caster_stat:
                return True
            if not is_weapon and has_stat('Stamina') and not has_caster_stat:
                return True
            if slot == 'One-Hand' and has_stat('Stamina') and not has_caster_stat:
                return True
            if slot == 'Two-Hand' and has_stat('Stamina') and not has_caster_stat:
                return True
            return False
        if cls == 'druid':
            if is_leather and has_stat('Stamina') and not has_caster_stat:
                return True
            return False
        return False

    if role == 'heal':
        if cls not in ('priest', 'paladin', 'druid', 'shaman'):
            return False
        if has_stat('Spirit') or has_stat('MP5') or has_stat('Spell Power'):
            return True
        if has_stat('Intellect') and (is_cloth or is_leather or is_mail):
            return True
        return False

    if role == 'melee':
        if cls not in ('warrior', 'paladin', 'dk', 'rogue', 'hunter', 'druid', 'shaman'):
            return False
        if cls == 'hunter':
            return False
        if is_weapon and (has_stat('Spirit') or has_stat('Spell Power') or has_stat('MP5')):
            return False
        if is_weapon and has_stat('Intellect') and not (
                has_stat('Strength') or has_stat('Agility') or has_stat('Attack Power')):
            return False
        if cls in ('rogue', 'druid'):
            if has_stat('Agility') or has_stat('Attack Power') or has_stat('Armor Pen'):
                return True
            if slot in ('One-Hand', 'Two-Hand', 'Main Hand') and not has_stat('Strength'):
                return True
            return False
        if has_stat('Strength') or has_stat('Attack Power') or has_stat('Armor Pen'):
            return True
        if has_stat('Agility') and cls == 'shaman':
            return True
        if slot in ('One-Hand', 'Two-Hand', 'Main Hand'):
            return True
        return False

    if role == 'ranged':
        if cls == 'hunter':
            if has_stat('Agility') or has_stat('Attack Power'):
                return True
            if slot == 'Ranged':
                return True
            return False
        if cls in ('mage', 'warlock', 'priest'):
            if has_stat('Spell Power'):
                return True
            if is_wand:
                return True
            if has_stat('Intellect'):
                return True
            return False
        if cls in ('shaman', 'druid'):
            # Druids blocked from shields at top via ARMOR_CLASS_RESTRICTIONS.
            # Shamans pass through here — a Spell Power or Int shield IS valid
            # Elemental shaman ranged gear (1H + shield caster setup), so we
            # let it tag as both Heal AND Ranged when stats fit.
            if has_stat('Spell Power'):
                return True
            if has_stat('Intellect') and not has_stat('Spirit'):
                return True
            return False
        return False

    return False


def infer_roles(item):
    """For each role, check if any class can fill it with this item."""
    roles = []
    for role in ('tank', 'heal', 'melee', 'ranged'):
        for cls in ROLE_CLASSES.get(role, []):
            if class_fills_role(item, cls, role):
                roles.append(role)
                break
    return roles


def infer_classes(item):
    """
    Find which classes can MEANINGFULLY use this item — that is, classes that
    can fill at least one role (tank/heal/melee/ranged) with it.

    Stat-aware via class_fills_role, which already encodes:
      - "Cloth/Leather/Mail/Plate" armor floor per class
      - Caster vs melee stat distinctions (Spirit/Intellect/Spell Power vs
        Strength/Agility/Attack Power/Armor Pen)
      - Tank stat requirements (Defense/Dodge/Parry/Block/Resilience or
        Stamina without caster stats)
      - Healer stat requirements (Spirit/MP5/Spell Power)
      - Weapon role appropriateness (e.g. melee weapons can't have Spirit)

    A class drops out when none of the four roles are viable. So a Warrior
    won't appear on an Intellect-only staff (no role works), but WILL appear
    on a Stamina+Agility cloak (tank role works).

    Death Knight extra rule: DK is a hero class — characters START at level
    55, so any item with RequiredLevel < 55 is filtered out for DK regardless
    of stats/armor. A level 55 DK rolling out of Acherus already has better
    quest gear than anything dropping in Ragefire Chasm or Wailing Caverns;
    showing those rows as "DK loot" would be misleading. BC reference items
    (req 60+) and WotLK gear still appear for DK.
    """
    DK_MIN_LEVEL = 55
    req = item.get('RequiredLevel', 0) or 0

    classes = []
    for cls in ALL_CLASSES:
        if cls == 'dk' and req < DK_MIN_LEVEL:
            continue
        for role in ('tank', 'heal', 'melee', 'ranged'):
            if class_fills_role(item, cls, role):
                classes.append(cls)
                break
    return classes


# ============================================================================
# Database queries
# ============================================================================

def fetch_boss_loot(cursor, boss_entry, quality_floor, req_level_max=None):
    """
    Pull all items dropped by a boss with computed effective drop chance.

    Handles two AzerothCore loot mechanisms that the database stores as
    Chance = 0:

    1. Reference loot (creature_loot_template.Reference != 0) — clt.Item is
       a reference_loot_template.Entry. Effective chance =
       (boss-side multiplier) × (within-reference chance).

    2. Group drops (GroupId > 0) — items in a group split chance: explicit
       chances are kept, then any zero-chance group members share whatever
       is left of 100% equally among themselves. So [A:30, B:0, C:0]
       resolves to [A:30, B:35, C:35].

    Both mechanisms can stack (a reference template can itself contain
    grouped items), and we resolve them in order: group share first within
    each pool, then the reference multiplier on top.

    `req_level_max`: optional cap on item RequiredLevel. Items requiring a
    higher level are filtered out — this excludes TBC/WotLK loot that got
    sprinkled into Classic boss loot tables in later patches.
    """
    # Shared item_template column list — kept in one place so both halves of
    # the lookup (direct + reference) return the same row shape.
    item_cols = """
        it.entry, it.name, it.Quality,
        it.InventoryType, it.class, it.subclass,
        it.ItemLevel, it.RequiredLevel, it.AllowableClass,
        it.itemset,
        it.armor,
        it.dmg_min1, it.dmg_max1, it.dmg_min2, it.dmg_max2, it.delay,
        it.bonding, it.MaxDurability, it.SellPrice,
        it.stat_type1, it.stat_value1,
        it.stat_type2, it.stat_value2,
        it.stat_type3, it.stat_value3,
        it.stat_type4, it.stat_value4,
        it.stat_type5, it.stat_value5,
        it.stat_type6, it.stat_value6,
        it.stat_type7, it.stat_value7,
        it.stat_type8, it.stat_value8,
        it.stat_type9, it.stat_value9,
        it.stat_type10, it.stat_value10,
        it.spellid_1, it.spelltrigger_1,
        it.spellid_2, it.spelltrigger_2,
        it.spellid_3, it.spelltrigger_3,
        it.spellid_4, it.spelltrigger_4,
        it.spellid_5, it.spelltrigger_5
    """

    # ---- 1. Direct drops (Reference = 0) ---------------------------------
    sql = f"""
        SELECT {item_cols},
               clt.Chance, clt.GroupId, clt.QuestRequired
        FROM creature_loot_template clt
        JOIN item_template it ON it.entry = clt.Item
        WHERE clt.Entry = (SELECT lootid FROM creature_template WHERE entry = %s)
          AND clt.Reference = 0
          AND it.Quality >= %s
          AND it.InventoryType > 0
          AND it.class IN (2, 4)             -- 2=weapon, 4=armor only
          AND it.InventoryType NOT IN (4, 19) -- exclude shirts & tabards
    """
    params = [boss_entry, quality_floor]
    if req_level_max is not None:
        sql += " AND it.RequiredLevel <= %s"
        params.append(req_level_max)
    cursor.execute(sql, params)
    direct = cursor.fetchall()
    for row in direct:
        # Pool key keeps direct items grouped together regardless of which
        # boss they come from in this call. Multiplier is 1 (no reference).
        row['_pool'] = 'direct'
        row['_multiplier'] = 1.0

    # ---- 2. Reference drops (Reference != 0) -----------------------------
    # Pulls items from reference_loot_template, with rlt.Entry tracked so
    # group share is computed within each reference independently.
    sql = f"""
        SELECT {item_cols},
               rlt.Chance, rlt.GroupId,
               rlt.Entry AS RefEntry,
               clt.Chance AS RefMultiplier,
               GREATEST(clt.QuestRequired, rlt.QuestRequired) AS QuestRequired
        FROM creature_loot_template clt
        JOIN reference_loot_template rlt ON rlt.Entry = clt.Item
        JOIN item_template it ON it.entry = rlt.Item
        WHERE clt.Entry = (SELECT lootid FROM creature_template WHERE entry = %s)
          AND clt.Reference != 0
          AND it.Quality >= %s
          AND it.InventoryType > 0
          AND it.class IN (2, 4)             -- 2=weapon, 4=armor only
          AND it.InventoryType NOT IN (4, 19) -- exclude shirts & tabards
    """
    params = [boss_entry, quality_floor]
    if req_level_max is not None:
        sql += " AND it.RequiredLevel <= %s"
        params.append(req_level_max)
    cursor.execute(sql, params)
    referenced = cursor.fetchall()
    for row in referenced:
        # Each reference template is its own pool (different references shouldn't
        # share group share). Multiplier is the boss's clt.Chance / 100.
        row['_pool'] = ('ref', row['RefEntry'])
        row['_multiplier'] = float(row.get('RefMultiplier') or 0) / 100.0

    rows = list(direct) + list(referenced)

    # ---- 3. Compute group-share chances ----------------------------------
    # Within each (pool, GroupId) where GroupId > 0, items with Chance = 0
    # split (100 - sum_explicit) equally. GroupId = 0 items keep stored
    # chance untouched (independent rolls).
    groups = defaultdict(list)
    for row in rows:
        gid = int(row.get('GroupId') or 0)
        if gid > 0:
            groups[(row['_pool'], gid)].append(row)

    for members in groups.values():
        sum_explicit = sum(
            float(m.get('Chance') or 0) for m in members
            if float(m.get('Chance') or 0) > 0
        )
        zeros = [m for m in members if float(m.get('Chance') or 0) == 0]
        if zeros:
            share = max(0.0, 100.0 - sum_explicit) / len(zeros)
            for m in zeros:
                m['Chance'] = share

    # ---- 4. Apply reference multiplier and finalize ----------------------
    for row in rows:
        chance = float(row.get('Chance') or 0)
        mult   = row.get('_multiplier', 1.0)
        # Cap at 100 just in case a misconfigured group sums above it.
        row['Chance'] = min(100.0, chance * mult)

    rows.sort(key=lambda r: (-(r.get('Quality') or 0), -(r.get('ItemLevel') or 0)))
    return rows


def fetch_boss_info(cursor, boss_entry):
    """Pull boss name, level info from creature_template."""
    cursor.execute("""
        SELECT entry, name, minlevel, maxlevel, `rank`
        FROM creature_template
        WHERE entry = %s
    """, (boss_entry,))
    return cursor.fetchone()


# ============================================================================
# Spell description handling — reads spell_descriptions.json (produced by
# convert_spells.py) and turns item spell IDs into human-readable effect text
# like "Equip: Increases attack power by 18."
# ============================================================================

def load_spell_descriptions(json_path):
    """Load spell descriptions JSON. Returns dict {spell_id: spell_data}.

    Returns empty dict if file is missing — equip text is then quietly skipped
    rather than failing the whole build. Run convert_spells.py to produce it.
    """
    if not os.path.exists(json_path):
        print(f"  [info] {json_path} not found — skipping equip/use effect text")
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"  [info] Loaded {len(data)} spell descriptions from {json_path}")
    return data


def fetch_durations(cnx):
    """Fetch the spellduration_dbc table into a {DurationIndex: ms} dict.

    Used to resolve $d placeholders in spell descriptions. Returns empty dict
    if the table doesn't exist or query fails — $d will then stay raw.
    """
    cursor = cnx.cursor(dictionary=True)
    try:
        cursor.execute("SELECT ID, Duration FROM spellduration_dbc")
        durations = {row['ID']: row['Duration'] for row in cursor.fetchall()}
        print(f"  [info] Loaded {len(durations)} duration entries from spellduration_dbc")
        return durations
    except mysql.connector.Error as e:
        print(f"  [info] Could not query spellduration_dbc: {e} — $d placeholders will be raw")
        return {}
    finally:
        cursor.close()


def load_item_sets_definitions(json_path):
    """Load itemsets.json (produced by convert_itemsets.py).

    Returns dict of {set_id_str: {name, items: [ids], bonuses: [{spellId, pieces}]}}.
    Empty dict if the file is missing — set tooltips simply won't render.
    """
    if not os.path.exists(json_path):
        print(f"  [info] {json_path} not found — set tooltips disabled "
              f"(run convert_itemsets.py to enable them)")
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"  [info] Loaded {len(data)} item sets from {json_path}")
    return data


def fetch_item_sets(cnx, set_ids, set_definitions, spell_descriptions, durations):
    """Resolve full set info for the given set IDs.

    `set_definitions`: output of load_item_sets_definitions() — provides set
    name, piece IDs, and bonus spell IDs/thresholds (from ItemSet.dbc CSV).

    `cnx` is used only to look up piece names from item_template, so server
    customisations to item names are reflected. If cnx is None, names fall
    back to "Item <id>".

    Returns dict of {set_id: {name, items: [{id, name}], bonuses: [{pieces, text}]}}.
    """
    if not set_ids or not set_definitions:
        return {}

    # Pull only the sets we actually need
    requested = {str(sid): set_definitions.get(str(sid))
                 for sid in set_ids if str(sid) in set_definitions}
    requested = {k: v for k, v in requested.items() if v}
    if not requested:
        return {}

    # Single MySQL query for piece name + quality across every requested set
    needed_item_ids = set()
    for sd in requested.values():
        needed_item_ids.update(sd.get('items', []))
    item_meta = {}
    if needed_item_ids and cnx is not None:
        cursor = cnx.cursor(dictionary=True)
        try:
            ids_csv = ','.join(str(i) for i in needed_item_ids)
            cursor.execute(
                f"SELECT entry, name, Quality FROM item_template WHERE entry IN ({ids_csv})")
            item_meta = {r['entry']: {'name': r['name'], 'quality': r['Quality']}
                         for r in cursor.fetchall()}
        except mysql.connector.Error as e:
            print(f"  [info] Could not look up set piece names: {e}")
        finally:
            cursor.close()

    sets_out = {}
    skipped_bonuses = 0
    for sid_str, sd in requested.items():
        sid = int(sid_str)
        pieces = [{
            'id':      iid,
            'name':    item_meta.get(iid, {}).get('name', f'Item {iid}'),
            'quality': item_meta.get(iid, {}).get('quality', 1),
        } for iid in sd.get('items', [])]
        # Set quality = highest piece quality (most sets are uniform; mixed
        # sets render as the better grade, which matches what the player
        # sees in-game when they hover the set tooltip).
        set_quality = max((p['quality'] for p in pieces), default=1)

        bonuses = []
        for b in sd.get('bonuses', []):
            spell_id = b['spellId']
            pieces_required = b['pieces']
            spell_data = spell_descriptions.get(str(spell_id))
            if not spell_data:
                skipped_bonuses += 1
                continue
            # Set bonuses are usually passive auras: their text lives in
            # auraDesc, not description. Fall through to auraDesc when the
            # active description is empty.
            raw_text = spell_data.get('description') or spell_data.get('auraDesc') or ''
            if not raw_text:
                skipped_bonuses += 1
                continue
            text = expand_placeholders(raw_text, spell_data, spell_descriptions, durations)
            bonuses.append({'pieces': pieces_required, 'text': text})
        bonuses.sort(key=lambda b: b['pieces'])

        sets_out[sid] = {
            'name':    sd['name'],
            'items':   pieces,
            'bonuses': bonuses,
            'quality': set_quality,
        }

    msg = f"  [info] Resolved {len(sets_out)} item set(s)"
    if skipped_bonuses:
        msg += f" ({skipped_bonuses} bonuses skipped — spell missing or has no text)"
    print(msg)
    return sets_out


# Regex for spell description placeholders. Three alternatives in one pattern:
#   - Effect-value:  $sN, $SN, $mN, $MN, $<spellID>sN, $<spellID>mN
#   - Duration:      $d, $D, $<spellID>d, $<spellID>D
#   - Proc chance:   $h, $H, $<spellID>h, $<spellID>H
# Where <spellID> (digits) is optional and means "look up that spell instead
# of the current one".
_PLACEHOLDER = re.compile(
    r'\$(?P<ref>\d*)(?:(?P<type>[sSmM])(?P<idx>[1-3])|(?P<dur>[dD])|(?P<proc>[hH]))'
)


def format_duration(ms):
    """Render a millisecond duration as 'X sec', 'Y min', 'Z hour(s)', etc."""
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


def expand_placeholders(text, spell_data, all_spells, durations=None):
    """Substitute placeholders in a spell description.

    Handles:
      $sN, $<spellID>sN  — effect value (BasePoints + 1, range if dice > 1)
      $mN, $<spellID>mN  — base points (no +1, used in some math idioms)
      $d,  $<spellID>d   — spell duration, looked up via spellduration_dbc
      $h,  $<spellID>h   — proc chance, read from spell.procChance (Spell.dbc)

    Special idiom: "$s1 to $s2 X damage" with no effect 2 → range of effect 1.

    Other placeholders (${expr}, $<mult>, $t) are left raw — rare in
    equip/use descriptions.
    """
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

        # Pick which spell's data to read from
        if ref_id:
            target = all_spells.get(ref_id)
            if not target:
                return m.group(0)  # spell not in our data, leave raw
        else:
            target = spell_data

        # $d / $<spellID>d → format duration
        if m.group('dur'):
            # Prefer durationMs baked into spell_descriptions.json by
            # convert_spells.py (when SpellDuration.csv was provided).
            # Fall back to looking up durationIdx in the MySQL durations dict.
            dur_ms = target.get('durationMs', 0)
            if not dur_ms:
                dur_idx = target.get('durationIdx', 0)
                if dur_idx:
                    dur_ms = durations.get(dur_idx, 0)
            if dur_ms <= 0:
                return m.group(0)
            return format_duration(dur_ms)

        # $h / $<spellID>h → proc chance (percentage, 0–100)
        if m.group('proc'):
            # Try common field-name variants so this works regardless of
            # whether convert_spells.py wrote 'procChance' (camelCase) or
            # 'proc_chance' (snake_case). If absent or zero, leave raw —
            # the player will see "$h%" and we'll know to update the JSON.
            proc = (target.get('procChance')
                    or target.get('proc_chance')
                    or target.get('ProcChance')
                    or 0)
            if proc <= 0:
                return m.group(0)
            # WoW's $h is shown as an integer % when whole, otherwise 1 dp
            return str(int(proc)) if proc == int(proc) else f"{proc:.1f}"

        # $sN / $mN
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

        # $sN: BasePoints + 1, possibly as a range
        val_min = bp + 1
        val_max = bp + ds
        if ds > 1 and val_max != val_min:
            lo, hi = sorted((abs(val_min), abs(val_max)))
            return f"{lo} to {hi}"
        return str(abs(val_min))

    return _PLACEHOLDER.sub(replace_match, text)


def build_effects(item, spell_descriptions, durations=None):
    """Build an `effects` list from item_template.spellid_1..5 + spelltrigger_1..5.

    Returns a list of dicts like:
        [{"trigger": "Equip", "text": "Increases attack power by 18."}]

    Skips slots where: spell ID is 0/missing, the spell isn't in our description
    data, or the trigger type isn't user-facing (e.g. recipe learning).
    """
    if not spell_descriptions:
        return []

    effects = []
    for slot in range(1, 6):
        spell_id  = item.get(f'spellid_{slot}', 0) or 0
        trigger   = item.get(f'spelltrigger_{slot}', 0) or 0
        if spell_id <= 0:
            continue
        trigger_label = SPELL_TRIGGER_LABELS.get(trigger, '')
        if not trigger_label:
            continue
        spell_data = spell_descriptions.get(str(spell_id))
        if not spell_data:
            continue
        # Prefer Description; fall back to AuraDescription for some Use spells
        # whose Description field is empty but whose aura has the player-facing
        # text (food/drink, scrolls, etc.).
        raw_text = spell_data.get('description') or spell_data.get('auraDesc') or ''
        if not raw_text:
            continue
        text = expand_placeholders(raw_text, spell_data, spell_descriptions, durations)
        effects.append({'trigger': trigger_label, 'text': text})
    return effects


def format_chance(chance):
    """Render an effective drop chance as a display string.

    Adapts decimal precision to magnitude so very small chances stay legible
    instead of all rounding to '0.0%':
      >= 1.0%       → '5.5%'    (one decimal)
      0.1 to 1.0%   → '0.55%'   (two decimals)
      0.01 to 0.1%  → '0.05%'   (two decimals)
      < 0.01%       → '<0.01%'  (the precise value isn't meaningful here)
      0 or negative → '—'        (genuinely never drops)
    """
    if chance is None or chance <= 0:
        return '\u2014'
    if chance >= 1.0:
        return f"{chance:.1f}%"
    if chance >= 0.01:
        return f"{chance:.2f}%"
    return "<0.01%"


def build_item_record(boss, item_row, dungeon_meta, dungeon_slug, spell_descriptions, durations):
    """Transform a DB row into the item dict that matches existing JSON format
    AND includes tooltip fields (matches armoury_api.py shape)."""
    item = dict(item_row)
    quality = item['Quality']

    # Compute slot fields
    item['slotFilter'] = slot_filter(item)
    item['slot'] = format_slot(item)

    # Parse stats
    item['stats'] = parse_stats(item)

    # Infer classes & roles using the smart filter rules
    classes = infer_classes(item)
    roles = infer_roles(item)

    # Drop chance — formatted with magnitude-aware precision so 0.04% doesn't
    # render as '0.0%'.
    chance = float(item.get('Chance') or 0)
    chance_str = format_chance(chance)

    # ----- Tooltip-specific fields -----
    # Damage range for weapons (from primary damage entry only — matches what
    # the in-game tooltip shows; secondary damage like "1-3 Frost" isn't
    # surfaced here for now).
    damage = ''
    if item.get('class') == ITEM_CLASS_WEAPON:
        dmin = item.get('dmg_min1') or 0
        dmax = item.get('dmg_max1') or 0
        if dmin and dmax:
            # En-dash to match WoW client tooltip styling
            damage = f"{int(dmin)}\u2013{int(dmax)} Damage"

    # Armor type / weapon type for the right side of the slot row in tooltip.
    armor_type = ''
    if item.get('class') == ITEM_CLASS_ARMOR:
        armor_type = ARMOR_SUBCLASS_NAMES.get(item.get('subclass'), '')
    elif item.get('class') == ITEM_CLASS_WEAPON:
        armor_type = WEAPON_SUBCLASS_NAMES.get(item.get('subclass'), '')

    # Bonding (Soulbound / BoE / Quest Item / etc.)
    bonding = item.get('bonding', 0) or 0

    # Sell price split into gold/silver/copper for the coin row in tooltip
    sell_price = item.get('SellPrice', 0) or 0
    sell_gold = sell_price // 10000
    sell_silver = (sell_price % 10000) // 100
    sell_copper = sell_price % 100

    max_durability = item.get('MaxDurability', 0) or 0

    # Weapon speed (seconds) and DPS (calculated from damage range and delay).
    # None for non-weapons; tooltip.js renders the damage row differently when
    # speed is absent.
    speed, dps = weapon_speed_dps(item)

    # Equip/Use/Proc effects with description text from spell_descriptions.json,
    # combined with stat-based "Equip: Improves X by N" lines from rating stats.
    effects = build_effects(item, spell_descriptions, durations) + parse_stat_effects(item)

    return {
        'id':         item['entry'],
        'name':       item['name'],
        'quality':    quality,
        'qualityName': QUALITY_NAMES.get(quality, 'Common'),
        'color':      QUALITY_COLORS.get(quality, '#ffffff'),
        'ilvl':       item['ItemLevel'],
        'req':        item['RequiredLevel'],
        'slot':       item['slot'],
        'slotFilter': item['slotFilter'],
        'isWand':     item.get('class') == ITEM_CLASS_WEAPON and item.get('subclass') == 19,
        'itemClass':  item.get('class') or 0,
        'subclass':   item.get('subclass') or 0,
        'setId':      item.get('itemset') or 0,
        'armorType':  armor_type,
        'damage':     damage,
        'speed':      speed,
        'dps':        dps,
        'stats':      item['stats'],
        'effects':    effects,
        'bonding':    bonding,
        'bondingName': BONDING_NAMES.get(bonding, ''),
        'maxDurability': max_durability,
        'sellPrice':  sell_price,
        'sellGold':   sell_gold,
        'sellSilver': sell_silver,
        'sellCopper': sell_copper,
        'roles':      roles,
        'classes':    classes,
        'chance':     chance,
        'chanceStr':  chance_str,
        'bossId':     boss['entry'],
        'bossName':   boss['name'],
        'bossLvl':    boss['maxlevel'],
        'mapId':      dungeon_meta['mapid'],
        'dungeon':    dungeon_meta['title'],
        'page':       dungeon_meta['page'],
        'faction':    dungeon_meta['faction'],
        'wing':       boss.get('wing'),
    }


def fetch_set_dropping_creature_ids(cnx):
    """One-time global lookup: every creature_template.entry whose loot table
    contains at least one item with itemset > 0.

    This is the expensive half of the trash-discovery query — it joins three
    large tables (creature_template, creature_loot_template, item_template,
    plus reference_loot_template). Computing it once and reusing the result
    across all dungeons replaces N expensive global queries with N cheap
    per-map intersections. Returns set of entry IDs.
    """
    cursor = cnx.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT ct.entry
            FROM creature_template ct
            JOIN creature_loot_template clt ON clt.Entry = ct.lootid AND clt.Reference = 0
            JOIN item_template it ON it.entry = clt.Item
            WHERE it.itemset > 0 AND it.class IN (2, 4)
            UNION
            SELECT DISTINCT ct.entry
            FROM creature_template ct
            JOIN creature_loot_template clt ON clt.Entry = ct.lootid AND clt.Reference != 0
            JOIN reference_loot_template rlt ON rlt.Entry = clt.Item
            JOIN item_template it ON it.entry = rlt.Item
            WHERE it.itemset > 0 AND it.class IN (2, 4)
        """)
        entries = {row[0] for row in cursor.fetchall()}
        print(f"  [info] {len(entries)} creature(s) drop set pieces (cached for all dungeons)")
        return entries
    except mysql.connector.Error as e:
        print(f"  [warn] Could not pre-compute set-dropping creatures: {e}")
        return set()
    finally:
        cursor.close()


def discover_set_piece_droppers(cnx, map_id, existing_entries, set_dropping_entries):
    """Find every creature spawned in the given map that has a loot table
    and isn't already tracked as a config-defined boss. Used to surface
    trash-only drops on dungeon pages and in Find Loot.

    The `set_dropping_entries` parameter is no longer used (kept for
    backward signature compat); previously this function intersected
    with set-droppers only. Switched to "all trash" per user request so
    that items like the Oscillating Power Hammer (drops only from
    Caverndeep Ambusher rank-0 trash) appear on the dungeon page.

    AzerothCore stores spawned creatures in `creature` with id1/id2/id3
    columns (multi-template spawn support). We UNION across all three so a
    creature that spawns in any slot is captured.

    Returns list of {entry, name, minlevel, maxlevel, rank}.
    """
    cursor = cnx.cursor(dictionary=True)
    try:
        # 1. Which creature_template entries spawn in this map?
        cursor.execute("""
            SELECT DISTINCT id1 AS entry FROM creature WHERE map = %s AND id1 > 0
            UNION SELECT DISTINCT id2 FROM creature WHERE map = %s AND id2 > 0
            UNION SELECT DISTINCT id3 FROM creature WHERE map = %s AND id3 > 0
        """, (map_id, map_id, map_id))
        spawned = {row['entry'] for row in cursor.fetchall()}

        # 2. Exclude already-tracked bosses; keep every other spawned creature
        existing = {int(e) for e in existing_entries} if existing_entries else set()
        candidates = spawned - existing
        if not candidates:
            return []

        # 3. Fetch metadata for the candidates, filtered to those with a
        # loot table. Creatures with lootid=0 have nothing to contribute.
        # `rank` is a reserved keyword in MySQL 8.0+ (window functions) so
        # backtick it.
        ids_csv = ','.join(str(e) for e in candidates)
        cursor.execute(f"""
            SELECT entry, name, minlevel, maxlevel, `rank`
            FROM creature_template
            WHERE entry IN ({ids_csv})
              AND lootid > 0
            ORDER BY minlevel, entry
        """)
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"  [warn] Could not discover trash for map {map_id}: {e}")
        return []
    finally:
        cursor.close()


def build_dungeon(cnx, slug, dungeon, spell_descriptions, durations, quality_floor=2,
                  level_buffer=10, min_chance=None, include_trash_set_pieces=True,
                  set_dropping_entries=None):
    """Process all bosses in one dungeon. Returns (items, boss_count, no_loot, over_skipped, bosses).

    `bosses` is a list of {id, name, level, page, ...} for EVERY boss successfully
    looked up in creature_template — even those with no equipment loot. Used by
    the page generator to render placeholder cards for completeness.

    `level_buffer`: items with RequiredLevel > boss.maxlevel + level_buffer are
    filtered out. This excludes TBC/WotLK loot patched into Classic boss tables.
    Set to None to disable the filter (return all items).

    `include_trash_set_pieces`: when True, also discovers and processes any
    elite trash mobs in the dungeon's map that drop items belonging to a set.
    This makes set tooltips accurate (no pieces marked as ✗ when they're
    actually farmable from trash). Each item record gets source='boss' or
    source='trash' for downstream UI distinction.
    """
    cursor = cnx.cursor(dictionary=True)
    items = []
    bosses_processed = 0
    bosses_with_no_loot = []
    over_level_skipped = 0
    bosses_meta = []  # every boss we saw, regardless of loot
    trash_count = 0

    def process_creature(entry_dict, source):
        """Run a single creature through the loot pipeline. Used for both
        config-defined bosses and auto-discovered trash. Pushes to outer
        `items`, `bosses_meta`, `bosses_with_no_loot` and updates
        `over_level_skipped`. Mutating closure for brevity."""
        nonlocal over_level_skipped
        bid = entry_dict['id']
        boss_db = fetch_boss_info(cursor, bid)
        if not boss_db:
            print(f"  ! Creature {bid} ({entry_dict.get('name', '?')}) not in creature_template — skipping")
            return False
        boss_db['wing'] = entry_dict.get('wing')

        req_level_max = None
        if level_buffer is not None and boss_db.get('maxlevel'):
            req_level_max = int(boss_db['maxlevel']) + int(level_buffer)

        all_loot = fetch_boss_loot(cursor, bid, quality_floor, None)
        if req_level_max is not None:
            loot = [r for r in all_loot if (r.get('RequiredLevel') or 0) <= req_level_max]
            over_level_skipped += len(all_loot) - len(loot)
        else:
            loot = all_loot

        # All items (boss + trash) are filtered to Rare+ (Quality >= 3)
        # OR set pieces. Many dungeon bosses link to shared reference
        # loot pools full of Uncommon world-drop greens that aren't
        # really part of the boss's signature loot — Zul'Farrak and
        # BRD especially were dominated by these. Set pieces are
        # always kept regardless of quality.
        loot = [
            r for r in loot
            if (r.get('Quality') or 0) >= 3 or (r.get('itemset') or 0) > 0
        ]

        bosses_meta.append({
            'id':       bid,
            'name':     entry_dict.get('name') or boss_db.get('name'),
            'minLevel': boss_db.get('minlevel'),
            'maxLevel': boss_db.get('maxlevel'),
            'rank':     boss_db.get('rank'),
            'mapId':    dungeon['mapid'],
            'page':     dungeon['page'],
            'wing':     entry_dict.get('wing'),
            'hasLoot':  bool(loot),
            'source':   source,
        })

        if not loot:
            bosses_with_no_loot.append(entry_dict.get('name') or boss_db.get('name'))
            return True  # still counted as processed

        for item_row in loot:
            chance = float(item_row.get('Chance') or 0)
            if chance <= 0:
                continue
            if min_chance is not None and chance < min_chance:
                continue
            rec = build_item_record(
                boss_db, item_row, dungeon, slug, spell_descriptions, durations)
            rec['source'] = source
            items.append(rec)
        return True

    # 1) Config-defined bosses
    for boss_entry in dungeon['bosses']:
        if process_creature(boss_entry, 'boss'):
            bosses_processed += 1

    # 2) Auto-discovered trash that drops set pieces. We deliberately limit
    # this to set-piece droppers (rather than all elite trash) — the goal is
    # to make set tooltips accurate, not to flood Find Loot with every elite
    # mob's drop table.
    if include_trash_set_pieces and dungeon.get('mapid'):
        existing_ids = {b['id'] for b in dungeon['bosses']}
        candidates = discover_set_piece_droppers(
            cnx, dungeon['mapid'], existing_ids, set_dropping_entries or set())
        for cand in candidates:
            entry_dict = {'id': cand['entry'], 'name': cand['name']}
            if process_creature(entry_dict, 'trash'):
                trash_count += 1

    cursor.close()
    return items, bosses_processed, bosses_with_no_loot, over_level_skipped, bosses_meta, trash_count


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', default='build_config.yaml',
        help='Path to YAML config (default: build_config.yaml)')
    parser.add_argument('--out', default='loot-data.json',
        help='Output JSON path (default: loot-data.json)')
    parser.add_argument('--dungeon', default=None,
        help='Process only this dungeon slug (e.g. shadowfang-keep). Default: all.')
    parser.add_argument('--dry-run', action='store_true',
        help='Print summary, do not write output file.')
    parser.add_argument('--update-index', metavar='PATH', default=None,
        help='Path to index.html — if given, the JSON is also patched directly into '
             'the <script id="loot-data"> element. Saves a manual paste step.')
    parser.add_argument('--spells', metavar='PATH', default='spell_descriptions.json',
        help='Path to spell_descriptions.json (produced by convert_spells.py). '
             'Default: spell_descriptions.json. If missing, equip/use text is skipped.')
    parser.add_argument('--itemsets', metavar='PATH', default='itemsets.json',
        help='Path to itemsets.json (produced by convert_itemsets.py). '
             'Default: itemsets.json. If missing, set tooltips are skipped.')
    parser.add_argument('--no-trash-set-pieces', dest='trash_set_pieces',
        action='store_false', default=True,
        help='Disable auto-discovery of trash mobs that drop set pieces. '
             'By default, elite trash that drops items belonging to a set '
             '(e.g. Defias Overseer → Blackened Defias Gloves) is included '
             'so set tooltips have full piece coverage. Pass this to '
             'restrict to config-defined bosses only.')
    parser.add_argument('--build-pages', metavar='DIR', nargs='?', const='.', default=None,
        help='Also render the 9 dungeon HTML pages from this run. Optionally pass a '
             'directory (default: cwd). Requires build_pages.py alongside this script.')
    parser.add_argument('--level-buffer', type=int, default=10,
        help='Filter out items where RequiredLevel > boss.maxlevel + this value. '
             'Default: 10. Excludes TBC/WotLK items patched into Classic boss tables. '
             'Set to a very large number (e.g. 999) to disable. Per-dungeon override '
             'in YAML via "level_buffer:" field.')
    parser.add_argument('--min-chance', type=float, default=None,
        help='Drop items whose effective chance is below this percentage. Items '
             'with truly 0%% chance (group members that can never roll) are '
             'always filtered. Examples: --min-chance 0.5 hides anything below '
             '0.5%%; useful for cutting out world-drop noise from reference loot.')
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))

    dungeons = config['dungeons']
    if args.dungeon:
        if args.dungeon not in dungeons:
            sys.exit(f"Dungeon '{args.dungeon}' not in config. Available: {list(dungeons.keys())}")
        dungeons = {args.dungeon: dungeons[args.dungeon]}

    # Load spell descriptions (used to populate `effects` on each item)
    spell_descriptions = load_spell_descriptions(args.spells)

    # Load item set definitions (used for set tooltips on set pieces)
    set_definitions = load_item_sets_definitions(args.itemsets)

    # Connect to DB
    print(f"Connecting to {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']} ...")
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        sys.exit(f"DB connection failed: {e}")

    # Fetch spellduration_dbc once for $d placeholder substitution
    durations = fetch_durations(cnx)

    # Pre-compute creatures that drop set pieces (one global query, shared
    # across all dungeons — replaces what was N redundant joins). Skipped
    # when --no-trash-set-pieces is set since we won't use it.
    set_dropping_entries = (
        fetch_set_dropping_creature_ids(cnx)
        if args.trash_set_pieces else set()
    )

    # Process each dungeon
    all_items = []
    all_dungeons_meta = []
    all_bosses_meta = []
    total_bosses = 0
    no_loot_bosses = []

    for slug, dungeon in dungeons.items():
        quality_floor = dungeon.get('quality_floor', 2)
        level_buffer = dungeon.get('level_buffer', args.level_buffer)
        print(f"\n[{slug}] map={dungeon['mapid']} quality_floor={quality_floor} "
              f"level_buffer=+{level_buffer} bosses={len(dungeon['bosses'])}")

        items, boss_count, empty, over_skipped, bosses_meta, trash_count = build_dungeon(
            cnx, slug, dungeon, spell_descriptions, durations, quality_floor,
            level_buffer, args.min_chance,
            include_trash_set_pieces=args.trash_set_pieces,
            set_dropping_entries=set_dropping_entries)
        all_items.extend(items)
        all_bosses_meta.extend(bosses_meta)
        total_bosses += boss_count
        no_loot_bosses.extend(empty)

        # Per-dungeon meta (matches existing JSON)
        # Both level signals shipped:
        #   `lvl`    = recommended_level (Wowhead-style player guideline)
        #   `mobLvl` = actual creature level range — the source of truth for
        #              "is this dungeon for me right now". Used by the Find
        #              Loot dropdown sort and label so it matches what the
        #              Browse Dungeons cards show.
        all_dungeons_meta.append({
            'id':      dungeon['mapid'],
            'name':    dungeon['title'],
            'page':    dungeon['page'],
            'faction': dungeon['faction'],
            'lvl':     dungeon.get('recommended_level', '?'),
            'mobLvl':  dungeon.get('mob_level', '?'),
            'count':   len(items),
        })

        msg = f"  {boss_count} bosses, {len(items)} items"
        if trash_count:
            msg += f" (incl. {trash_count} trash mob(s) dropping set pieces)"
        if over_skipped:
            msg += f", {over_skipped} item(s) excluded by level filter"
        if empty:
            msg += f", {len(empty)} bosses with no loot at q>={quality_floor}"
        print(msg)

    # Resolve item-set definitions (Defias Leather, Embrace of the Viper, etc.)
    # for every distinct set referenced by the items we've built. Done before
    # closing the connection so we can issue one MySQL query for the lot.
    set_ids = {it['setId'] for it in all_items if it.get('setId')}
    item_sets = fetch_item_sets(cnx, set_ids, set_definitions, spell_descriptions, durations)

    # Denormalize: attach the full set definition to each item that belongs to
    # one. The dungeon HTML pages embed item JSON per row (data-item-json) so
    # each row needs to be self-contained for the tooltip — there's no shared
    # sets dict on those pages. Bloat is small (~500 bytes per piece) and the
    # alternative of registering a sets table per surface is more plumbing.
    for it in all_items:
        sid = it.get('setId')
        if sid and sid in item_sets:
            it['set'] = item_sets[sid]

    cnx.close()

    # Default sort: by drop chance DESC, then name ASC for ties. Both
    # downstream surfaces (Find Loot table and per-boss tables on dungeon
    # pages) iterate this list in order, so a single sort here gives both
    # the same default ordering. Users can still re-sort interactively
    # via the sort headers — this just sets the initial state.
    all_items.sort(key=lambda it: (-(it.get('chance') or 0), (it.get('name') or '').lower()))

    # Build output structure
    output = {
        'meta': {
            'totalItems':    len(all_items),
            'totalBosses':   total_bosses,
            'totalDungeons': len(all_dungeons_meta),
        },
        'dungeons': all_dungeons_meta,
        'bosses':   all_bosses_meta,
        'items':    all_items,
        # Resolved gear-set details (name, items[id,name,quality],
        # bonuses[pieces,text], quality) keyed by setId. Persisted so the
        # standalone `build_pages.py --json` path renders the gear-set
        # callout the same as the integrated --build-pages path.
        'itemSets': item_sets,
    }

    # Summary
    print(f"\n{'='*60}")
    print(f"Total: {len(all_items)} items across {total_bosses} bosses in {len(all_dungeons_meta)} dungeons")

    # Drop-chance coverage — how many items still show "—" because the chance
    # resolves to 0 (typically GroupId pool members where the chance is computed
    # by group share math rather than stored as a single value).
    n_resolved = sum(1 for it in all_items if (it.get('chance') or 0) > 0)
    n_dashed   = len(all_items) - n_resolved
    if all_items:
        pct = 100.0 * n_resolved / len(all_items)
        print(f"Drop chances: {n_resolved}/{len(all_items)} resolved ({pct:.0f}%), "
              f"{n_dashed} still showing '—'")

    if no_loot_bosses:
        print(f"\nBosses with no loot at the configured quality floor:")
        for n in no_loot_bosses:
            print(f"  - {n}")
        print(f"(Lower the dungeon's quality_floor in build_config.yaml to include them.)")

    if args.dry_run:
        print("\n(--dry-run: not writing output file)")
    else:
        out_path = Path(args.out)
        json_text = json.dumps(output, separators=(',', ':'))
        out_path.write_text(json_text, encoding='utf-8')
        print(f"\n✓ Wrote {out_path} ({out_path.stat().st_size:,} bytes)")

        # Optional: patch index.html in place
        if args.update_index:
            idx_path = Path(args.update_index)
            if not idx_path.exists():
                print(f"\n! --update-index: file not found: {idx_path}")
            else:
                html = idx_path.read_text(encoding='utf-8')
                pattern = re.compile(
                    r'(<script id="loot-data" type="application/json">)'
                    r'.*?'
                    r'(</script>)',
                    re.DOTALL
                )
                m = pattern.search(html)
                if not m:
                    print(f"\n! --update-index: could not find <script id=\"loot-data\"> in {idx_path}")
                else:
                    new_html = pattern.sub(
                        lambda mm: mm.group(1) + json_text + mm.group(2),
                        html, count=1
                    )

                    # Also embed class_info.json so index.html and dungeon
                    # pages share a single source of truth for class colors,
                    # letters, and display names. Silently no-op if either
                    # the JSON file or the target script tag is missing — the
                    # page still has its inline CLASS_INFO fallback.
                    class_info_path = Path(__file__).parent / 'class_info.json'
                    class_pattern = re.compile(
                        r'(<script id="class-info" type="application/json">)'
                        r'.*?'
                        r'(</script>)',
                        re.DOTALL
                    )
                    if class_info_path.exists() and class_pattern.search(new_html):
                        ci_text = class_info_path.read_text(encoding='utf-8').strip()
                        new_html = class_pattern.sub(
                            lambda mm: mm.group(1) + ci_text + mm.group(2),
                            new_html, count=1
                        )
                        print(f"  (also embedded class_info.json)")

                    # Backup before overwriting
                    backup = idx_path.with_suffix(idx_path.suffix + '.bak')
                    backup.write_text(html, encoding='utf-8')
                    idx_path.write_text(new_html, encoding='utf-8')
                    print(f"✓ Patched {idx_path} (backup saved to {backup.name})")
        else:
            print(f"\nNext: paste this JSON into index.html, replacing the contents")
            print(f'of <script id="loot-data" type="application/json">...</script>')
            print(f"(Or re-run with --update-index path/to/index.html to do it automatically.)")

        # Optional: render dungeon HTML pages from the items we just produced
        if args.build_pages is not None:
            try:
                from build_pages import build_pages
            except ImportError:
                print(f"\n! --build-pages: build_pages.py not found alongside this script.")
            else:
                build_pages(config, all_items, args.build_pages,
                            bosses=all_bosses_meta, item_sets=item_sets)


if __name__ == '__main__':
    main()
