/* =============================================================================
 * KCraft smart filter — single source of truth for class/role filter rules.
 *
 * Loaded into pages via:
 *   <script src="smart_filter_block.js"></script>
 *
 * Exposes the public API (window.KCraftFilter):
 *   - CLASS_ARMOR_FLOOR
 *   - ROLE_CLASSES
 *   - passesClassArmor(item, cls, role)
 *   - classFillsRole(item, cls, role)
 *
 * Used by both:
 *   - index.html (Find Loot tab) — JSON-driven dynamic table
 *   - dungeon_filter.js          — DOM-walking dungeon page filter
 *
 * Both consume the SAME rules from this file, so filter behavior is
 * identical across the site. Edit ONLY this file to change a rule.
 * ============================================================================= */

(function (root) {
    'use strict';

    const CLASS_ARMOR_FLOOR = {
        warrior: ['Plate', 'Mail'],
        paladin: ['Plate', 'Mail'],
        dk:      ['Plate'],
        hunter:  ['Mail', 'Leather'],
        shaman:  ['Mail', 'Leather'],
        rogue:   ['Leather'],
        druid:   ['Leather'],
        priest:  ['Cloth'],
        mage:    ['Cloth'],
        warlock: ['Cloth'],
    };

    const ROLE_CLASSES = {
        '':       ['warrior','paladin','hunter','rogue','priest','dk','shaman','mage','warlock','druid'],
        'tank':   ['warrior','paladin','dk','druid'],
        'heal':   ['priest','paladin','druid','shaman'],
        'melee':  ['warrior','paladin','dk','rogue','druid','shaman'],
        'ranged': ['hunter','mage','warlock','priest','druid','shaman','paladin'],
    };

    // WotLK 3.3.5a proficiency tables — mirror of WEAPON_PROFICIENCY and
    // ARMOR_CLASS_RESTRICTIONS in build_dungeons.py. KEEP IN SYNC. Keys are
    // raw item_template.subclass values; itemClass is 2 (weapon) or 4 (armor).
    const WEAPON_PROFICIENCY = {
        0:  new Set(['warrior','paladin','hunter','rogue','dk','shaman']),               // 1H Axe
        1:  new Set(['warrior','paladin','hunter','dk','shaman']),                        // 2H Axe
        2:  new Set(['warrior','hunter','rogue']),                                        // Bow
        3:  new Set(['warrior','hunter','rogue']),                                        // Gun
        4:  new Set(['warrior','paladin','rogue','priest','dk','shaman','druid']),        // 1H Mace
        5:  new Set(['warrior','paladin','dk','shaman','druid']),                         // 2H Mace
        6:  new Set(['warrior','paladin','hunter','dk','druid']),                         // Polearm
        7:  new Set(['warrior','paladin','hunter','rogue','dk','mage','warlock']),        // 1H Sword
        8:  new Set(['warrior','paladin','hunter','dk']),                                  // 2H Sword
        10: new Set(['warrior','hunter','priest','shaman','mage','warlock','druid']),     // Staff
        13: new Set(['warrior','hunter','rogue','shaman','druid']),                       // Fist
        15: new Set(['warrior','hunter','rogue','priest','shaman','mage','warlock','druid']), // Dagger
        16: new Set(['warrior','rogue']),                                                  // Thrown
        18: new Set(['warrior','hunter','rogue']),                                         // Crossbow
        19: new Set(['priest','mage','warlock']),                                          // Wand
    };

    const ARMOR_CLASS_RESTRICTIONS = {
        6:  new Set(['warrior','paladin','shaman']),  // Shield
        7:  new Set(['paladin']),                      // Libram
        8:  new Set(['druid']),                        // Idol
        9:  new Set(['shaman']),                       // Totem
        10: new Set(['dk']),                           // Sigil
    };

    function passesClassArmor(it, cls, role) {
        const allowed = CLASS_ARMOR_FLOOR[cls];
        if (!allowed) return true;
        const m = (it.slot || '').match(/\((Cloth|Leather|Mail|Plate)\)/);
        if (!m) return true;
        const ARMOR_SLOTS = ['Head','Shoulder','Chest','Wrist','Hands','Waist','Legs','Feet'];
        if (!ARMOR_SLOTS.includes(it.slotFilter)) return true;
        return allowed.includes(m[1]);
    }

    function classFillsRole(it, cls, role) {
        if (!passesClassArmor(it, cls, role)) return false;

        const slot = it.slotFilter;
        const ic = it.slot;
        const stats = (it.stats || []).join(' ');
        const hasStat = (n) => stats.indexOf(n) >= 0;
        const isShield = slot === 'Off-Hand' && /Shield/.test(ic);
        const isPlate = /\(Plate\)/.test(ic);
        const isMail = /\(Mail\)/.test(ic);
        const isLeather = /\(Leather\)/.test(ic);
        const isCloth = /\(Cloth\)/.test(ic);
        const isWeapon = ['One-Hand','Two-Hand','Main Hand','Off-Hand','Ranged','Held','Thrown'].includes(slot);

        // Class proficiency. WEAPON_PROFICIENCY (itemClass=2) and
        // ARMOR_CLASS_RESTRICTIONS (itemClass=4) are the authoritative
        // tables — they carry full WotLK 3.3.5a granularity (1H vs 2H
        // sword, polearm vs staff, etc.). Used when the JSON ships the
        // itemClass + subclass fields.
        //
        // Older JSON without those fields falls through to the legacy
        // slot-based check below (Thrown/Ranged/Shield only). After the
        // user runs build_dungeons.py once with the new code, every item
        // carries the integer fields and the legacy path is unused.
        const sub = it.subclass;
        const icat = it.itemClass;
        if (typeof sub === 'number' && typeof icat === 'number') {
            if (icat === 2 && WEAPON_PROFICIENCY.hasOwnProperty(sub)) {
                if (!WEAPON_PROFICIENCY[sub].has(cls)) return false;
            } else if (icat === 4 && ARMOR_CLASS_RESTRICTIONS.hasOwnProperty(sub)) {
                if (!ARMOR_CLASS_RESTRICTIONS[sub].has(cls)) return false;
            }
        } else if (slot === 'Thrown') {
            if (!['warrior','hunter','rogue'].includes(cls)) return false;
        } else if (slot === 'Ranged') {
            if (it.isWand) {
                if (!['mage','warlock','priest'].includes(cls)) return false;
            } else {
                if (!['warrior','hunter','rogue'].includes(cls)) return false;
            }
        } else if (isShield) {
            if (!['warrior','paladin','shaman'].includes(cls)) return false;
        }

        if (role === 'tank') {
            if (!['warrior','paladin','dk','druid'].includes(cls)) return false;
            if (hasStat('Defense') || hasStat('Dodge') || hasStat('Parry') ||
                hasStat('Block') || hasStat('Resilience')) return true;
            const hasCasterStat = hasStat('Spirit') || hasStat('Spell Power') ||
                                  hasStat('MP5') || hasStat('Intellect');
            if (cls === 'warrior' || cls === 'paladin' || cls === 'dk') {
                if (isShield && !hasCasterStat) return true;
                if (isPlate && !hasCasterStat) return true;
                if (!isWeapon && hasStat('Stamina') && !hasCasterStat) return true;
                if (slot === 'One-Hand' && hasStat('Stamina') && !hasCasterStat) return true;
                if (slot === 'Two-Hand' && hasStat('Stamina') && !hasCasterStat) return true;
                return false;
            }
            if (cls === 'druid') {
                if (isLeather && hasStat('Stamina') && !hasCasterStat) return true;
                return false;
            }
            return false;
        }

        if (role === 'heal') {
            if (!['priest','paladin','druid','shaman'].includes(cls)) return false;
            if (hasStat('Spirit') || hasStat('MP5') || hasStat('Spell Power')) return true;
            if (hasStat('Intellect') && (isCloth || isLeather || isMail)) return true;
            return false;
        }

        if (role === 'melee') {
            if (!['warrior','paladin','dk','rogue','hunter','druid','shaman'].includes(cls)) return false;
            if (cls === 'hunter') return false;
            if (isWeapon && (hasStat('Spirit') || hasStat('Spell Power') || hasStat('MP5'))) return false;
            if (isWeapon && hasStat('Intellect') && !(hasStat('Strength') || hasStat('Agility') || hasStat('Attack Power'))) return false;
            if (cls === 'rogue' || cls === 'druid') {
                if (hasStat('Agility') || hasStat('Attack Power') || hasStat('Armor Pen')) return true;
                if (['One-Hand','Two-Hand','Main Hand'].includes(slot) && !hasStat('Strength')) return true;
                return false;
            }
            if (hasStat('Strength') || hasStat('Attack Power') || hasStat('Armor Pen')) return true;
            if (hasStat('Agility') && cls === 'shaman') return true;
            if (['One-Hand','Two-Hand','Main Hand'].includes(slot)) return true;
            return false;
        }

        if (role === 'ranged') {
            if (cls === 'hunter') {
                if (hasStat('Agility') || hasStat('Attack Power')) return true;
                if (slot === 'Ranged') return true;
                return false;
            }
            if (cls === 'mage' || cls === 'warlock' || cls === 'priest') {
                if (hasStat('Spell Power')) return true;
                if (it.isWand) return true;
                if (hasStat('Intellect')) return true;
                return false;
            }
            if (cls === 'shaman' || cls === 'druid') {
                // Druids blocked from shields at top (no proficiency).
                // Shamans still pass through here — a Spell Power or Int
                // shield IS valid Elemental shaman ranged gear (1H + shield
                // caster setup), so we let it tag as both Heal AND Ranged
                // when the stats fit. Shaman/druid have no wands; their
                // 'Ranged' slot blocked at top ('Relic' isn't 'Ranged').
                if (hasStat('Spell Power')) return true;
                if (hasStat('Intellect') && !hasStat('Spirit')) return true;
                return false;
            }
            return false;
        }

        return false;
    }

    root.KCraftFilter = {
        CLASS_ARMOR_FLOOR: CLASS_ARMOR_FLOOR,
        ROLE_CLASSES: ROLE_CLASSES,
        passesClassArmor: passesClassArmor,
        classFillsRole: classFillsRole,
        computeItemRoles: computeItemRoles,
        computeItemClasses: computeItemClasses,
        VERSION: '2.5.0',
    };

    // -------------------------------------------------------------------
    // Pill-rendering helpers. These wrap classFillsRole to answer the two
    // questions every render path needs:
    //
    //   "Which roles does this item actually fit?"   → computeItemRoles
    //   "Which classes can use it (per role)?"        → computeItemClasses
    //
    // Both Find Loot (runtime) and dungeon pages (kcraft_pills.js) use
    // these to recompute the pill columns from raw item data, replacing
    // whatever was statically generated by build_pages.py at build time.
    // -------------------------------------------------------------------

    function computeItemRoles(item) {
        const allClasses = ROLE_CLASSES[''];
        return ['tank', 'heal', 'melee', 'ranged'].filter(function (role) {
            return allClasses.some(function (cls) {
                return classFillsRole(item, cls, role);
            });
        });
    }

    function computeItemClasses(item, role) {
        const allClasses = ROLE_CLASSES[''];
        if (role) {
            return allClasses.filter(function (cls) {
                return classFillsRole(item, cls, role);
            });
        }
        // No role: classes that pass armor floor AND fill at least one role.
        return allClasses.filter(function (cls) {
            if (!passesClassArmor(item, cls, null)) return false;
            return ['tank', 'heal', 'melee', 'ranged'].some(function (r) {
                return classFillsRole(item, cls, r);
            });
        });
    }

})(typeof window !== 'undefined' ? window : this);
