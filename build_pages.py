"""
build_pages.py — Render dungeon HTML pages from build_config.yaml + the
in-memory items list produced by build_dungeons.

Imported by build_dungeons.py and called when --build-pages is set.
Can also be invoked standalone if you already have a loot-data.json:
    python build_pages.py --config build_config.yaml --json loot-data.json --out-dir .
"""

import argparse
import collections
import html
import json
import re
import sys
from pathlib import Path

# Standalone import compatibility
try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Static colour / style mappings (must match WC's existing inline styling)
# ---------------------------------------------------------------------------

CLASS_COLORS = {}
CLASS_LETTER = {}
CLASS_DISPLAY = {}
ALL_CLASSES = []

def _load_item_sets():
    """Load itemsets.json so the Loot Summary can show which gear sets a
    dungeon drops pieces of. Silently returns {} if the file is missing —
    the set note just won't render."""
    try:
        path = Path(__file__).parent / 'itemsets.json'
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


ITEM_SETS = _load_item_sets()


def _load_class_info():
    """Load class display data from class_info.json (single source of truth,
    shared with index.html via build_dungeons.py --update-index)."""
    here = Path(__file__).parent
    candidates = [here / 'class_info.json', here / '..' / 'class_info.json']
    for p in candidates:
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            ALL_CLASSES[:] = list(data.get('all', []))
            for cls, info in (data.get('classes') or {}).items():
                CLASS_DISPLAY[cls] = info['display']
                CLASS_COLORS[cls]  = info['color']
                CLASS_LETTER[cls]  = info['letter']
            return p
    raise FileNotFoundError(
        "class_info.json not found alongside build_pages.py — "
        "this file is the source of truth for class display data."
    )

_CLASS_INFO_PATH = _load_class_info()

ROLE_PILL = {
    # role → (bg, fg, glyph, title)
    'tank':   ('#3a5a7a', '#87ceeb', '🛡', 'Tank'),
    'heal':   ('#2d5a3d', '#7ec896', '+',  'Healer'),
    'melee':  ('#7a3a3a', '#e88080', '⚔',  'Melee DPS'),
    'ranged': ('#7a5a2d', '#e8c87e', '🏹', 'Ranged DPS'),
}

ALL_ROLES = ['tank', 'heal', 'melee', 'ranged']


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def esc(s):
    """Escape a string for HTML body content."""
    return html.escape(str(s) if s is not None else '', quote=False)


def attr(s):
    """Escape a string for use inside double-quoted HTML attribute."""
    return html.escape(str(s) if s is not None else '', quote=True)


def stats_text(item):
    """Format the stats array as a comma-separated string."""
    stats = item.get('stats') or []
    if not stats:
        return ''
    parts = []
    for s in stats:
        if isinstance(s, dict):
            v = s.get('value', 0)
            n = s.get('name', '')
            sign = '+' if v >= 0 else ''
            parts.append(f"{sign}{v} {n}")
        elif isinstance(s, str):
            parts.append(s)
    return ', '.join(parts)


def role_pills_html(roles):
    out = []
    for r in ALL_ROLES:
        if r in roles:
            bg, fg, glyph, title = ROLE_PILL[r]
            out.append(f'<span class="role-pill" style="background:{bg};color:{fg};" '
                       f'title="{attr(title)}">{glyph}</span>')
    if not out:
        return '<span class="pill-empty">\u2014</span>'
    return '\n                            '.join(out)


def class_pills_html(classes):
    out = []
    # Render in the canonical class order (consistent across pages)
    for cls in ALL_CLASSES:
        if cls in classes:
            colour = CLASS_COLORS[cls]
            letter = CLASS_LETTER[cls]
            out.append(f'<span class="class-pill" style="background:{colour};" '
                       f'title="{attr(CLASS_DISPLAY[cls])}">{letter}</span>')
    if not out:
        return '<span class="pill-empty">\u2014</span>'
    return '\n                            '.join(out)


def render_item_row(item):
    """Produce a single <tr class="item-row"> for one item."""
    roles = item.get('roles') or []
    classes = item.get('classes') or []

    # Tooltip data — embed a compact JSON blob; tooltip.js reads it.
    item_json = json.dumps(item, separators=(',', ':'), ensure_ascii=False)

    # Item name colour comes from 'color' field (#0070dd = blue, #1eff00 = green)
    name_color = item.get('color', '#ffffff')
    # The 'slot' field already contains the parenthetical armor/weapon type
    # (e.g. "Chest (Plate)") — armorType is for the tooltip, not the row.
    slot_text = item.get('slot', '')
    stats = stats_text(item)
    chance = item.get('chanceStr') or '—'

    return f'''                    <tr class="item-row"
                        data-roles="{attr(' '.join(roles))}"
                        data-classes="{attr(' '.join(classes))}"
                        data-req="{attr(item.get('req', 0))}"
                        data-item-id="{attr(item.get('id', 0))}"
                        data-item-json="{attr(item_json)}">
                        <td><span style="color:{esc(name_color)}; font-weight:600;">{esc(item.get('name', ''))}</span></td>
                        <td><span class="slot-text">{esc(slot_text)}</span></td>
                        <td><span class="stat-text">{esc(stats)}</span></td>
                        <td>
                            {role_pills_html(roles)}
                        </td>
                        <td>
                            {class_pills_html(classes)}
                        </td>
                        <td class="text-end">{esc(item.get('ilvl', ''))}</td>
                        <td class="text-end">{esc(chance)}</td>
                    </tr>'''


def render_boss_card(boss_cfg, items, boss_meta=None):
    """Render one <div class="card boss-card"> for a boss + its loot.

    `items` may be an empty list — in that case we emit a placeholder
    "No equipment drops" card instead of a table.
    `boss_meta` (optional): the {id, name, maxLevel, ...} record from the JSON,
    used to pull the boss level when items is empty.
    """
    boss_type = boss_cfg.get('type', 'boss')
    is_rare  = boss_type == 'rare'  or boss_cfg.get('rare')
    is_trash = boss_type == 'notable_trash'

    if is_trash:
        marker = '🗡️ '
    elif is_rare:
        marker = '⭐ '
    else:
        marker = ''
    name = esc(boss_cfg['name'])

    # boss-meta line — match WC's pattern "desc · notable · Level X Elite · Entry NNNN"
    meta_parts = []
    if boss_cfg.get('description'):
        meta_parts.append(esc(boss_cfg['description']))
    if boss_cfg.get('notable'):
        meta_parts.append(esc(boss_cfg['notable']))

    # Pull boss level — from items if we have any, else from boss_meta
    boss_lvl = None
    if items:
        boss_lvl = items[0].get('bossLvl')
    elif boss_meta:
        boss_lvl = boss_meta.get('maxLevel')
    if boss_lvl:
        meta_parts.append(f"Level {boss_lvl} Elite")
    meta_parts.append(f"Entry {boss_cfg['id']}")
    meta_line = ' · '.join(meta_parts)

    # No-loot placeholder card
    if not items:
        return f'''
    <!-- {esc(boss_cfg['name'])} -->
    <details class="card boss-card">
        <summary class="boss-card-summary">
            <h3 class="card-title">{marker}{name}</h3>
        </summary>
        <div class="boss-card-content">
            <p class="boss-meta">{meta_line}</p>
            <p class="no-equipment-drops" style="color:#777; font-style:italic; text-align:center; padding:1rem 0;">
                No equipment drops at this quality level.
            </p>
        </div>
    </details>'''

    rows = '\n'.join(render_item_row(it) for it in items)

    return f'''
    <!-- {esc(boss_cfg['name'])} -->
    <details class="card boss-card">
        <summary class="boss-card-summary">
            <h3 class="card-title">{marker}{name}</h3>
        </summary>
        <div class="boss-card-content">
            <p class="boss-meta">{meta_line}</p>
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th style="width:23%">ITEM</th>
                        <th style="width:13%">SLOT</th>
                        <th class="no-sort" style="width:21%">STATS</th>
                        <th style="width:10%">ROLES</th>
                        <th style="width:17%">CLASSES</th>
                        <th class="text-end" style="width:8%">ILVL</th>
                        <th class="text-end" style="width:8%">DROP</th>
                    </tr>
                </thead>
                <tbody>
{rows}
                </tbody>
            </table>
            <p class="no-loot" style="display:none;">No items match these filters for this boss.</p>
        </div>
    </details>'''


def render_summary_block(summary, set_data=None):
    """Render the alert-dark Loot Summary block from the YAML 'summary' field.
    If `set_data` is non-empty, append a "🛡 Gear sets" callout listing each
    set's pieces and bonuses. set_data items are dicts: {name, items, bonuses}
    where items=[{id,name}] and bonuses=[{pieces,text}]."""
    if not summary:
        return ''
    heading = esc(summary.get('heading', 'Loot Summary'))
    intro = summary.get('intro', '')
    bullets = summary.get('bullets') or []

    # Intro often has "Equipment Focus: ..." at the start in WC. Detect that
    # pattern and add the strong tag for consistency.
    intro_html = ''
    if intro:
        m = re.match(r'^([A-Z][A-Za-z ]+?):\s*(.*)$', intro)
        if m:
            intro_html = (f'<strong style="color:#4ea8de;">{esc(m.group(1))}:</strong> '
                          f'{esc(m.group(2))}')
        else:
            intro_html = esc(intro)

    bullets_html = []
    for b in bullets:
        if isinstance(b, dict):
            label = b.get('label', '')
            text  = b.get('text', '')
            if label:
                bullets_html.append(
                    f'            <li><strong style="color:#4ea8de;">{esc(label)}:</strong> {esc(text)}</li>'
                )
            else:
                bullets_html.append(f'            <li>{esc(text)}</li>')
        else:
            bullets_html.append(f'            <li>{esc(b)}</li>')

    bullets_str = '\n'.join(bullets_html)

    # Optional gear-set callout — for every set with at least one piece
    # dropping in this dungeon, list its items and bonuses. Heading in
    # gold (matches page heading); set names + piece-count labels in cyan
    # (matches the existing "Best for / Famous for" labels in the box —
    # neutral, no implied quality).
    set_note_html = ''
    if set_data:
        set_blocks = []
        for s in set_data:
            name = esc(s.get('name', ''))
            pieces = s.get('items') or []
            bonuses = s.get('bonuses') or []

            items_html = ''
            if pieces:
                items_html = (
                    '<div style="margin-top: 0.15rem; color:#bbb;">'
                    + ', '.join(esc(p.get('name', f"Item {p.get('id','?')}"))
                                for p in pieces)
                    + '</div>'
                )

            bonuses_html = ''
            if bonuses:
                lis = ''.join(
                    f'<li><strong style="color:#4ea8de;">{b["pieces"]} pieces:</strong> '
                    f'{esc(b.get("text",""))}</li>'
                    for b in bonuses
                )
                bonuses_html = (
                    '<ul style="margin: 0.25rem 0 0 0; padding-left: 1.2rem;">'
                    f'{lis}</ul>'
                )

            set_blocks.append(
                '<div style="margin-top: 0.5rem;">'
                f'<strong style="color:#e6cc80;">{name}</strong>'
                f'{items_html}{bonuses_html}'
                '</div>'
            )

        set_note_html = (
            '\n        <div class="gear-sets-note" style="margin-top: 0.6rem; '
            'padding-top: 0.6rem; border-top: 1px solid #3a3a3a;">'
            '<strong style="color:#ffd100;">🛡 Gear sets</strong>'
            + ''.join(set_blocks)
            + '</div>'
        )

    return f'''    <div class="alert alert-dark mt-3 mb-4" style="background:#232323; border:1px solid #3a3a3a; color:#ddd;">
        <h5 class="alert-heading" style="color:#ffd100;">{heading}</h5>
        <p class="mb-2">{intro_html}</p>
        <ul class="mb-0" style="margin-left: 0; padding-left: 1.2rem;">
{bullets_str}
        </ul>{set_note_html}
    </div>'''


def render_filter_bar(total_count, role_counts, class_counts):
    """Render the sticky filter bar with computed counts."""
    role_buttons = [
        ('all',    f'All (<span id="count-all">{total_count}</span>)'),
        ('tank',   f'🛡 Tank (<span id="count-tank">{role_counts.get("tank", 0)}</span>)'),
        ('heal',   f'+ Healer (<span id="count-heal">{role_counts.get("heal", 0)}</span>)'),
        ('melee',  f'⚔ Melee (<span id="count-melee">{role_counts.get("melee", 0)}</span>)'),
        ('ranged', f'🏹 Ranged (<span id="count-ranged">{role_counts.get("ranged", 0)}</span>)'),
    ]
    role_html = '\n            '.join(
        f'<button class="filter-btn{"" if r != "all" else " active"}" data-role="{r}">{label}</button>'
        for r, label in role_buttons
    )

    class_options = [f'<option value="all">All classes ({total_count})</option>']
    for cls in ALL_CLASSES:
        n = class_counts.get(cls, 0)
        if n > 0:
            class_options.append(
                f'<option value="{cls}">{CLASS_DISPLAY[cls]} ({n})</option>'
            )
    class_options_html = '\n                    '.join(class_options)

    legend_pills = []
    for cls in ALL_CLASSES:
        # Wrap each pill+name in a nowrap span so multi-word classes like
        # "Death Knight" can't break across lines, and the pill never gets
        # orphaned from its name when the legend wraps.
        legend_pills.append(
            f'<span class="legend-item">'
            f'<span class="class-pill" style="background:{CLASS_COLORS[cls]};color:#1a1a1a;">'
            f'{CLASS_LETTER[cls]}</span> {CLASS_DISPLAY[cls]}'
            f'</span>'
        )
    legend_html = '\n                '.join(legend_pills)

    return f'''    <details class="filter-bar-collapsible" open>
    <summary class="filter-summary">🔧 Filters · all {total_count} items</summary>
    <div class="filter-bar">
        <div class="filter-row row-class">
            <span class="label">Class:</span>
            <div class="dropdown">
                <select id="class-dropdown">
                    {class_options_html}
                </select>
            </div>
        </div>
        <div class="filter-row row-role">
            <span class="label">Role:</span>
            {role_html}
        </div>
        <div class="filter-row row-quality">
            <span class="label">Quality:</span>
            <div class="dropdown">
                <select id="quality-dropdown">
                    <option value="">Any quality</option>
                    <option value="2" style="color:#1eff00">Uncommon and above</option>
                    <option value="3" style="color:#0070dd">Rare and above</option>
                    <option value="4" style="color:#a335ee">Epic only</option>
                </select>
            </div>
        </div>
        <div class="filter-row row-buttons">
            <button class="filter-btn apply-btn" id="apply-filters">Apply</button>
            <button class="filter-btn reset-btn" id="reset-filters">Reset</button>
        </div>
        <div class="filter-row row-legend">
            <span class="label">Legend:</span>
            <div class="legend" style="font-size: 0.85rem;">
                {legend_html}
            </div>
        </div>
    </div>
    </details>'''


# ---------------------------------------------------------------------------
# Static head + style block (matches WC's inline CSS verbatim)
# ---------------------------------------------------------------------------

PAGE_CSS = """body { background: #1a1a1a; color: #ddd; padding-bottom: 3rem; }
        .container { max-width: 1100px; }
        h1, h2, h3 { color: #ffd100; }
        a { color: #4ea8de; text-decoration: none; }
        a:hover { color: #88c5f0; }
        .navbar { background: #2d2d2d !important; margin-bottom: 2rem; }
        .navbar-brand {
            font-size: 1.25rem;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .card { background: #232323; border: 1px solid #3a3a3a; margin-bottom: 1.5rem; }
        .card-title { color: #ffd100; margin-bottom: 0.25rem; }
        .boss-meta { color: #777; font-size: 0.85rem; margin-bottom: 1rem; }

        /* Collapsible boss cards. The whole card is a <details> element;
           clicking the summary header toggles the items table below.
           Defaults to open so the page reads exactly like before — the
           collapse is opt-in, useful when scrolling through a dungeon
           with many bosses. The trash section's inner cards inherit
           this behavior since they share render_boss_card.
           Arrow is anchored to the top-right corner of the card via
           absolute positioning so it lines up consistently regardless
           of how long the boss-meta line wraps. */
        .boss-card {
            display: block;  /* override Bootstrap card flex */
            padding: 0;
            position: relative;
        }
        .boss-card > summary {
            cursor: pointer;
            user-select: none;
            list-style: none;
            /* Right padding leaves room for the absolutely-positioned arrow */
            padding: 0.85rem 2.5rem 0.85rem 1rem;
            transition: background 0.15s;
        }
        .boss-card > summary:hover {
            background: rgba(255, 255, 255, 0.02);
        }
        .boss-card > summary::-webkit-details-marker { display: none; }
        .boss-card::after {
            content: '▼';
            position: absolute;
            top: 0.95rem;
            right: 1rem;
            color: #888;
            font-size: 0.95em;
            pointer-events: none;  /* let the click pass through to summary */
            transition: color 0.15s;
        }
        .boss-card[open]::after { content: '▲'; color: #ffd100; }
        /* Title is the only line in summary now — meta moved into content
           so it collapses with the table. No bottom margin needed. */
        .boss-card > summary .card-title { margin-bottom: 0; }
        .boss-card > .boss-card-content {
            padding: 0.5rem 1rem 1rem;
        }
        .boss-card > .boss-card-content .boss-meta {
            margin-top: 0;
            margin-bottom: 0.85rem;
        }
        table.table { color: #ddd; margin-bottom: 0; }
        table.table > :not(caption) > * > * {
            background-color: transparent; color: #ddd;
            border-bottom-color: #3a3a3a; vertical-align: middle;
        }
        table.table > thead {
            color: #999; font-size: 0.78rem;
            text-transform: uppercase; letter-spacing: 0.5px;
        }
        table.table tbody tr:hover { background: #2a2a2a; }

        .filter-bar {
            margin-bottom: 1.5rem; padding: 1rem;
            background: #232323; border: 1px solid #3a3a3a; border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }

        /* Collapsible filter wrapper. The whole <details> sticks to the top
           of the viewport on scroll so users can change filters from
           anywhere on a long dungeon page without scrolling back up.
           Desktop: summary is hidden, content always visible. Mobile:
           closed by default (set by dungeon_filter.js on init), summary
           shown as a single-line summary that toggles the filter content.
           The HTML defaults to <details open> so non-JS users get the
           working default of expanded. */
        .filter-bar-collapsible {
            margin-bottom: 1.5rem;
            position: sticky;
            top: 0;
            z-index: 100;
            background: #1a1a1a;  /* matches body so scrolled content doesn't peek through */
        }
        .filter-bar-collapsible > .filter-bar {
            margin-bottom: 0;  /* details element provides outer spacing */
        }
        .filter-bar-collapsible > summary {
            display: none;  /* hidden on desktop */
            cursor: pointer;
            user-select: none;
            list-style: none;
            padding: 0.7rem 0.9rem;
            background: #232323;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
            color: #ccc;
            font-size: 0.92rem;
        }
        .filter-bar-collapsible > summary::-webkit-details-marker { display: none; }
        .filter-bar-collapsible > summary::after {
            content: ' ▼';
            color: #888;
            float: right;
            font-size: 0.85em;
        }
        .filter-bar-collapsible[open] > summary::after { content: ' ▲'; }
        .filter-bar-collapsible[open] > summary {
            border-radius: 6px 6px 0 0;
            border-bottom: 0;
            margin-bottom: 0;
        }
        .filter-bar-collapsible[open] > .filter-bar {
            border-top-left-radius: 0;
            border-top-right-radius: 0;
        }
        .filter-row {
            display: flex; gap: 8px; flex-wrap: wrap;
            align-items: center; margin-bottom: 8px;
        }
        .filter-row:last-child { margin-bottom: 0; }
        .filter-row > .label { color: #999; font-size: 0.9rem; min-width: 90px; }
        .filter-btn {
            padding: 8px 14px; border-radius: 5px; border: 2px solid #555;
            background: #2a2a2a; color: #ccc; cursor: pointer;
            font-size: 0.85rem; transition: all 0.2s ease;
        }
        .filter-btn:hover { background: #3a3a3a; border-color: #777; }
        .filter-btn.active {
            background: #ffd100; color: #1a1a1a; border-color: #ffd100;
            font-weight: 600;
        }
        /* Apply / Reset buttons. Visually identical across all pages
           (Find Loot tab on index.html uses the same .reset-btn spec).
           Apply is the primary action (brand yellow); Reset is destructive
           but stays subtle so it doesn't shout for attention.
           Override .filter-btn padding/border so these read as polished
           action buttons rather than the chunky role-toggle base style.
           Apply is hidden on desktop — the filter bar is always visible
           there so collapsing-via-Apply isn't useful — and only shown
           inside the mobile @media block below. */
        .filter-btn.apply-btn {
            display: none;
            margin-left: 10px; padding: 6px 14px;
            background: #ffd100; color: #1a1a1a;
            border: 1px solid #ffd100; border-radius: 4px;
            font-size: 0.85rem; font-weight: 600;
        }
        .filter-btn.apply-btn:hover { background: #ffe14d; border-color: #ffe14d; }
        .filter-btn.reset-btn {
            margin-left: 10px; padding: 6px 14px;
            background: #4a1818; color: #ff9b9b;
            border: 1px solid #6a2828; border-radius: 4px;
            font-size: 0.85rem;
        }
        .filter-btn.reset-btn:hover { background: #6a2828; border-color: #6a2828; }

        /* Expand all / Collapse all controls — sit between the filter
           bar and the first boss card so they're always reachable. */
        .expand-controls {
            display: flex; gap: 0.5rem; flex-wrap: wrap;
            margin: 0 0 1rem 0;
        }
        .expand-controls .expand-btn {
            padding: 6px 12px; background: #2d2d2d; color: #ccc;
            border: 1px solid #3a3a3a; border-radius: 4px;
            cursor: pointer; font-size: 0.85rem;
            transition: color 0.1s ease, border-color 0.1s ease;
        }
        .expand-controls .expand-btn:hover {
            color: #ffd100; border-color: #ffd100;
        }

        .dropdown { position: relative; display: inline-block; }
        .dropdown select {
            padding: 8px 12px; background: #2a2a2a; color: #ccc;
            border: 2px solid #555; border-radius: 5px; font-size: 0.85rem;
            min-width: 150px;
        }

        .role-pill {
            display: inline-block; padding: 2px 7px; border-radius: 4px;
            font-size: 0.75rem; margin-right: 3px; cursor: default;
            font-weight: 600;
        }
        .class-pill {
            display: inline-block; width: 18px; height: 18px;
            line-height: 18px; text-align: center; border-radius: 3px;
            font-size: 0.7rem; font-weight: 700;
            color: #1a1a1a; margin-right: 2px; cursor: default;
        }
        .pill-empty {
            color: #555; font-size: 1rem; font-weight: 400; cursor: default;
        }

        .no-loot { color: #777; font-style: italic; text-align: center; padding: 1rem; }
        .stat-text { color: #4ea8de; font-size: 0.85rem; }
        .slot-text { color: #bbb; font-size: 0.85rem; }

        /* Notable trash collapsible — secondary content, visually quieter */
        .trash-section {
            margin-top: 1.5rem;
            border-top: 1px solid #333;
            padding-top: 1rem;
        }
        .trash-section > summary {
            cursor: pointer;
            font-size: 1.1rem;
            font-weight: 600;
            color: #ddd;
            padding: 0.5rem 0;
            list-style: none;
            user-select: none;
        }
        .trash-section > summary::-webkit-details-marker { display: none; }
        .trash-section > summary::before {
            content: '▶';
            display: inline-block;
            margin-right: 8px;
            color: #888;
            transition: transform 0.15s ease;
        }
        .trash-section[open] > summary::before { transform: rotate(90deg); }
        .trash-section > summary:hover { color: #ffd100; }
        .trash-section .trash-count { color: #888; font-weight: normal; font-size: 0.95rem; }
        .trash-section .trash-blurb {
            color: #999; font-size: 0.85rem; font-style: italic;
            margin: 0.5rem 0 1rem 1.5rem;
        }

        /* Sortable headers (sortable.js wires up clicks) */
        th.sortable {
            cursor: pointer;
            user-select: none;
            transition: color 0.1s ease;
            white-space: nowrap;  /* keep header text + indicator on one line */
        }
        th.sortable:hover { color: #ffd100; }
        th.sortable::after {
            content: ' ⇅';
            color: #444;
            font-size: 0.75em;
            margin-left: 4px;
        }
        th.sortable.sort-asc::after  { content: ' ▲'; color: #ffd100; }
        th.sortable.sort-desc::after { content: ' ▼'; color: #ffd100; }

        /* ============================================================
           Mobile (≤600px): boss-card tables become labeled cards.
           Mirrors the Find Loot card pattern for consistency.
           Column order: 1=ITEM 2=SLOT 3=STATS 4=ROLES 5=CLASSES 6=ILVL 7=DROP
           ============================================================ */
        @media (max-width: 600px) {
            body { font-size: 0.92rem; }
            .container { padding: 0 0.5rem; }

            h1 { font-size: 1.5rem; }
            h2 { font-size: 1.2rem; }
            .summary-block { padding: 0.7rem 0.8rem; font-size: 0.88rem; }

            /* Filter bar: each row stacks (label on top, controls below).
               Role buttons go into a 2-col grid for a uniform look — when
               there's an odd count (we have 5 roles) the last button spans
               both columns so nothing is stranded as a half-width cell.
               Class/Quality/Reset stack vertically as full-width controls. */
            /* Filter bar layout. Each row gets a named class (.row-class,
               .row-role, .row-quality, .row-buttons, .row-legend) for
               targeted styling. HTML order is the visual order on mobile:
               Class → Role → Quality → Apply/Reset → Legend. */
            .filter-bar { padding: 0.75rem; }

            /* Collapsible summary visible on mobile only */
            .filter-bar-collapsible > summary {
                display: block;
            }

            .filter-row {
                flex-direction: column;
                align-items: stretch;
                gap: 6px;
                margin-bottom: 12px;
            }
            .filter-row > .label {
                min-width: 0 !important;
                font-size: 0.85rem;
                margin-bottom: 0;
                /* Override inline margin-left:18px on the Quality label */
                margin-left: 0 !important;
            }

            /* Class & Quality dropdown rows: full-width selects */
            .filter-row.row-class .dropdown,
            .filter-row.row-quality .dropdown {
                width: 100%;
            }
            .filter-row.row-class select,
            .filter-row.row-quality select {
                width: 100%;
                font-size: 0.9rem;
                padding: 8px 10px;
            }

            /* Role row: 2-col button grid, label spans full width.
               5 buttons total — the lone last one (odd-position) spans
               both cols so nothing is stranded as a half-width cell. */
            .filter-row.row-role {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 6px;
                align-items: stretch;
            }
            .filter-row.row-role > .label {
                grid-column: 1 / -1;
            }
            .filter-row.row-role > .filter-btn {
                font-size: 0.82rem;
                padding: 8px 10px;
                margin: 0;
            }
            .filter-row.row-role > .filter-btn:last-child:nth-child(odd) {
                grid-column: 1 / -1;
            }

            /* Apply + Reset row: side-by-side 50/50 split with Apply on
               the left. Apply is hidden on desktop (display:none on the
               base rule); on mobile we show it and stretch both buttons
               to share the row evenly. */
            .filter-row.row-buttons {
                flex-direction: row;
                gap: 6px;
            }
            .filter-row.row-buttons .filter-btn.apply-btn {
                display: block;
            }
            .filter-row.row-buttons .filter-btn.apply-btn,
            .filter-row.row-buttons .filter-btn.reset-btn {
                flex: 1 1 0;
                margin-left: 0;
                padding: 10px;
            }

            /* Legend: pills wrap naturally, just make text smaller. Each
               entry is a .legend-item that holds the pill + name together
               so multi-word classes (e.g. Death Knight) never split. */
            .filter-row.row-legend .legend {
                font-size: 0.8rem !important;
                line-height: 1.7;
            }
            .filter-row.row-legend .legend-item {
                white-space: nowrap;
                display: inline-block;
                margin-right: 8px;
            }

            /* Boss cards: tighter, full-width. Padding lives on summary
               and content children (the card is a <details>). */
            .boss-card { padding: 0; margin-bottom: 1rem; }
            .boss-card > summary { padding: 0.7rem 0.85rem; }
            .boss-card > .boss-card-content { padding: 0 0.85rem 0.85rem; }
            .boss-card h3 { font-size: 1.1rem; }
            .boss-meta { font-size: 0.8rem; }

            /* Table → card list. Sortable headers don't help on mobile
               since each row is a card with labeled fields. */
            .boss-card table,
            .boss-card thead,
            .boss-card tbody,
            .boss-card tr,
            .boss-card td { display: block; width: 100%; }
            .boss-card thead { display: none; }

            .boss-card tbody tr {
                background: #232323; border: 1px solid #2d2d2d;
                border-radius: 6px;
                padding: 0.65rem 0.85rem;
                margin-bottom: 0.5rem;
            }

            .boss-card tbody tr td {
                padding: 4px 0; border: 0;
                font-size: 0.85rem; line-height: 1.5;
            }
            .boss-card tbody tr td::before {
                display: block;
                color: #777; font-size: 0.7rem;
                text-transform: uppercase; letter-spacing: 0.5px;
                margin-bottom: 2px;
            }
            .boss-card tbody tr td:nth-child(2)::before { content: 'Slot'; }
            .boss-card tbody tr td:nth-child(3)::before { content: 'Stats'; }
            .boss-card tbody tr td:nth-child(4)::before { content: 'Roles'; }
            .boss-card tbody tr td:nth-child(5)::before { content: 'Classes'; }
            .boss-card tbody tr td:nth-child(6)::before { content: 'iLvl'; }
            .boss-card tbody tr td:nth-child(7)::before { content: 'Drop'; }

            /* Stats list: inline with spacing */
            .boss-card .stat-text {
                font-size: 0.82rem;
            }
            .boss-card .role-pill, .boss-card .class-pill {
                margin: 0 2px 2px 0; vertical-align: middle;
            }

            /* Item name as full-width header */
            .boss-card tbody tr td:nth-child(1) {
                font-size: 0.95rem; font-weight: 600;
                margin-bottom: 6px; padding: 0 0 6px 0;
                border-bottom: 1px solid #2d2d2d;
            }
            .boss-card tbody tr td:nth-child(1)::before { content: none; }

            /* Inline label/value for short fields: Slot, iLvl, Drop.
               Override .text-end which would right-align the value. */
            .boss-card tbody tr td:nth-child(2),
            .boss-card tbody tr td:nth-child(6),
            .boss-card tbody tr td:nth-child(7) {
                display: flex; gap: 12px;
                align-items: baseline;
                font-size: 0.82rem;
                text-align: left !important;
            }
            .boss-card tbody tr td:nth-child(2)::before,
            .boss-card tbody tr td:nth-child(6)::before,
            .boss-card tbody tr td:nth-child(7)::before {
                display: inline-block; margin-bottom: 0;
            }

            /* Trash section: tighten */
            .trash-section > summary { font-size: 1rem; }
            .trash-section .trash-blurb {
                margin: 0.5rem 0 0.75rem 1.25rem;
            }
        }"""


# ---------------------------------------------------------------------------
# Top-level page assembly
# ---------------------------------------------------------------------------

def render_dungeon_page(dungeon_cfg, items, bosses_for_page=None, item_sets=None):
    """Produce the full HTML string for one dungeon page.

    `bosses_for_page`: optional dict {boss_id: boss_meta} from the JSON's
    top-level bosses list. If provided, no-loot bosses get placeholder cards
    instead of being silently dropped.

    `item_sets`: optional resolved set dict (from fetch_item_sets) used to
    render the gear-set callout in the loot summary with items + bonuses.
    """
    item_sets = item_sets or {}
    title = dungeon_cfg['title']
    emoji = dungeon_cfg.get('emoji', '')
    flavour = dungeon_cfg.get('flavour', '')
    summary = dungeon_cfg.get('summary')

    # Group items by bossId
    by_boss = collections.defaultdict(list)
    for it in items:
        by_boss[it['bossId']].append(it)

    # Compute role/class counts (across ALL items in the dungeon)
    role_counts = {r: 0 for r in ALL_ROLES}
    class_counts = {c: 0 for c in ALL_CLASSES}
    for it in items:
        for r in (it.get('roles') or []):
            if r in role_counts:
                role_counts[r] += 1
        for c in (it.get('classes') or []):
            if c in class_counts:
                class_counts[c] += 1

    # Render boss cards in YAML order — emit a placeholder card for no-loot bosses
    boss_cards = []
    bosses_with_no_loot = []
    bosses_for_page = bosses_for_page or {}
    for boss_cfg in dungeon_cfg.get('bosses', []):
        bid = boss_cfg['id']
        boss_items = by_boss.get(bid, [])
        boss_meta = bosses_for_page.get(bid)

        if not boss_items:
            bosses_with_no_loot.append(boss_cfg['name'])
            # Only emit a placeholder if we have boss_meta (i.e. the boss was
            # confirmed in the DB). If neither items nor meta, skip silently.
            if not boss_meta:
                continue

        boss_cards.append(render_boss_card(boss_cfg, boss_items, boss_meta))

    # Auto-discovered "notable trash" — creatures (not in YAML) that drop set
    # pieces and were pulled in by build_dungeons.py's discover_set_piece_droppers.
    # Each shows up in bosses_for_page with source='trash'. We collect them here
    # and render in a collapsible section at the bottom of the page so they
    # don't clutter the main boss list while still being discoverable.
    trash_cards = []
    config_boss_ids = {b['id'] for b in dungeon_cfg.get('bosses', [])}
    for bid, meta in bosses_for_page.items():
        if meta.get('source') != 'trash':
            continue
        if bid in config_boss_ids:
            continue  # belt-and-braces: shouldn't happen, but skip if it does
        trash_items = by_boss.get(bid, [])
        if not trash_items:
            continue  # nothing to show
        # Synthesise a minimal cfg dict for render_boss_card. The 'notable_trash'
        # type triggers the 🗡️ marker that's already in the renderer.
        trash_cfg = {
            'id':   bid,
            'name': meta.get('name', f'Creature {bid}'),
            'type': 'notable_trash',
        }
        trash_cards.append(render_boss_card(trash_cfg, trash_items, meta))

    # Resolve full data for every gear set with at least one piece in
    # this dungeon. Prefer the resolved item_sets dict (has item names
    # and bonus text); fall back to itemsets.json for name-only when
    # running without the resolved data.
    set_ids = sorted({it.get('setId') for it in items if it.get('setId')})
    set_data = []
    for sid in set_ids:
        resolved = item_sets.get(sid) or item_sets.get(str(sid))
        if resolved:
            set_data.append(resolved)
            continue
        # Fallback: name only from raw itemsets.json
        raw = ITEM_SETS.get(str(sid)) or ITEM_SETS.get(sid)
        if raw and raw.get('name'):
            set_data.append({'name': raw['name'], 'items': [], 'bonuses': []})

    summary_html = render_summary_block(summary, set_data=set_data)
    filter_bar_html = render_filter_bar(len(items), role_counts, class_counts)
    boss_cards_html = '\n'.join(boss_cards)
    # Trash section: collapsed by default since it's secondary content.
    # The summary line shows the count so players know there's more without
    # opening it. Inside, cards render with the existing 🗡️ trash marker.
    if trash_cards:
        trash_section_html = f'''
<details class="trash-section">
    <summary>🗡️ Trash drops <span class="trash-count">({len(trash_cards)} mobs)</span></summary>
    <p class="trash-blurb">Trash mobs you encounter clearing the dungeon —
       set pieces, world drops, and miscellaneous gear from non-boss
       creatures. They respawn, so multiple kills per run are possible.</p>
    {chr(10).join(trash_cards)}
</details>'''
    else:
        trash_section_html = ''

    # Italic flavour quote — match WC's wrapping ("...")
    flavour_html = ''
    if flavour:
        flavour_html = (f'    <p class="mb-3" style="color:#bbb; font-style:italic;">'
                        f'"{esc(flavour)}"</p>\n')

    # Inline-SVG favicon using the dungeon's emoji (matches index.html's
    # 💎 pattern; browsers render the emoji glyph directly via the system
    # emoji font). Falls back to ⚔️ when no emoji is set in YAML.
    fav_emoji = emoji or '⚔️'
    favicon = (
        f'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 '
        f'viewBox=%220 0 100 100%22>'
        f'<text y=%22.9em%22 font-size=%2290%22>{fav_emoji}</text></svg>'
    )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(title)} — KCraft</title>
    <link rel="icon" href="{favicon}">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
    <style>
        {PAGE_CSS}
    </style>
