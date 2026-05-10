/* =============================================================================
 * KCraft pill recomputer — DOM bootstrap for dungeon pages.
 *
 * On page load, walks every <tr class="item-row" data-item-json="...">,
 * parses the raw item data, re-derives the role and class pills via
 * window.KCraftFilter.classFillsRole, and overwrites:
 *
 *   1. The role-pill <td> (column index 3)
 *   2. The class-pill <td> (column index 4)
 *   3. The data-roles attribute (used by dungeon_filter.js for filtering)
 *   4. The data-classes attribute (same)
 *
 * This makes smart_filter_block.js the runtime source of truth for what
 * dungeon-page rows display — even when build_pages.py rendered them
 * with older logic. Future edits to filter rules only need to touch
 * smart_filter_block.js; pages auto-correct on next load.
 *
 * Find Loot doesn't need this — it builds rows dynamically from JSON
 * and already calls classFillsRole at render time.
 *
 * Load order (in each dungeon HTML):
 *   <script src="smart_filter_block.js"></script>   -- defines KCraftFilter
 *   <script src="kcraft_pills.js"></script>         -- THIS file (depends on it)
 *   <script src="dungeon_filter.js"></script>       -- reads data-* after we update them
 *
 * Pill style data must match build_pages.py (ROLE_PILL + class_info.json).
 * If you change colors/letters/glyphs in one place, change them in both.
 * ============================================================================= */

(function () {
    'use strict';

    // --- Pill style data. KEEP IN SYNC with build_pages.py / class_info.json. ---

    const ROLE_PILL = {
        tank:   { bg: '#3a5a7a', fg: '#87ceeb', glyph: '🛡', title: 'Tank' },
        heal:   { bg: '#2d5a3d', fg: '#7ec896', glyph: '+',  title: 'Healer' },
        melee:  { bg: '#7a3a3a', fg: '#e88080', glyph: '⚔',  title: 'Melee DPS' },
        ranged: { bg: '#7a5a2d', fg: '#e8c87e', glyph: '🏹', title: 'Ranged DPS' },
    };

    const ROLE_ORDER = ['tank', 'heal', 'melee', 'ranged'];

    const CLASS_DATA = {
        warrior: { color: '#C79C6E', letter: 'W', name: 'Warrior' },
        paladin: { color: '#F58CBA', letter: 'P', name: 'Paladin' },
        hunter:  { color: '#ABD473', letter: 'H', name: 'Hunter' },
        rogue:   { color: '#FFF569', letter: 'R', name: 'Rogue' },
        priest:  { color: '#FFFFFF', letter: 'P', name: 'Priest' },
        dk:      { color: '#C41F3B', letter: 'K', name: 'Death Knight' },
        shaman:  { color: '#0070DE', letter: 'S', name: 'Shaman' },
        mage:    { color: '#69CCF0', letter: 'M', name: 'Mage' },
        warlock: { color: '#9482C9', letter: 'W', name: 'Warlock' },
        druid:   { color: '#FF7D0A', letter: 'D', name: 'Druid' },
    };

    const CLASS_ORDER = [
        'warrior', 'paladin', 'hunter', 'rogue', 'priest',
        'dk', 'shaman', 'mage', 'warlock', 'druid',
    ];

    const PILL_EMPTY = '<span class="pill-empty">\u2014</span>';

    // --- HTML builders. Match the markup that build_pages.py emits. ---

    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function rolePillsHTML(roles) {
        const set = new Set(roles);
        const pills = ROLE_ORDER.filter(function (r) { return set.has(r); });
        if (!pills.length) return PILL_EMPTY;
        return pills.map(function (r) {
            const d = ROLE_PILL[r];
            return '<span class="role-pill" style="background:' + d.bg +
                   ';color:' + d.fg + ';" title="' + escapeAttr(d.title) +
                   '">' + d.glyph + '</span>';
        }).join('\n                            ');
    }

    function classPillsHTML(classes) {
        const set = new Set(classes);
        const pills = CLASS_ORDER.filter(function (c) { return set.has(c); });
        if (!pills.length) return PILL_EMPTY;
        return pills.map(function (c) {
            const d = CLASS_DATA[c];
            return '<span class="class-pill" style="background:' + d.color +
                   ';" title="' + escapeAttr(d.name) + '">' + d.letter + '</span>';
        }).join('\n                            ');
    }

    // --- Per-row recompute. ---

    function recomputeRow(row, KF) {
        const json = row.getAttribute('data-item-json');
        if (!json) return;

        let item;
        try {
            item = JSON.parse(json);
        } catch (e) {
            // Malformed JSON — leave the static pills alone, log once.
            if (!recomputeRow._warned) {
                console.warn('[kcraft_pills] Could not parse data-item-json:', e);
                recomputeRow._warned = true;
            }
            return;
        }

        const newRoles   = KF.computeItemRoles(item);
        const newClasses = KF.computeItemClasses(item);

        // Update filterable data-* attributes so dungeon_filter.js sees fresh values.
        row.setAttribute('data-roles',   newRoles.join(' '));
        row.setAttribute('data-classes', newClasses.join(' '));

        // Replace the pill <td> cells. Column layout from build_pages.py:
        //   0=name  1=slot  2=stats  3=roles  4=classes  5=ilvl  6=drop
        const tds = row.children;
        if (tds.length >= 5) {
            // Match build_pages.py whitespace for visual diff cleanliness.
            tds[3].innerHTML =
                '\n                            ' + rolePillsHTML(newRoles) +
                '\n                        ';
            tds[4].innerHTML =
                '\n                            ' + classPillsHTML(newClasses) +
                '\n                        ';
        }
    }

    // --- Bootstrap. ---

    function init() {
        const KF = window.KCraftFilter;
        if (!KF || typeof KF.computeItemRoles !== 'function') {
            console.warn(
                '[kcraft_pills] window.KCraftFilter or its compute helpers ' +
                'not found — make sure smart_filter_block.js loads first.'
            );
            return;
        }
        const rows = document.querySelectorAll('tr.item-row[data-item-json]');
        rows.forEach(function (row) { recomputeRow(row, KF); });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
