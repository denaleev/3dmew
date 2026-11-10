/* Мяу-аркада: общая часть. Без рекламы, покупок и сбора данных: всё хранится только в localStorage этого браузера. */
'use strict';
const Mya = (() => {
  const INK = '#2b0a3d';
  const COL = {y: '#ffd23f', o: '#ff9f1c', p: '#ff4fa3', v: '#a64dff', c: '#22e0d0', l: '#9dff4a', b: '#4da6ff'};

  // ---------- хранилище (может быть недоступно в приватном режиме) ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem('mya.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('mya.' + k, JSON.stringify(v)); } catch (e) { /* ничего */ } },
  };
  const record = (game, mode) => store.get(`rec.${game}.${mode}`, 0);
  function saveRecord(game, mode, score, lowerIsBetter) {
    const old = record(game, mode);
    const better = lowerIsBetter ? (!old || score < old) : score > old;
    if (better) store.set(`rec.${game}.${mode}`, score);
    return better;
  }
  const difficulty = () => store.get('diff', 'player'); // kid | player | pro

  // ---------- день и случайность с зерном (для испытаний дня) ----------
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`; };
  function rng(seed) {
    let h = 2166136261; for (const ch of String(seed)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    return () => { h += 0x6D2B79F5; let t = h; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  }

  // ---------- рисунки ----------
  let gid = 0;
  function catSVG(s, back) {
    const i = 'k' + (gid++), O = '#4a1838';
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 200 200"><defs>
<linearGradient id="${i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe98a"/><stop offset=".55" stop-color="#ffd457"/><stop offset="1" stop-color="#ffab2e"/></linearGradient>
<linearGradient id="${i}e" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb35c"/><stop offset="1" stop-color="#ffd8a0"/></linearGradient></defs>
<g stroke="${O}" stroke-width="8" stroke-linejoin="round" stroke-linecap="round">
<path d="M26 104 Q22 50 36 22 Q46 14 58 22 Q76 36 92 54 Z" fill="url(#${i})"/><path d="M174 104 Q178 50 164 22 Q154 14 142 22 Q124 36 108 54 Z" fill="url(#${i})"/>
${back ? '' : `<path d="M40 70 Q40 42 48 34 Q60 40 72 54Z M160 70 Q160 42 152 34 Q140 40 128 54Z" fill="url(#${i}e)" stroke="none"/>`}
<path d="M14 124 Q14 52 100 50 Q186 52 186 124 Q186 186 100 188 Q14 186 14 124Z" fill="url(#${i})"/></g>
<ellipse cx="78" cy="74" rx="34" ry="12" fill="#fff" opacity=".45"/>
<g stroke="#f08a1c" stroke-width="7" stroke-linecap="round" fill="none"><path d="M88 60 v12 M100 58 v14 M112 60 v12"/>
${back ? '<path d="M60 110 q40 -14 80 0 M54 132 q46 -14 92 0 M60 154 q40 -12 80 0" stroke-width="8"/>' : '<path d="M22 118 h16 M20 132 h18 M162 118 h16 M162 132 h18"/>'}</g>
${back ? '' : `<g stroke="${O}" stroke-width="7.5" stroke-linecap="round" fill="none"><path d="M52 116 q16 -18 32 0 M116 116 q16 -18 32 0"/>
<path d="M84 140 q8 10 16 0 q8 10 16 0"/></g><path d="M93 128 q7 -4 14 0 q-3 7 -7 8 q-4 -1 -7 -8z" fill="#ff7a8a" stroke="${O}" stroke-width="4" stroke-linejoin="round"/>
<ellipse cx="48" cy="140" rx="13" ry="8" fill="#ff8a7a" opacity=".55"/><ellipse cx="152" cy="140" rx="13" ry="8" fill="#ff8a7a" opacity=".55"/>`}
</svg>`;
  }
  function spoolSVG(c) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="-60 -60 120 120"><g stroke="${INK}" stroke-width="5">