</head>
<body>

<nav class="navbar navbar-dark">
    <div class="container">
        <a class="navbar-brand fw-bold" href="index.html" style="color: #ffd100;">⚔️ KCraft</a>
    </div>
</nav>

<div class="container">
    <p class="mb-2"><a href="index.html">← All dungeons</a></p>

    <h1>{esc(emoji)} {esc(title)}</h1>
{flavour_html}
{summary_html}

{filter_bar_html}

    <div class="expand-controls">
        <button class="expand-btn" id="expand-all">▼ Expand all</button>
        <button class="expand-btn" id="collapse-all">▲ Collapse all</button>
    </div>

{boss_cards_html}

{trash_section_html}

</div>

<script src="tooltip.js"></script>
<script src="smart_filter_block.js"></script>
<script src="kcraft_pills.js"></script>
<script src="dungeon_filter.js"></script>
<script src="sortable.js"></script>

</body>
</html>
''', bosses_with_no_loot


# ---------------------------------------------------------------------------
# Public API: build all pages
# ---------------------------------------------------------------------------

def build_pages(config, all_items, out_dir, bosses=None, item_sets=None):
    """Render every dungeon in config to {out_dir}/{slug}.html

    `bosses` (optional): the top-level "bosses" list from loot-data.json. When
    provided, no-loot bosses get rendered as placeholder cards instead of being
    silently dropped.

    `item_sets` (optional): {set_id: {name, items:[{id,name}], bonuses:[{pieces,text}]}}
    as produced by fetch_item_sets() in build_dungeons. Drives the gear-set
    note in the loot summary. Falls back to {} when not supplied.
    """
    item_sets = item_sets or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Group items by dungeon page
    items_by_page = collections.defaultdict(list)
    for it in all_items:
        items_by_page[it['page']].append(it)

    # Group boss meta by page → {bossId: bossMeta}
    bosses_by_page = collections.defaultdict(dict)
    for b in (bosses or []):
        bosses_by_page[b['page']][b['id']] = b

    print(f"\nBuilding dungeon pages → {out_dir}/")

    written = 0
    for slug, dungeon_cfg in config['dungeons'].items():
        page = dungeon_cfg.get('page', f"{slug}.html")
        items = items_by_page.get(page, [])
        boss_meta_for_page = bosses_by_page.get(page, {})

        if not items and not boss_meta_for_page:
            print(f"  [{slug:<22}] no items or boss meta — skipped")
            continue

        html_str, no_loot = render_dungeon_page(
            dungeon_cfg, items, boss_meta_for_page, item_sets=item_sets)
        out_path = out_dir / page
        out_path.write_text(html_str, encoding='utf-8')

        # Count cards we actually rendered (either with loot or as placeholders)
        n_cards = sum(
            1 for b in dungeon_cfg.get('bosses', [])
            if b['id'] in {it['bossId'] for it in items} or b['id'] in boss_meta_for_page
        )
        print(f"  [{slug:<22}] {n_cards} cards, {len(items):>3} items"
              f" → {page} ({out_path.stat().st_size:,} bytes)"
              + (f" [{len(no_loot)} no-loot placeholder(s)]" if no_loot else ''))
        written += 1

    print(f"\n✓ Wrote {written} dungeon pages to {out_dir}/")
    return written


# ---------------------------------------------------------------------------
# Standalone CLI: regenerate pages from an existing loot-data.json
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default='build_config.yaml',
                    help='Path to build_config.yaml (default: build_config.yaml)')
    ap.add_argument('--json',   default='loot-data.json',
                    help='Path to loot-data.json (default: loot-data.json)')
    ap.add_argument('--out-dir', default='.',
                    help='Where to write {slug}.html files (default: cwd)')
    args = ap.parse_args()

    config_path = Path(args.config)
    json_path = Path(args.json)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    if not json_path.exists():
        sys.exit(f"Loot data not found: {json_path}\n"
                 f"  Run build_dungeons.py first to produce it.")

    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    data   = json.loads(json_path.read_text(encoding='utf-8'))

    build_pages(config, data['items'], args.out_dir,
                bosses=data.get('bosses'),
                item_sets=data.get('itemSets'))


if __name__ == '__main__':
    main()
