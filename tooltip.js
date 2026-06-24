/**
 * KCraft tooltip — shared in-game style item tooltip.
 *
 * Used by armoury.html, index.html (Find Loot tab), and dungeon pages.
 *
 * Usage:
 *   1. Include this script in your page:
 *        <script src="tooltip.js"></script>
 *
 *   2. On any element you want to show a tooltip for, set:
 *        data-item-id="123"
 *        data-item-json='{"id":123, "name":"...", "color":"#0070dd", ...}'
 *
 *   The script auto-attaches body-level mouse/touch listeners on load and
 *   shows the WoW-style tooltip on hover (desktop) or tap (mobile).
 *
 * Required item fields (all optional except id+name+color):
 *   id, name, color, qualityName, bondingName,
 *   slotFilter (or invType), armorType,
 *   damage (string), stats (array of strings),
 *   maxDurability, durability,
 *   reqLevel (or req),
 *   sellPrice, sellGold, sellSilver, sellCopper
 */
(function() {
  'use strict';

  // ============================================================
  // Styles — injected once on init
  // ============================================================
  const CSS = `
    #kcraft-tooltip {
      position: fixed; z-index: 9999;
      background: #000000; color: #ffffff;
      border: 1px solid #444; border-radius: 3px;
      padding: 8px 12px;
      font-size: 0.82rem; line-height: 1.4;
      min-width: 180px; max-width: 280px;
      pointer-events: none;
      opacity: 0; visibility: hidden;
      transition: opacity 0.08s;
      box-shadow: 0 4px 12px rgba(0,0,0,0.6);
    }
    #kcraft-tooltip.visible { opacity: 1; visibility: visible; }
    #kcraft-tooltip .tt-name {
      font-size: 0.95rem; font-weight: 600; margin-bottom: 2px;
    }
    #kcraft-tooltip .tt-bind { color: #ffffff; font-size: 0.78rem; }
    #kcraft-tooltip .tt-slot-row {
      display: flex; justify-content: space-between; margin-top: 4px;
    }
    #kcraft-tooltip .tt-slot-row .tt-slot { color: #ffffff; }
    #kcraft-tooltip .tt-slot-row .tt-armor-type { color: #ffffff; }
    #kcraft-tooltip .tt-stat { color: #ffffff; }
    #kcraft-tooltip .tt-bonus { color: #1eff00; }
    /* Delta tags shown next to each stat when comparing to equipped gear.
       Green = upgrade, red = downgrade, slightly smaller than the stat line. */
    #kcraft-tooltip .tt-delta-up   { color: #1eff00; font-size: 0.85em; }
    #kcraft-tooltip .tt-delta-down { color: #ff5555; font-size: 0.85em; }
    /* Ghost line for stats present on the compared item but missing here. */
    #kcraft-tooltip .tt-missing    { color: #888; }
    /* Dual-slot (ring/trinket) net-swap line: "<equipped> -> +8 Spi +2 Int".
       Each delta keeps its green/red colour; spaced for readability. */
    #kcraft-tooltip .tt-compare-swap   { margin: 2px 0 2px; font-size: 0.9em; }
    #kcraft-tooltip .tt-compare-swap .tt-delta-up,
    #kcraft-tooltip .tt-compare-swap .tt-delta-down { font-size: 1em; margin-right: 7px; }
    #kcraft-tooltip .tt-compare-same   { color: #888; font-size: 0.85em; }
    /* Zero-delta tag (grey) — used where alignment matters. */
    #kcraft-tooltip .tt-delta-zero { color: #888; font-size: 0.85em; }
    /* "replacing <name>" sub-header above a dual-slot swap panel's deltas. */
    #kcraft-tooltip .tt-swap-sub { color: #888; font-size: 0.8em; font-style: italic; margin-bottom: 1px; }

    /* Action-button band (e.g. "Find on AH"). Inline-block so multiple
       buttons can sit side by side; stopPropagation in onclick keeps
       the click from triggering the tap-to-close handler. */
    #kcraft-tooltip .tt-actions {
        margin-top: 12px;
        padding-top: 10px;
        border-top: 1px dashed #3a3a3a;
        display: flex; flex-wrap: wrap; gap: 6px;
    }
    #kcraft-tooltip .tt-action-btn {
        background: #2d4a2d; color: #b8e8b8;
        border: 1px solid #3d5a3d; border-radius: 4px;
        padding: 5px 12px; font-size: 0.82rem; font-weight: 600;
        cursor: pointer; text-decoration: none; display: inline-block;
    }
    #kcraft-tooltip .tt-action-btn:hover { background: #3d5a3d; color: #fff; }
    #kcraft-tooltip .tt-damage-row {
      display: flex; justify-content: space-between; margin-top: 2px;
    }
    #kcraft-tooltip .tt-damage-row .tt-damage  { color: #ffffff; }
    #kcraft-tooltip .tt-damage-row .tt-speed   { color: #ffffff; }
    #kcraft-tooltip .tt-dps {
      color: #ffffff; font-size: 0.8rem; margin-left: 4px;
    }
    #kcraft-tooltip .tt-effect {
      color: #1eff00; margin-top: 4px; line-height: 1.3;
    }
    #kcraft-tooltip .tt-durability { color: #ffffff; margin-top: 4px; }
    /* Class restriction ("Classes: Mage") — red like the in-game tooltip so
       a wrong-class buy stands out before you click Confirm. */
    #kcraft-tooltip .tt-classes { color: #ff2020; margin-top: 4px; }
    #kcraft-tooltip .tt-required { color: #ffffff; margin-top: 4px; }
    #kcraft-tooltip .tt-sell {
      margin-top: 4px;
      display: flex; gap: 6px; align-items: center;
    }
    #kcraft-tooltip .tt-sell-label { color: #ffffff; }
    #kcraft-tooltip .tt-coin {
      display: inline-flex; align-items: center; gap: 2px;
      font-variant-numeric: tabular-nums;
    }
    #kcraft-tooltip .tt-coin-icon {
      display: inline-block; width: 11px; height: 11px;
      border-radius: 50%; border: 1px solid rgba(0,0,0,0.4);
    }
    #kcraft-tooltip .tt-coin-gold .tt-coin-icon   { background: #ffd700; }
    #kcraft-tooltip .tt-coin-silver .tt-coin-icon { background: #c8c8c8; }
    #kcraft-tooltip .tt-coin-copper .tt-coin-icon { background: #c97a36; }
    #kcraft-tooltip .tt-id {
      color: #555; font-size: 0.7rem; margin-top: 4px;
      border-top: 1px solid #1f1f1f; padding-top: 4px;
    }
    /* Item set block — yellow set name, dim grey piece list, green bonuses,
       matching the in-game tooltip styling shown to players. */
    #kcraft-tooltip .tt-set-heading {
      color: #ffd100; margin-top: 6px; font-weight: 600;
    }
    #kcraft-tooltip .tt-set-piece {
      color: #888; padding-left: 6px; line-height: 1.3;
    }
    #kcraft-tooltip .tt-set-bonus {
      color: #1eff00; line-height: 1.3; margin-top: 1px;
    }
    #kcraft-tooltip .tt-set-bonus .tt-set-pieces { color: #888; }
    [data-item-id].tooltip-active { outline: 1px solid #555; outline-offset: -1px; }

    /* Mobile: narrower, smaller font, never go off-edge */
    @media (max-width: 600px) {
      #kcraft-tooltip {
        max-width: calc(100vw - 24px);
        min-width: 0;
        font-size: 0.78rem;
        padding: 6px 10px;
      }
      #kcraft-tooltip .tt-name { font-size: 0.88rem; }
    }

    /* Modal mode (small viewports): the tooltip fills the entire viewport
       so it's easy to read on phones. Tapping anywhere on it dismisses
       and returns the user to the item list (the tap-handler in tooltip.js
       handles this). Scrolling within long tooltips still works thanks
       to the 10px movement threshold that distinguishes tap from scroll. */
    #kcraft-tooltip.tt-modal {
      position: fixed;
      inset: 0;
      left: 0 !important;
      top: 0 !important;
      transform: none;
      width: 100vw;
      height: 100vh;
      max-width: none;
      max-height: none;
      border-radius: 0;
      padding: 20px 16px;
      overflow-y: auto;
      pointer-events: auto;
      z-index: 10001;
      cursor: pointer;
    }
    #kcraft-tooltip.tt-modal::after {
      /* Subtle hint: tells the user how to get back. Sticky so it stays
         visible while they scroll long set-bonus lists. */
      content: '✕ Tap anywhere to close';
      display: block;
      position: sticky;
      bottom: -20px;
      margin-top: 16px;
      padding: 8px;
      text-align: center;
      color: #666;
      font-size: 0.75rem;
      background: rgba(20, 20, 20, 0.9);
      border-top: 1px solid #333;
    }

    .tt-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      z-index: 10000;
      display: none;
    }
    .tt-backdrop.visible { display: block; }
  `;

  // ============================================================
  // Helpers
  // ============================================================
  function escape(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Resolve WoW spell-formula placeholders like ${21/-10} (which the game
  // client evaluates at runtime). Set bonuses and equip effects often contain
  // them in raw form. We compute |result| rounded to the nearest integer —
  // descriptions like "X less rage" or "X additional rage" use positive
  // magnitudes regardless of the formula's sign convention. If the inner
  // expression contains anything other than digits/decimals/+-*/()/space the
  // placeholder is left as-is (defensive against arbitrary $vars).
  function resolveFormulas(text) {
    if (!text || typeof text !== 'string') return text;
    return text.replace(/\$\{([^}]+)\}/g, (match, expr) => {
      if (!/^[\d+\-*/(). ]+$/.test(expr)) return match;
      try {
        const v = Function('return (' + expr + ')')();
        if (typeof v !== 'number' || !isFinite(v)) return match;
        return String(Math.round(Math.abs(v)));
      } catch (e) {
        return match;
      }
    });
  }

  // Parse a stat line like "+5 Stamina" or "+1019 Armor" → {name, value}.
  // Used by the comparison-delta logic. Returns null if the format isn't
  // recognized (e.g. weapon damage strings, descriptive lines).
  function parseStatLine(s) {
    const m = String(s || '').match(/^([+-]?\d+)\s+(.+)$/);
    if (!m) return null;
    return { value: parseInt(m[1], 10), name: m[2].trim() };
  }

  // Effect-line rating extractors — mirror of armoury.html RATING_EXTRACTORS.
  // KEEP IN SYNC. Used so secondary stats that render as Equip-effect lines
  // ("Equip: Increases spell power by 8.", "...your critical strike rating
  // by 12.") get a +/- delta tag next to them, matching the primary-stat
  // delta tags. Pattern + canonical-name pair; first match wins per line.
  const EFFECT_RATING_EXTRACTORS = [
    ['Defense',         /defense rating by (\d+)/i],
    ['Dodge',           /dodge rating by (\d+)/i],
    ['Parry',           /parry rating by (\d+)/i],
    ['Block',           /block rating .* by (\d+)/i],
    ['Block Value',     /block value of your shield by (\d+)/i],
    ['Hit',             /hit rating by (\d+)/i],
    ['Critical Strike', /critical strike rating by (\d+)/i],
    ['Haste',           /haste rating by (\d+)/i],
    ['Expertise',       /expertise rating by (\d+)/i],
    ['Resilience',      /resilience rating by (\d+)/i],
    ['Armor Pen',       /armor penetration rating by (\d+)/i],
    ['Spell Power',     /(?:spell power|damage and healing) (?:done )?by (?:up to )?(\d+)/i],
    ['Attack Power',    /attack power by (\d+)/i],
    ['MP5',             /(\d+)\s*mana\s+(?:per|every)\s+5\s+sec/i],
  ];
  // Returns {ratingName: value} for an item's effects, or {} if none match.
  // Values are SUMMED across effect lines, not first-wins: a normal item has
  // at most one line per rating so the sum == that one value, but the virtual
  // "Main Hand + Off Hand" combine item (combineWeaponItemsForCompare in
  // armoury.html) concatenates BOTH weapons' Equip effects — so a 2H candidate
  // must baseline against MH+OH spell power summed (9 + 12 = 21), not just the
  // main hand's 9. First-wins was silently dropping the off-hand's contribution.
  function extractEffectRatings(item) {
    const out = {};
    for (const e of ((item && item.effects) || [])) {
      if (e.trigger && e.trigger !== 'Equip') continue;   // Use:/Chance: don't have steady stats
      const t = e.text || '';
      for (const [name, re] of EFFECT_RATING_EXTRACTORS) {
        const m = re.exec(t);
        if (m) out[name] = (out[name] || 0) + parseInt(m[1], 10);
      }
    }
    return out;
  }

  function statIndexOf(item) {
    const idx = {};
    (item && item.stats || []).forEach(s => {
      const p = parseStatLine(s);
      // SUM same-named lines, don't overwrite: an item can carry a stat on both
      // its base and a random suffix ("+8 Intellect" base + "+2 Intellect" of
      // the Owl) = 10 total. Overwriting kept only the last (2), corrupting the
      // delta. Single-stat items are unaffected (one line per name).
      if (p) idx[p.name] = (idx[p.name] || 0) + p.value;
    });
    // Fold in effect-line rating stats so deltas span both the primary stat
    // block AND Equip-effect lines. Stats from effects use the same name
    // namespace (Spell Power, Hit, Crit, etc.) — no collision with primary
    // stat names (Strength, Stamina, Intellect, etc.).
    const ratings = extractEffectRatings(item);
    for (const k of Object.keys(ratings)) idx[k] = ratings[k];
    return idx;
  }

  // Render a small "(+5)" or "(-3)" tag if there's a delta vs compareIdx.
  // Empty string when stat is identical to the comparison baseline.
  function deltaTag(name, value, compareIdx) {
    if (!compareIdx) return '';
    const other = compareIdx[name] || 0;
    const delta = value - other;
    if (delta === 0) return '';
    const cls  = delta > 0 ? 'tt-delta-up' : 'tt-delta-down';
    const sign = delta > 0 ? '+' : '';
    return ` <span class="${cls}">(${sign}${delta})</span>`;
  }

  // One-line NET stat change if `candidate` replaced THIS specific equipped
  // piece. Used for dual-slot items (rings/trinkets) so the player can weigh
  // "swap Finger 1" vs "swap Finger 2" directly — each finger shows its own
  // outcome. Gains (green) listed first, then losses (red). statIndexOf folds
  // in Equip-effect ratings, so Spell Power / MP5 are included. Returns a
  // "no change" line when the swap is a wash.
  // "Finger 1" -> "F1", "Trinket 2" -> "T2". Labels dual-slot inline deltas.
  function abbrevSlot(label) {
    if (!label) return '';
    const letter = (String(label).match(/[A-Za-z]/) || ['?'])[0].toUpperCase();
    const num    = (String(label).match(/\d+/) || [''])[0];
    return letter + num;
  }

  // Delta tag(s) for one stat line. `labelled` (dual-slot) -> one tag per
  // baseline, prefixed with its abbreviation ("(F1 -4) (F2 +6)") and showing
  // zero-deltas in grey so the columns align. Unlabelled (single baseline) ->
  // the classic single "(+N)/(-N)", hidden when zero.
  function multiDeltaTag(name, value, baselines, labelled) {
    let out = '';
    baselines.forEach(b => {
      const d = value - (b.idx[name] || 0);
      if (!labelled) {
        if (d === 0) return;
        out += ` <span class="${d > 0 ? 'tt-delta-up' : 'tt-delta-down'}">(${d > 0 ? '+' : ''}${d})</span>`;
      } else {
        const cls = d > 0 ? 'tt-delta-up' : (d < 0 ? 'tt-delta-down' : 'tt-delta-zero');
        out += ` <span class="${cls}">(${b.abbr} ${d > 0 ? '+' : ''}${d})</span>`;
      }
    });
    return out;
  }

  // Choose which equipped item the TOP tooltip's inline (+N)/(-N) deltas
  // compare against, for dual-slot items (rings, trinkets, main/off hand).
  // A new ring replaces ONE of two equipped pieces — whichever swap is the
  // bigger upgrade — so we headline that slot: the equipped item with the
  // greatest net stat gain when swapped for the candidate (i.e. the piece
  // you'd realistically replace). `withItems` are compare entries that
  // actually carry an item (empty slots are excluded by the caller, since an
  // empty slot is pure gain with no baseline to subtract). Returns null when
  // there are none → plain tooltip, no inline deltas.
  function pickInlineBaseline(candidate, withItems) {
    if (!withItems.length) return null;
    const candIdx = statIndexOf(candidate);
    let best = null, bestNet = -Infinity;
    withItems.forEach(c => {
      const eqIdx = statIndexOf(c.item);
      const names = new Set(Object.keys(candIdx).concat(Object.keys(eqIdx)));
      let net = 0;
      names.forEach(n => { net += (candIdx[n] || 0) - (eqIdx[n] || 0); });
      if (net > bestNet) { bestNet = net; best = c.item; }
    });
    return best;
  }

  // Dual-slot (ring/trinket) comparison panel, in the SAME format as a
  // single-slot item: the CANDIDATE's stat lines with "(+N)/(-N)" deltas vs
  // this equipped piece, plus grey "0 X (-N)" ghost lines for stats the
  // candidate lacks that the piece has. One panel per equipped piece, so both
  // swap outcomes show; the slot label above identifies which piece. Any
  // non-stat Equip text on the piece (procs / on-use you'd give up) is listed
  // after, since those aren't captured by the stat deltas. `eq` = equipped
  // piece, `cand` = hovered candidate.
  function buildSwapPanel(eq, cand) {
    if (!eq) return '';
    const baselines = [{ abbr: '', idx: statIndexOf(eq) }];
    let h = `<div class="tt-swap-sub">replacing ${escape(eq.name)}</div>`;
    // Candidate's own stats, each with the standard single-baseline delta.
    (cand.stats || []).forEach(s => {
      const cls = /^[+]/.test(s) ? 'tt-stat tt-bonus' : 'tt-stat';
      const p = parseStatLine(s);
      const d = p ? multiDeltaTag(p.name, p.value, baselines, false) : '';
      h += `<div class="${cls}">${escape(s)}${d}</div>`;
    });
    // Ghost lines: stats the equipped piece has that the candidate lacks.
    const myStats = new Set((cand.stats || []).map(s => {
      const p = parseStatLine(s); return p ? p.name : null;
    }).filter(Boolean));
    Object.keys(extractEffectRatings(cand)).forEach(n => myStats.add(n));
    Object.keys(baselines[0].idx).forEach(name => {
      if (myStats.has(name) || !baselines[0].idx[name]) return;
      h += `<div class="tt-stat tt-missing">0 ${escape(name)}` +
           multiDeltaTag(name, 0, baselines, false) + `</div>`;
    });
    // Non-stat Equip text on the piece you'd give up (procs / on-use).
    (eq.effects || []).forEach(e => {
      const text = e.text || '';
      const isRating = (!e.trigger || e.trigger === 'Equip')
        && EFFECT_RATING_EXTRACTORS.some(([, re]) => re.test(text));
      if (isRating) return;
      const trigger = e.trigger ? `${escape(e.trigger)}: ` : '';
      h += `<div class="tt-effect">${trigger}${escape(resolveFormulas(text))}</div>`;
    });
    return h;
  }

  // Build the in-game style tooltip HTML for an item.
  // `compareTo` is optional. It may be:
  //   - a single equipped item -> each stat line gets one "(+5)/(-3)" delta;
  //   - an array of {item,label} baselines (dual-slot rings/trinkets) -> each
  //     stat line gets one SHORT-LABELLED delta per baseline, "(F1 -4)(F2 +6)",
  //     so both swap outcomes show inline on the candidate's own stats.
  // Used by the Upgrade Finder and AH compare flow.
  function buildTooltipHTML(it, compareTo) {
    const parts = [];
    const cmpArr = !compareTo ? []
      : (Array.isArray(compareTo) ? compareTo : [{ item: compareTo, label: '' }]);
    const baselines = cmpArr.filter(c => c && c.item).map(c => ({
      abbr: abbrevSlot(c.label),
      idx:  statIndexOf(c.item),
    }));
    // Labelled mode when there's >1 baseline or the lone one carries a label.
    const labelled = baselines.length > 1 || !!(baselines[0] && baselines[0].abbr);
    // dps delta only applies to a single equipped-weapon comparison.
    const dpsCmp = (!Array.isArray(compareTo) && compareTo) ? compareTo : null;

    // Name in quality colour
    parts.push(
      `<div class="tt-name" style="color:${escape(it.color || '#fff')}">${escape(it.name)}</div>`
    );

    // Soulbound / BoE / quest line
    if (it.bondingName) {
      parts.push(`<div class="tt-bind">${escape(it.bondingName)}</div>`);
    }
    // Unique / Unique-Equipped — matches in-game tooltip placement.
    // Some items have both flags set; the in-game client typically shows
    // "Unique-Equipped" if present, otherwise "Unique" if MaxCount==1.
    if (it.uniqueEquipped) {
      parts.push(`<div class="tt-bind">Unique-Equipped</div>`);
    } else if (it.unique) {
      parts.push(`<div class="tt-bind">Unique</div>`);
    }

    // Slot ↔ armor type row
    // The loot-data JSON uses `slotFilter` for the bare slot name; the armoury
    // API uses `invType`. Accept either.
    const slot = it.invType || it.slotFilter || '';
    const armorType = it.armorType || '';
    if (slot || armorType) {
      parts.push(
        `<div class="tt-slot-row">` +
          `<span class="tt-slot">${escape(slot)}</span>` +
          `<span class="tt-armor-type">${escape(armorType)}</span>` +
        `</div>`
      );
    }

    // Weapon damage line: "X-Y Damage" with "Speed Z.ZZ" on the right and
    // "(W.W damage per second)" below — matches the in-game tooltip layout.
    if (it.damage) {
      if (it.speed) {
        parts.push(
          `<div class="tt-damage-row">` +
            `<span class="tt-damage">${escape(it.damage)}</span>` +
            `<span class="tt-speed">Speed ${Number(it.speed).toFixed(2)}</span>` +
          `</div>`
        );
        if (it.dps) {
          // DPS delta vs the compared weapon. Weapons aren't in the stat
          // index (statIndexOf only covers stat/effect lines), so compare the
          // raw .dps fields directly. One decimal; ignore sub-0.05 rounding.
          let dpsDelta = '';
          if (dpsCmp && dpsCmp.dps != null) {
            const d = it.dps - dpsCmp.dps;
            if (Math.abs(d) >= 0.05) {
              const cls = d > 0 ? 'tt-delta-up' : 'tt-delta-down';
              dpsDelta = ` <span class="${cls}">(${d > 0 ? '+' : ''}${d.toFixed(1)})</span>`;
            }
          }
          parts.push(
            `<div class="tt-dps">(${Number(it.dps).toFixed(1)} damage per second)${dpsDelta}</div>`
          );
        }
      } else {
        parts.push(`<div class="tt-stat">${escape(it.damage)}</div>`);
      }
    }

    // Stats list — values starting with "+" are highlighted green. When a
    // compareTo item is provided, each line gets a "(+N)" / "(-N)" delta tag.
    (it.stats || []).forEach(s => {
      const isBonus = /^[+]/.test(s);
      const cls = isBonus ? 'tt-stat tt-bonus' : 'tt-stat';
      let delta = '';
      if (baselines.length) {
        const p = parseStatLine(s);
        if (p) delta = multiDeltaTag(p.name, p.value, baselines, labelled);
      }
      parts.push(`<div class="${cls}">${escape(s)}${delta}</div>`);
    });
    // Also surface stats that the COMPARE item has but THIS item lacks.
    // Rendered as a 0-value ghost line with a negative delta — tells the user
    // "you're losing 22 Armor by switching to this", which would otherwise be
    // invisible if you only look at the upgrade item's stats.
    if (baselines.length) {
      const myStats = new Set((it.stats || []).map(s => {
        const p = parseStatLine(s); return p ? p.name : null;
      }).filter(Boolean));
      // Also count stats this item provides via its OWN Equip-effect ratings
      // (crit, hit, spell power...). Otherwise an effect-rating the equipped
      // item also has gets double-counted: a spurious "0 X (-N)" ghost line
      // here AND the correct (+/-N) delta on the effect line below. E.g. a
      // helm with "Equip: crit by 14" vs an equipped "crit by 4" must show
      // ONLY "+10" on the effect line — not also "0 Critical Strike (-4)".
      Object.keys(extractEffectRatings(it)).forEach(n => myStats.add(n));
      // Union across ALL baselines of stats the candidate lacks -> one ghost
      // line each, with a labelled delta per baseline (multi) or a single
      // "(-N)" (single). multiDeltaTag handles both.
      const ghostNames = new Set();
      baselines.forEach(b => Object.keys(b.idx).forEach(n => {
        if (!myStats.has(n)) ghostNames.add(n);
      }));
      ghostNames.forEach(name => {
        parts.push(
          `<div class="tt-stat tt-missing">0 ${escape(name)}` +
            multiDeltaTag(name, 0, baselines, labelled) +
          `</div>`
        );
      });
    }

    // Durability (if present — characters only; loot data omits)
    if (it.maxDurability) {
      const cur = (it.durability != null) ? it.durability : it.maxDurability;
      parts.push(`<div class="tt-durability">Durability ${cur} / ${it.maxDurability}</div>`);
    }

    // Class restriction ("Classes: Mage") — renders red when the item is
    // class-locked. Comes from item_template.AllowableClass resolved into a
    // slug list by armoury_api. Empty list = no restriction = no line. We
    // capitalise the slugs for display ("dk" -> "DK", others -> "Mage").
    if (Array.isArray(it.allowedClasses) && it.allowedClasses.length) {
      const SLUG_DISPLAY = {
        warrior:'Warrior', paladin:'Paladin', hunter:'Hunter', rogue:'Rogue',
        priest:'Priest',   dk:'Death Knight', shaman:'Shaman', mage:'Mage',
        warlock:'Warlock', druid:'Druid',
      };
      const labels = it.allowedClasses.map(s => SLUG_DISPLAY[s] || s).join(', ');
      parts.push(`<div class="tt-classes">Classes: ${escape(labels)}</div>`);
    }

    // Required level. Accept either reqLevel (armoury) or req (loot guide).
    const reqLvl = it.reqLevel || it.req;
    if (reqLvl) {
      parts.push(`<div class="tt-required">Requires Level ${reqLvl}</div>`);
    }

    // Equip: / Use: / Chance on hit: effects (in green, same as in-game).
    // When comparing against an equipped item, each Equip-rating line gets
    // a (+N)/(-N) delta tag — same treatment as primary stat lines, so
    // "Equip: Increases spell power by 8 (+3)" appears when the equipped
    // piece had +5 Spell Power. First-match-wins regex per line.
    (it.effects || []).forEach(e => {
      const trigger = e.trigger ? `${escape(e.trigger)}: ` : '';
      let delta = '';
      if (baselines.length && (!e.trigger || e.trigger === 'Equip')) {
        for (const [name, re] of EFFECT_RATING_EXTRACTORS) {
          const m = re.exec(e.text || '');
          if (m) { delta = multiDeltaTag(name, parseInt(m[1], 10), baselines, labelled); break; }
        }
      }
      parts.push(`<div class="tt-effect">${trigger}${escape(resolveFormulas(e.text))}${delta}</div>`);
    });

    // Item set block — yellow heading "Set Name (n/m)", greyed-out piece list,
    // green bonus lines. Mirrors the in-game set tooltip; we don't know how
    // many pieces the player owns so the heading shows total only ("(5)").
    if (it.set && it.set.name) {
      const s = it.set;
      const pieceCount = (s.items || []).length;
      const heading = pieceCount
        ? `${escape(s.name)} (${pieceCount})`
        : escape(s.name);
      parts.push(`<div class="tt-set-heading">${heading}</div>`);
      (s.items || []).forEach(piece => {
        const name = escape(piece.name || `Item ${piece.id}`);
        parts.push(`<div class="tt-set-piece">${name}</div>`);
      });
      (s.bonuses || []).forEach(b => {
        parts.push(
          `<div class="tt-set-bonus">` +
            `<span class="tt-set-pieces">(${b.pieces}) Set:</span> ` +
            `${escape(resolveFormulas(b.text))}` +
          `</div>`
        );
      });
    }

    // Sell price with coin indicators
    if (it.sellPrice && it.sellPrice > 0) {
      const coins = [];
      if (it.sellGold > 0) coins.push(
        `<span class="tt-coin tt-coin-gold">${it.sellGold}<span class="tt-coin-icon"></span></span>`
      );
      if (it.sellSilver > 0 || it.sellGold > 0) coins.push(
        `<span class="tt-coin tt-coin-silver">${it.sellSilver}<span class="tt-coin-icon"></span></span>`
      );
      coins.push(
        `<span class="tt-coin tt-coin-copper">${it.sellCopper}<span class="tt-coin-icon"></span></span>`
      );
      parts.push(
        `<div class="tt-sell">` +
          `<span class="tt-sell-label">Sell Price:</span>` +
          coins.join('') +
        `</div>`
      );
    }

    // Item ID footer
    if (it.id) {
      parts.push(`<div class="tt-id">Item ID: ${escape(it.id)}</div>`);
    }

    return parts.join('');
  }

  // ============================================================
  // Tooltip element + show/hide/position
  // ============================================================
  let tooltipEl = null;
  let tooltipShownFor = null;

  function getOrCreateTooltipEl() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.getElementById('kcraft-tooltip');
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.id = 'kcraft-tooltip';
      tooltipEl.setAttribute('role', 'tooltip');
      tooltipEl.setAttribute('aria-hidden', 'true');
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  // Mobile = small viewport. Threshold matches the CSS @media breakpoint so
  // visual layout and JS behaviour switch together. Probed each call rather
  // than cached so it tracks orientation changes and viewport resizes.
  const MOBILE_BREAKPOINT = 600;
  function isMobileViewport() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function getOrCreateBackdropEl() {
    let bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) return bd;
    bd = document.createElement('div');
    bd.id = 'kcraft-tooltip-backdrop';
    bd.className = 'tt-backdrop';
    document.body.appendChild(bd);
    return bd;
  }

  function showTooltip(it, ev, row) {
    const el = getOrCreateTooltipEl();
    // Optional comparison block — set window.KCraftTooltip.compareProvider
    // to a function that receives the item and returns an array of
    // { item, label } objects (or a falsy value to skip). Each entry is
    // rendered below the main tooltip, separated by a horizontal rule and
    // labelled (e.g. "Currently equipped"). Used by armoury.html to show
    // the character's gear underneath an auction item for comparison.
    let compares = [];
    const provider = window.KCraftTooltip && window.KCraftTooltip.compareProvider;
    if (typeof provider === 'function') {
      try { compares = provider(it) || []; } catch (e) { compares = []; }
    }
    // Both single- and dual-slot use the same layout: the top tooltip's stat
    // lines get green/red (+N)/(-N) delta tags, and each equipped item is
    // rendered plain (full stats) below. Single-slot baselines the deltas
    // against the one equipped item. Dual-slot items (rings, trinkets,
    // main/off hand) return TWO equipped entries, both shown plain below; the
    // top deltas baseline against the piece the candidate best upgrades (the
    // one you'd realistically replace), so the +/- live only on the top.
    const realCompares = compares.filter(c => c);
    // Inline-delta baseline = the equipped piece the candidate would actually
    // replace. Exclude reference-only slots (e.g. the main hand shown beside an
    // off-hand item or shield — the candidate can't equip there, so it must not
    // drive the deltas). pickInlineBaseline returns the best-swap among real
    // target slots, the lone target, or null (empty target → candidate plain).
    const realTargets = realCompares.filter(c => c.item && !c.reference);
    // Dual-slot (rings/trinkets/1H either-hand): a new piece replaces ONE of
    // two, and which one is the player's call. The candidate renders PLAIN up
    // top; the comparison lives on each EQUIPPED piece's panel below — its own
    // stats/effects annotated with the swap delta (see buildSwapPanel). The
    // slot label identifies the piece, so no F1/F2 shorthand. Single-slot keeps
    // the classic inline delta against the one equipped item.
    const isDualSlot = realTargets.length > 1;
    const baseline = isDualSlot ? null : pickInlineBaseline(it, realTargets);
    let html = buildTooltipHTML(it, baseline);
    realCompares.forEach(cmp => {
      const label = cmp.label || 'Currently equipped';
      html += `<div class="tt-compare-sep"></div>`;
      html += `<div class="tt-compare-label">${escape(label)}</div>`;
      if (cmp.item) {
        // Dual-slot: render the equipped piece with its stats/effects annotated
        // by the swap delta vs the candidate. Single-slot: plain full tooltip.
        const body = isDualSlot ? buildSwapPanel(cmp.item, it) : buildTooltipHTML(cmp.item);
        html += `<div class="tt-compare-body">${body}</div>`;
      } else {
        html += `<div class="tt-compare-empty">(empty)</div>`;
      }
    });
    // Optional action-button band. Set window.KCraftTooltip.actionsHTML
    // to a function that takes the hovered item and returns HTML for
    // buttons rendered beneath the main body (and beneath any compare
    // panels). Used by the Upgrade Finder to inject a "Find on AH" jump
    // button inside the mobile tooltip — where the tooltip IS the
    // comparison view, so a per-row button on the page itself wouldn't
    // be visible.
    if (typeof window.KCraftTooltip.actionsHTML === 'function') {
      try {
        const a = window.KCraftTooltip.actionsHTML(it);
        if (a) html += `<div class="tt-actions">${a}</div>`;
      } catch (e) { /* swallow — actions must never break the tooltip */ }
    }
    el.innerHTML = html;
    el.classList.add('visible');
    el.setAttribute('aria-hidden', 'false');
    positionTooltip(ev);
    if (tooltipShownFor && tooltipShownFor !== row) {
      tooltipShownFor.classList.remove('tooltip-active');
    }
    if (row) row.classList.add('tooltip-active');
    tooltipShownFor = row || null;
  }

  function hideTooltip() {
    const el = getOrCreateTooltipEl();
    el.classList.remove('visible');
    el.classList.remove('tt-modal');
    el.setAttribute('aria-hidden', 'true');
    // Reset inline positioning so a future desktop hover doesn't inherit
    // the centered modal coordinates.
    el.style.left = '';
    el.style.top = '';
    const bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) bd.classList.remove('visible');
    if (tooltipShownFor) tooltipShownFor.classList.remove('tooltip-active');
    tooltipShownFor = null;
  }

  function positionTooltip(ev) {
    const el = getOrCreateTooltipEl();
    if (isMobileViewport()) {
      // Modal mode: tooltip centered, backdrop dims the page. CSS handles
      // the actual centering — this just toggles classes and clears any
      // leftover inline coords from a previous desktop hover.
      el.classList.add('tt-modal');
      el.style.left = '';
      el.style.top = '';
      getOrCreateBackdropEl().classList.add('visible');
      return;
    }
    // Desktop: position next to the cursor with viewport-edge clamping.
    el.classList.remove('tt-modal');
    const bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) bd.classList.remove('visible');
    const pad = 14;
    const tw = el.offsetWidth;
    const th = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    if (x + tw + 8 > vw) x = ev.clientX - tw - pad;
    if (y + th + 8 > vh) y = ev.clientY - th - pad;
    if (x < 4) x = 4;
    if (y < 4) y = 4;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
  }

  // Lookup item data on a row. Returns null if attribute is missing/invalid.
  function readItemFromRow(row) {
    const json = row.dataset && row.dataset.itemJson;
    if (!json) return null;
    try {
      return JSON.parse(json);
    } catch (e) {
      return null;
    }
  }

  // ============================================================
  // Event listeners — body-level delegation, survives re-renders
  // ============================================================
  function setupEventListeners() {
    // Hover (desktop)
    document.body.addEventListener('mouseover', (ev) => {
      // Buttons and form controls are interactive — never tooltip targets.
      if (ev.target.closest('button, input, select, textarea, a')) return;
      const row = ev.target.closest('[data-item-id]');
      if (!row) return;
      if (tooltipShownFor === row) return;
      const data = readItemFromRow(row);
      if (data) showTooltip(data, ev, row);
    });

    document.body.addEventListener('mousemove', (ev) => {
      if (!tooltipShownFor) return;
      positionTooltip(ev);
    });

    document.body.addEventListener('mouseout', (ev) => {
      if (!tooltipShownFor) return;
      const leaving = ev.target.closest('[data-item-id]');
      if (leaving === tooltipShownFor && !leaving.contains(ev.relatedTarget)) {
        hideTooltip();
      }
    });

    // Touch (mobile) — distinguish a tap from a scroll-gesture
    let touchStart = null;
    const TAP_MOVE_THRESHOLD_PX = 10;

    document.body.addEventListener('touchstart', (ev) => {
      if (ev.touches.length !== 1) {
        touchStart = { x: 0, y: 0, isScroll: true };
        return;
      }
      const t = ev.touches[0];
      touchStart = { x: t.clientX, y: t.clientY, isScroll: false };
    }, { passive: true });

    document.body.addEventListener('touchmove', (ev) => {
      if (!touchStart) return;
      const t = ev.touches[0];
      if (!t) return;
      const dx = Math.abs(t.clientX - touchStart.x);
      const dy = Math.abs(t.clientY - touchStart.y);
      if (dx > TAP_MOVE_THRESHOLD_PX || dy > TAP_MOVE_THRESHOLD_PX) {
        touchStart.isScroll = true;
      }
    }, { passive: true });

    document.body.addEventListener('touchend', (ev) => {
      const wasScroll = !touchStart || touchStart.isScroll;
      touchStart = null;
      if (wasScroll) return;

      // Taps on interactive controls let the control handle the event itself.
      if (ev.target.closest('button, input, select, textarea, a')) return;

      const row = ev.target.closest('[data-item-id]');
      if (row) {
        if (tooltipShownFor === row) {
          ev.preventDefault();
          return;
        }
        const data = readItemFromRow(row);
        if (data) {
          const touch = ev.changedTouches[0];
          const fakeEv = { clientX: touch.clientX, clientY: touch.clientY };
          showTooltip(data, fakeEv, row);
          ev.preventDefault();
        }
      } else if (tooltipShownFor) {
        // Tap anywhere — including on the tooltip itself in full-screen
        // modal mode — dismisses and returns to the items. Scrolling
        // inside the tooltip is preserved by the touchmove threshold
        // earlier (a >10px drag flips isScroll=true and we never get
        // here on touchend).
        hideTooltip();
      }
    }, { passive: false });

    // Dismiss on scroll (any kind — programmatic, momentum, container scroll)
    window.addEventListener('scroll', () => {
      if (tooltipShownFor) hideTooltip();
    }, { passive: true, capture: true });
  }

  // ============================================================
  // Init
  // ============================================================
  function injectStyles() {
    if (document.getElementById('kcraft-tooltip-styles')) return;
    const style = document.createElement('style');
    style.id = 'kcraft-tooltip-styles';
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function init() {
    injectStyles();
    getOrCreateTooltipEl();
    setupEventListeners();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for manual control
  window.KCraftTooltip = {
    init: init,
    show: showTooltip,
    hide: hideTooltip,
    buildHTML: buildTooltipHTML,
  };
})();