<ellipse rx="50" ry="21" cy="18" fill="#a64dff"/><rect x="-40" y="-18" width="80" height="36" fill="${c}"/>
<path d="M-40 0h80" stroke="#fff" stroke-width="3" opacity=".5"/><ellipse rx="50" ry="21" cy="-18" fill="#c98aff"/></g><ellipse rx="12" ry="5" cy="-18" fill="${INK}"/></svg>`;
  }
  const imgCache = {};
  function img(key, svg) {
    if (!imgCache[key]) { const im = new Image(); im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); imgCache[key] = im; }
    return imgCache[key];
  }
  const catImg = back => img(back ? 'catb' : 'cat', catSVG(256, back));
  const spoolImg = c => img('sp' + c, spoolSVG(c));

  // скруглённый прямоугольник с обводкой
  function rrect(g, x, y, w, h, r, fill, stroke, lw) {
    g.beginPath(); g.roundRect ? g.roundRect(x, y, w, h, r) : g.rect(x, y, w, h);
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (stroke) { g.lineWidth = lw || 3; g.strokeStyle = stroke; g.stroke(); }
  }
  // блок-«мармеладка»
  function block(g, x, y, s, c, alpha) {
    g.save(); if (alpha != null) g.globalAlpha = alpha;
    rrect(g, x + 1, y + 1, s - 2, s - 2, s * .18, c, INK, Math.max(2, s * .08));
    g.globalAlpha = (alpha == null ? 1 : alpha) * .45; rrect(g, x + s * .16, y + s * .15, s * .55, s * .2, s * .08, '#fff');
    g.globalAlpha = (alpha == null ? 1 : alpha) * .15; rrect(g, x + s * .12, y + s * .74, s * .76, s * .12, s * .06, '#000');
    g.restore();
  }
  function text(g, t, x, y, size, fill, align) {
    g.save(); g.font = `900 ${size}px Rubik, Nunito, sans-serif`; g.textAlign = align || 'center'; g.textBaseline = 'middle';
    g.lineJoin = 'round'; g.lineWidth = Math.max(3, size / 5); g.strokeStyle = INK; g.strokeText(t, x, y);
    g.fillStyle = fill || '#fff'; g.fillText(t, x, y); g.restore();
  }

  // ---------- звук (короткие сигналы, без файлов) ----------
  let actx = null;
  const muted = () => store.get('mute', false);
  function beep(kind) {
    if (muted()) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      const S = {move: [440, .03, 'square', .03], rot: [660, .05, 'square', .04], drop: [180, .08, 'triangle', .12], line: [880, .18, 'triangle', .12],
        eat: [740, .08, 'sine', .12], star: [1046, .1, 'sine', .1], hit: [120, .25, 'sawtooth', .12], win: [784, .35, 'triangle', .14], jump: [520, .08, 'sine', .08]}[kind];
      if (!S) return;
      const [f, d, type, vol] = S, o = actx.createOscillator(), gn = actx.createGain(), t = actx.currentTime;
      o.type = type; o.frequency.setValueAtTime(f, t);
      if (kind === 'line' || kind === 'win') o.frequency.exponentialRampToValueAtTime(f * 1.5, t + d);
      if (kind === 'hit') o.frequency.exponentialRampToValueAtTime(60, t + d);
      gn.gain.setValueAtTime(vol, t); gn.gain.exponentialRampToValueAtTime(.0001, t + d);
      o.connect(gn).connect(actx.destination); o.start(t); o.stop(t + d + .02);
    } catch (e) { /* без звука */ }
  }

  // ---------- общие свайпы ----------
  function swipes(el, cb) {
    let sx = 0, sy = 0, st = 0, on = false;
    el.addEventListener('pointerdown', e => { on = true; sx = e.clientX; sy = e.clientY; st = performance.now(); });
    el.addEventListener('pointerup', e => {
      if (!on) return; on = false;
      const dx = e.clientX - sx, dy = e.clientY - sy, dt = performance.now() - st, m = Math.max(Math.abs(dx), Math.abs(dy));
      if (m < 18) return cb('tap', e, dt);
      cb(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up'), e, dt, m);
    });
    el.addEventListener('pointercancel', () => { on = false; });
  }

  return {INK, COL, store, record, saveRecord, difficulty, today, rng, catSVG, spoolSVG, catImg, spoolImg, rrect, block, text, beep, muted, swipes, games: {}};
})();
