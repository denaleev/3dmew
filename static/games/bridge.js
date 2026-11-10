/* Мур-мост: нарисуй линию, чтобы клубок докатился до котика. */
'use strict';
(() => {
const {INK} = Mya;
const WW = 360, WH = 600, BR = 14;
// p — платформы [x,y,w,h], s — шипы [x,y,w], m — движущиеся блоки [x,y,w,h,dx,dy,период], st — звёзды, ink — запас чернил
const LEVELS = [
  {b: [60, 60], c: [305, 392], p: [[250, 420, 110, 180]], s: [], m: [], st: [[120, 230], [180, 300], [240, 360]], ink: 420},
  {b: [300, 60], c: [55, 422], p: [[0, 450, 110, 150]], s: [[110, 600, 250]], m: [], st: [[250, 200], [180, 300], [110, 380]], ink: 400},
  {b: [180, 50], c: [310, 472], p: [[130, 250, 100, 30], [260, 500, 100, 100]], s: [[0, 600, 260]], m: [], st: [[90, 250], [150, 380], [240, 440]], ink: 430},
  {b: [50, 50], c: [310, 172], p: [[260, 200, 100, 20]], s: [[0, 600, 360]], m: [], st: [[120, 140], [200, 165], [235, 180]], ink: 330},
  {b: [60, 50], c: [315, 492], p: [[270, 520, 90, 80]], s: [[0, 600, 270]], m: [[140, 300, 80, 18, 100, 0, 3]], st: [[110, 200], [180, 330], [260, 430]], ink: 450},
  {b: [300, 40], c: [305, 492], p: [[0, 260, 150, 20], [250, 520, 110, 80]], s: [[0, 600, 250]], m: [], st: [[220, 150], [80, 240], [200, 420]], ink: 520},
  {b: [50, 60], c: [300, 552], p: [[170, 200, 20, 400], [220, 580, 140, 20]], s: [[0, 600, 170]], m: [], st: [[110, 170], [180, 160], [260, 400]], ink: 380},
  {b: [60, 60], c: [300, 302], p: [[250, 330, 110, 20]], s: [[0, 600, 360]], m: [], st: [[130, 190], [200, 250], [270, 300]], ink: 270},
  {b: [180, 40], c: [50, 512], p: [[0, 540, 100, 60]], s: [[100, 600, 260]], m: [[120, 220, 120, 18, 0, 80, 2.4]], st: [[250, 200], [200, 380], [120, 470]], ink: 430},
  {b: [320, 40], c: [310, 552], p: [[120, 180, 240, 16], [0, 360, 240, 16], [260, 580, 100, 20]], s: [[0, 600, 260]], m: [], st: [[60, 170], [300, 330], [150, 470]], ink: 520},
  {b: [40, 40], c: [320, 252], p: [[280, 280, 80, 20]], s: [[100, 420, 180], [0, 600, 360]], m: [[120, 330, 90, 16, 120, 0, 2]], st: [[100, 200], [200, 240], [255, 262]], ink: 340},
  {b: [180, 30], c: [180, 532], p: [[100, 300, 20, 300], [240, 300, 20, 300], [140, 560, 80, 40], [150, 180, 60, 16]], s: [[0, 600, 100], [260, 600, 100]], m: [], st: [[90, 200], [270, 200], [180, 420]], ink: 430},
];
const KEYMAP = {Space: 'GO', Enter: 'GO', Backspace: 'UNDO', KeyZ: 'UNDO', Delete: 'CLR'};
const starsMap = () => Mya.store.get('bridge.stars', {});
const totalStars = () => Object.values(starsMap()).reduce((a, b) => a + b, 0);
const unlocked = () => Math.min(LEVELS.length, Mya.store.get('bridge.open', 1));
const lvlName = n => `Мир ${Math.floor((n - 1) / 4) + 1}-${(n - 1) % 4 + 1}`;

Mya.games.bridge = {
  id: 'bridge', title: 'Мур-мост', touchOnly: false,
  modes: [{id: 'levels', name: 'Уровни', desc: 'Нарисуй линию пальцем или мышкой и нажми «Пуск». Клубок должен докатиться до котика. Чернил мало, шипы колются, блоки двигаются!'}],
  controls: [{k: 'GO', l: '▶ Пуск', wide: true}, {k: 'UNDO', l: '↶ Линия', wide: true}, {k: 'CLR', l: '🗑 Стереть', wide: true}],
  keys: 'Рисуй мышкой · Пробел — пуск/заново · Z — убрать последнюю линию · Delete — стереть всё',
  hint: 'Можно рисовать и пока клубок катится. Собери все 3 звезды на уровне!',
  recordText() { return `⭐ ${totalStars()} / ${LEVELS.length * 3}`; },
  subText() { return lvlName(unlocked()); },
  extra() {
    const sm = starsMap(), cur = Mya.store.get('bridge.lvl', unlocked()), open = unlocked();
    return `<div class="modes">${LEVELS.map((_, i) => { const n = i + 1, ok = n <= open;
      return `<button class="chip ${n === cur ? 'on' : ''}" ${ok ? '' : 'disabled style="opacity:.45"'} onclick="Mya.store.set('bridge.lvl',${n});this.parentNode.querySelectorAll('.chip').forEach(b=>b.classList.remove('on'));this.classList.add('on')">${ok ? n : '🔒'}<small>${ok ? ' ' + '★'.repeat(sm[n] || 0) : ''}</small></button>`; }).join('')}</div>`;
  },
  create(api) { return new Bridge(api); },
};

function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy;
  let t = l ? ((px - ax) * dx + (py - ay) * dy) / l : 0; t = Math.max(0, Math.min(1, t));
  const qx = ax + t * dx, qy = ay + t * dy; return [Math.hypot(px - qx, py - qy), qx, qy];
}
const rectSegs = ([x, y, w, h]) => [[x, y, x + w, y], [x + w, y, x + w, y + h], [x + w, y + h, x, y + h], [x, y + h, x, y]];

class Bridge {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0; this.lines = []; this.linesLvl = 0;
    this.down = e => { const p = this.world(e); if (!p || !this.L) return; this.stroke = [p]; this.cv.setPointerCapture && this.cv.setPointerCapture(e.pointerId); };
    this.move = e => {
      if (!this.stroke) return; const p = this.world(e), q = this.stroke[this.stroke.length - 1];
      const d = Math.hypot(p[0] - q[0], p[1] - q[1]); if (d < 6) return;
      if (this.inkLeft() - d < 0) return;
      this.stroke.push(p);
    };
    this.up = () => { if (this.stroke && this.stroke.length > 1) { this.lines.push(this.stroke); this.api.beep('rot'); } this.stroke = null; if (!this.api.running) this.draw(this.cv.getContext('2d')); };
    this.cv.addEventListener('pointerdown', this.down); this.cv.addEventListener('pointermove', this.move);
    this.cv.addEventListener('pointerup', this.up); this.cv.addEventListener('pointercancel', this.up);
    this.reset();
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.down); this.cv.removeEventListener('pointermove', this.move); this.cv.removeEventListener('pointerup', this.up); this.cv.removeEventListener('pointercancel', this.up); }
  resize(W, H) { this.W = W; this.H = H; this.k = Math.min(W / WW, H / WH); this.ox = (W - WW * this.k) / 2; this.oy = (H - WH * this.k) / 2; }
  world(e) { const r = this.cv.getBoundingClientRect(); return [(e.clientX - r.left - this.ox) / this.k, (e.clientY - r.top - this.oy) / this.k]; }
  inkMax() { return this.L.ink * {kid: 1.6, player: 1, pro: .78}[this.api.diff]; }
  inkUsed() { let s = 0; for (const l of this.lines.concat(this.stroke ? [this.stroke] : [])) for (let i = 1; i < l.length; i++) s += Math.hypot(l[i][0] - l[i - 1][0], l[i][1] - l[i - 1][1]); return s; }
  inkLeft() { return this.inkMax() - this.inkUsed(); }
  reset() {
    this.n = Math.min(Mya.store.get('bridge.lvl', unlocked()), unlocked());
    this.L = LEVELS[this.n - 1];
    if (this.linesLvl !== this.n) { this.lines = []; this.linesLvl = this.n; }
    this.stroke = null; this.t = 0; this.done = false;
    this.ballReset();
    this.hud();
  }
  ballReset() {
    this.ball = {x: this.L.b[0], y: this.L.b[1], vx: 0, vy: 0, a: 0}; this.rolling = false; this.still = 0;
    this.got = new Set(); this.t = 0;
  }
  hud() { this.api.hud(lvlName(this.n), '⭐'.repeat(this.got ? this.got.size : 0) + '☆'.repeat(3 - (this.got ? this.got.size : 0))); }
  key(code, down) {
    if (!down) return; const k = KEYMAP[code] || code;
    if (k === 'GO') { if (this.rolling) this.ballReset(); else { this.rolling = true; this.api.beep('jump'); } this.hud(); }
    if (k === 'UNDO') { this.lines.pop(); }
    if (k === 'CLR') { this.lines = []; this.ballReset(); this.hud(); }
  }
  movers() { return this.L.m.map(([x, y, w, h, dx, dy, per]) => { const s = Math.sin(this.t * 2 * Math.PI / per), c = Math.cos(this.t * 2 * Math.PI / per) * 2 * Math.PI / per; return {r: [x + dx * (s + 1) / 2, y + dy * (s + 1) / 2, w, h], vx: dx / 2 * c, vy: dy / 2 * c}; }); }
  update(dt) {
    if (this.done) return;
    this.t += dt;
    if (!this.rolling) return;
    const b = this.ball, N = 8, h = dt / N;
    const statics = [];
    for (const l of this.lines) for (let i = 1; i < l.length; i++) statics.push([l[i - 1][0], l[i - 1][1], l[i][0], l[i][1], 4, 0, 0]);
    for (const r of this.L.p) for (const s of rectSegs(r)) statics.push([...s, 0, 0, 0]);
    for (let it = 0; it < N; it++) {
      const segs = statics.concat(...this.movers().map(m => rectSegs(m.r).map(s => [...s, 0, m.vx, m.vy])));
      b.vy += 900 * h; b.x += b.vx * h; b.y += b.vy * h;
      for (const [ax, ay, bx, by, th, mvx, mvy] of segs) {
        const [d, qx, qy] = segDist(b.x, b.y, ax, ay, bx, by), R = BR + th / 2;
        if (d < R && d > 1e-6) {
          const nx = (b.x - qx) / d, ny = (b.y - qy) / d; b.x += nx * (R - d); b.y += ny * (R - d);
          const rvx = b.vx - mvx, rvy = b.vy - mvy, vn = rvx * nx + rvy * ny;
          if (vn < 0) { b.vx -= 1.25 * vn * nx; b.vy -= 1.25 * vn * ny; b.vx *= .9995; b.vy *= .9995; }
        }
      }
    }
    b.a += b.vx * dt / BR;
    this.L.st.forEach(([sx, sy], i) => { if (!this.got.has(i) && Math.hypot(b.x - sx, b.y - sy) < BR + 14) { this.got.add(i); this.api.beep('star'); this.hud(); } });
    if (Math.hypot(b.x - this.L.c[0], b.y - this.L.c[1]) < BR + 30) return this.win();
    for (const [sx, sy, sw] of this.L.s) if (b.x > sx - BR * .5 && b.x < sx + sw + BR * .5 && b.y + BR > sy - 16 && b.y - BR < sy) return this.fail('Ай! Клубок укололся о шипы.');
    if (b.y > WH + 60 || b.x < -60 || b.x > WW + 60) return this.fail('Клубок укатился за край.');
    this.still = Math.hypot(b.vx, b.vy) < 8 ? this.still + dt : 0;
    if (this.still > 2.2) return this.fail('Клубок застрял. Дорисуй горку или сотри лишнее!');
  }
  win() {
    this.done = true; this.api.beep('win');
    const sm = starsMap(), got = this.got.size; sm[this.n] = Math.max(sm[this.n] || 0, got); Mya.store.set('bridge.stars', sm);
    if (this.n >= unlocked() && this.n < LEVELS.length) Mya.store.set('bridge.open', this.n + 1);
    this.api.challenge('stars', totalStars());
    const last = this.n >= LEVELS.length;
    this.api.over({title: last ? 'ВСЕ УРОВНИ ПРОЙДЕНЫ!' : 'МУР! ДОКАТИЛСЯ!', big: '⭐'.repeat(got) + '☆'.repeat(3 - got),
      text: got < 3 ? 'Попробуй собрать все звёзды — нарисуй линию через них.' : 'Все звёзды собраны! Ты мастер мостов.',
      next: last ? null : () => { Mya.store.set('bridge.lvl', this.n + 1); }, again: 'Переиграть'});
  }
  fail(msg) { this.done = true; this.api.beep('hit'); this.api.over({title: 'ОЙ!', text: msg + ' Линии сохранены — можно поправить.', again: 'Ещё раз'}); }
  draw(g) {
    const {W, H, k, ox, oy} = this; if (!W) return;
    g.clearRect(0, 0, W, H);
    g.save(); g.translate(ox, oy); g.scale(k, k);
    const bg = g.createLinearGradient(0, 0, 0, WH); bg.addColorStop(0, '#ffb35c'); bg.addColorStop(1, '#ff7ac6');
    Mya.rrect(g, 0, 0, WW, WH, 18, bg, INK, 4);
    g.save(); g.beginPath(); g.roundRect ? g.roundRect(0, 0, WW, WH, 18) : g.rect(0, 0, WW, WH); g.clip();
    for (const [x, y, w, hh] of this.L.p) { Mya.rrect(g, x, y, w, hh, 6, '#a64dff', INK, 4); g.fillStyle = '#9dff4a'; g.fillRect(x + 2, y + 1, w - 4, 6); }
    for (const [sx, sy, sw] of this.L.s) {
      g.beginPath(); g.moveTo(sx, sy); for (let x = sx; x < sx + sw - 1; x += 18) { g.lineTo(x + 9, sy - 18); g.lineTo(Math.min(x + 18, sx + sw), sy); }
      g.closePath(); g.fillStyle = '#fff'; g.fill(); g.lineWidth = 3; g.strokeStyle = INK; g.stroke();
    }
    for (const m of this.movers()) { const [x, y, w, hh] = m.r; Mya.rrect(g, x, y, w, hh, 7, '#22e0d0', INK, 4); }
    this.L.st.forEach(([sx, sy], i) => { if (!this.got.has(i)) star(g, sx, sy, 13); });
    const cat = Mya.catImg(); if (cat.complete) g.drawImage(cat, this.L.c[0] - 36, this.L.c[1] - 40, 72, 72);
    g.lineCap = 'round'; g.lineJoin = 'round';
    for (const l of this.lines.concat(this.stroke ? [this.stroke] : [])) {
      g.beginPath(); l.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
      g.lineWidth = 9; g.strokeStyle = INK; g.stroke(); g.lineWidth = 4.5; g.strokeStyle = '#ffd23f'; g.stroke();
    }
    // клубок
    const b = this.ball;
    g.save(); g.translate(b.x, b.y); g.rotate(b.a);
    g.beginPath(); g.arc(0, 0, BR, 0, 7); g.fillStyle = '#ff4fa3'; g.fill(); g.lineWidth = 3.5; g.strokeStyle = INK; g.stroke();
    g.beginPath(); g.moveTo(-10, -6); g.quadraticCurveTo(0, 0, 11, -7); g.moveTo(-12, 3); g.quadraticCurveTo(0, 9, 12, 2); g.moveTo(-6, 10); g.quadraticCurveTo(3, 12, 8, 9);
    g.lineWidth = 2; g.strokeStyle = '#ffffffbb'; g.stroke(); g.restore();
    g.restore();
    // чернила
    const frac = Math.max(0, this.inkLeft() / this.inkMax());
    Mya.rrect(g, 60, 14, 240, 22, 11, '#fff', INK, 3); Mya.rrect(g, 63, 17, Math.max(0, 234 * frac), 16, 8, frac > .25 ? INK : '#ff2e88');
    Mya.text(g, `Чернила: ${Math.round(frac * 100)}%`, 180, 50, 15);
    if (!this.rolling && !this.done && this.api.running) Mya.text(g, this.lines.length ? 'Готово? Жми «▶ Пуск»' : 'Нарисуй линию для клубка ✏️', 180, 120, 18, '#fff');
    g.restore();
  }
}
function star(g, x, y, r) {
  g.beginPath();
  for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * .45 : r; g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
  g.closePath(); g.fillStyle = '#ffd23f'; g.fill(); g.lineWidth = 2.5; g.strokeStyle = INK; g.stroke();
}
})();
