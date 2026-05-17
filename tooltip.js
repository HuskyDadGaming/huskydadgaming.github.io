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

  function statIndexOf(item) {
    const idx = {};
    (item && item.stats || []).forEach(s => {
      const p = parseStatLine(s);
      if (p) idx[p.name] = p.value;
    });
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

  // Build the in-game style tooltip HTML for an item.
  // `compareTo` is optional. When provided, each primary-stat line gets a
  // small "(+5)" / "(-3)" tag showing the delta vs the compareTo item.
  // Used by the Upgrade Finder and AH compare flow so the hovered candidate
  // shows at-a-glance gains/losses.
  function buildTooltipHTML(it, compareTo) {
    const parts = [];
    const compareIdx = compareTo ? statIndexOf(compareTo) : null;

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
          parts.push(
            `<div class="tt-dps">(${Number(it.dps).toFixed(1)} damage per second)</div>`
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
      if (compareIdx) {
        const p = parseStatLine(s);
        if (p) delta = deltaTag(p.name, p.value, compareIdx);
      }
      parts.push(`<div class="${cls}">${escape(s)}${delta}</div>`);
    });
    // Also surface stats that the COMPARE item has but THIS item lacks.
    // Rendered as a 0-value ghost line with a negative delta — tells the user
    // "you're losing 22 Armor by switching to this", which would otherwise be
    // invisible if you only look at the upgrade item's stats.
    if (compareIdx) {
      const myStats = new Set((it.stats || []).map(s => {
        const p = parseStatLine(s); return p ? p.name : null;
      }).filter(Boolean));
      Object.keys(compareIdx).forEach(name => {
        if (myStats.has(name)) return;
        const otherVal = compareIdx[name];
        if (!otherVal) return;
        const delta = -otherVal;
        const sign = delta > 0 ? '+' : '';
        parts.push(
          `<div class="tt-stat tt-missing">0 ${escape(name)} ` +
            `<span class="tt-delta-down">(${sign}${delta})</span>` +
          `</div>`
        );
      });
    }

    // Durability (if present — characters only; loot data omits)
    if (it.maxDurability) {
      const cur = (it.durability != null) ? it.durability : it.maxDurability;
      parts.push(`<div class="tt-durability">Durability ${cur} / ${it.maxDurability}</div>`);
    }

    // Required level. Accept either reqLevel (armoury) or req (loot guide).
    const reqLvl = it.reqLevel || it.req;
    if (reqLvl) {
      parts.push(`<div class="tt-required">Requires Level ${reqLvl}</div>`);
    }

    // Equip: / Use: / Chance on hit: effects (in green, same as in-game)
    (it.effects || []).forEach(e => {
      const trigger = e.trigger ? `${escape(e.trigger)}: ` : '';
      parts.push(`<div class="tt-effect">${trigger}${escape(resolveFormulas(e.text))}</div>`);
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
    // Use the first compare entry's item (if any) as the delta baseline for
    // the main tooltip — each stat line on the hovered item will show a
    // green/red (+N)/(-N) tag vs that baseline.
    const primary = compares.find(c => c && c.item);
    let html = buildTooltipHTML(it, primary ? primary.item : null);
    compares.forEach(cmp => {
      if (!cmp) return;
      const label = cmp.label || 'Currently equipped';
      html += `<div class="tt-compare-sep"></div>`;
      html += `<div class="tt-compare-label">${escape(label)}</div>`;
      if (cmp.item) {
        // Compare items render plain (no nested deltas).
        html += `<div class="tt-compare-body">${buildTooltipHTML(cmp.item)}</div>`;
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
