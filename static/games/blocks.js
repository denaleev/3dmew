/* Мяу-блоки: падающие фигуры из четырёх блоков. */
'use strict';
(() => {
const {COL, INK} = Mya;
const COLS = 10, ROWS = 20, HID = 2;
const SHAPES = {
  I: {c: COL.c, m: ['....', 'XXXX', '....', '....']},
  O: {c: COL.y, m: ['XX', 'XX']},
  T: {c: COL.v, m: ['.X.', 'XXX', '...']},
  S: {c: COL.l, m: ['.XX', 'XX.', '...']},
  Z: {c: COL.p, m: ['XX.', '.XX', '...']},
  J: {c: COL.b, m: ['X..', 'XXX', '...']},
  L: {c: COL.o, m: ['..X', 'XXX', '...']},
};
// все повороты: список клеток [x, y]
for (const k in SHAPES) {
  const m = SHAPES[k].m, n = m.length, rots = [];
  let cells = []; m.forEach((r, y) => [...r].forEach((ch, x) => ch === 'X' && cells.push([x, y])));
  for (let i = 0; i < 4; i++) { rots.push(cells); cells = cells.map(([x, y]) => [n - 1 - y, x]); }
  SHAPES[k].rots = rots; SHAPES[k].n = n;
}
const KICKS = [[0, 0], [-1, 0], [1, 0], [0, -1], [-2, 0], [2, 0], [0, 1]];
const KEYMAP = {ArrowLeft: 'L', KeyA: 'L', ArrowRight: 'R', KeyD: 'R', ArrowDown: 'D', KeyS: 'D', ArrowUp: 'CW', KeyX: 'CW', KeyW: 'CW',
  KeyZ: 'CCW', ControlLeft: 'CCW', Space: 'HD', KeyC: 'HOLD', ShiftLeft: 'HOLD', ShiftRight: 'HOLD'};
const fmtTime = ms => { const s = ms / 1000; return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`; };
const fmt = n => n.toLocaleString('ru-RU');

Mya.games.blocks = {
  id: 'blocks', title: 'Мяу-блоки',
  modes: [
    {id: 'marathon', name: 'Марафон', desc: 'Каждые 10 линий — новый уровень, фигуры падают быстрее. Каждая линия печатает слой котика!'},
    {id: 'sprint', name: 'Спринт 40', desc: 'Убери 40 линий как можно быстрее. Рекорд — лучшее время.'},
    {id: 'zen', name: 'Дзен', desc: 'Проиграть нельзя: если поле заполнится, котик его почистит. Для спокойной игры.'},
  ],
  controls: [{k: 'HOLD', l: '⇄', aria: 'Отложить'}, {k: 'CCW', l: '↶', aria: 'Повернуть влево'}, {k: 'L', l: '←', aria: 'Влево'}, {k: 'D', l: '↓', aria: 'Вниз'},
    {k: 'R', l: '→', aria: 'Вправо'}, {k: 'CW', l: '↷', aria: 'Повернуть'}, {k: 'HD', l: '⤓', aria: 'Сбросить'}],
  keys: '← → двигать · ↑ или X повернуть · Z повернуть назад · ↓ вниз · Пробел сбросить · C отложить · Esc пауза',
  hint: 'На телефоне: тап по полю — поворот, проведи влево-вправо — сдвиг, резко вниз — сброс, вверх — отложить.',
  recordText(mode) {
    mode = mode || 'marathon'; const r = Mya.record('blocks', mode);
    return !r ? '—' : mode === 'sprint' ? fmtTime(r) : fmt(r);
  },
  subText() { return 'Спринт: ' + this.recordText('sprint'); },
  create(api) { return new Blocks(api); },
};

class Blocks {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0; this.cell = 20;
    this.drag = null;
    this.onDown = e => { if (!api.running) return; this.drag = {x: e.clientX, y: e.clientY, ox: e.clientX, oy: e.clientY, t: performance.now(), moved: false, soft: 0}; };
    this.onMove = e => {
      const d = this.drag; if (!d || !api.running) return; const c = this.cell * .9;
      while (e.clientX - d.x > c) { this.move(1); d.x += c; d.moved = true; }
      while (d.x - e.clientX > c) { this.move(-1); d.x -= c; d.moved = true; }
      if (e.clientY - d.y > c * 1.2 && performance.now() - d.t > 160) { if (this.step()) this.score += 1; d.y += c * 1.2; d.moved = true; d.soft++; }
    };
    this.onUp = e => {
      const d = this.drag; this.drag = null; if (!d || !api.running) return;
      const dx = e.clientX - d.ox, dy = e.clientY - d.oy, dt = performance.now() - d.t;
      if (dy > 70 && dt < 260 && Math.abs(dx) < dy * .6 && !d.soft) this.hardDrop();
      else if (-dy > 60 && Math.abs(dx) < -dy * .7) this.hold();
      else if (!d.moved && Math.abs(dx) < 14 && Math.abs(dy) < 14) this.rotate(1);
    };
    this.cv.addEventListener('pointerdown', this.onDown); this.cv.addEventListener('pointermove', this.onMove);
    this.cv.addEventListener('pointerup', this.onUp); this.cv.addEventListener('pointercancel', () => { this.drag = null; });
    this.reset('marathon');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); this.cv.removeEventListener('pointermove', this.onMove); this.cv.removeEventListener('pointerup', this.onUp); }
  resize(W, H) {
    this.W = W; this.H = H;
    this.cell = Math.floor(Math.min((W - 16) / (COLS + 5.2), (H - 16) / ROWS));
    const bw = this.cell * (COLS + 5.2);
    this.ox = Math.round((W - bw) / 2); this.oy = Math.round((H - this.cell * ROWS) / 2);
  }
  reset(mode) {
    this.mode = mode;
    this.board = Array.from({length: ROWS + HID}, () => Array(COLS).fill(null));
    this.bag = []; this.queue = []; this.holdP = null; this.canHold = true;
    this.score = 0; this.lines = 0; this.combo = -1; this.time = 0; this.pops = []; this.clearing = null;
    this.held = {L: false, R: false, D: false}; this.das = 0; this.dir = 0;
    this.diff = this.api.diff; this.startLvl = this.diff === 'pro' ? 3 : 1;
    this.fallT = 0; this.lockT = 0; this.resets = 0; this.cur = null; this.flash = 0;
    while (this.queue.length < 4) this.queue.push(this.fromBag());
    this.spawn();
    this.hud();
  }
  get level() { return this.startLvl + Math.floor(this.lines / 10); }
  gravity() {
    const lv = this.diff === 'kid' ? Math.min(this.level, 6) : this.level;
    let s = .8 * Math.pow(.84, lv - 1); if (this.diff === 'kid') s *= 1.7;
    return Math.max(.035, s);
  }
  fromBag() { if (!this.bag.length) { this.bag = Object.keys(SHAPES); for (let i = this.bag.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [this.bag[i], this.bag[j]] = [this.bag[j], this.bag[i]]; } } return this.bag.pop(); }
  spawn(type) {
    type = type || this.queue.shift(); if (this.queue.length < 4) this.queue.push(this.fromBag());
    const S = SHAPES[type];
    this.cur = {t: type, r: 0, x: Math.floor((COLS - S.n) / 2), y: type === 'I' ? HID - 1 : HID};
    this.lockT = 0; this.resets = 0; this.fallT = 0;
    if (!this.fits(this.cur.x, this.cur.y, 0)) {
      if (this.mode === 'zen') { this.zenClean(); return; }
      this.cur = null; this.end(false);
    }
  }
  zenClean() {
    for (let y = 0; y < ROWS + HID - 6; y++) this.board[y].fill(null);
    this.pops.push({t: 'Пуф! Котик прибрался 🧹', x: COLS / 2, y: ROWS / 2, a: 1.4});
    this.spawn();
  }
  cells(p, x = p.x, y = p.y, r = p.r) { return SHAPES[p.t].rots[r].map(([a, b]) => [x + a, y + b]); }
  fits(x, y, r, p = this.cur) {
    return this.cells(p, x, y, r).every(([a, b]) => a >= 0 && a < COLS && b < ROWS + HID && (b < 0 || !this.board[b][a]));
  }
  touched() { if (this.cur && !this.fits(this.cur.x, this.cur.y + 1, this.cur.r) && this.resets < 15) { this.lockT = 0; this.resets++; } }
  move(d) {
    if (!this.cur || this.clearing) return false;
    if (this.fits(this.cur.x + d, this.cur.y, this.cur.r)) { this.cur.x += d; this.touched(); this.api.beep('move'); return true; }
    return false;
  }
  rotate(d) {
    if (!this.cur || this.clearing || this.cur.t === 'O') return;
    const r = (this.cur.r + d + 4) % 4;
    for (const [kx, ky] of KICKS) if (this.fits(this.cur.x + kx, this.cur.y + ky, r)) { this.cur.x += kx; this.cur.y += ky; this.cur.r = r; this.touched(); this.api.beep('rot'); return; }
  }
  step() { if (this.cur && this.fits(this.cur.x, this.cur.y + 1, this.cur.r)) { this.cur.y++; return true; } return false; }
  ghostY() { let y = this.cur.y; while (this.fits(this.cur.x, y + 1, this.cur.r)) y++; return y; }
  hardDrop() {
    if (!this.cur || this.clearing) return; const y = this.ghostY(); this.score += 2 * (y - this.cur.y); this.cur.y = y; this.flash = .12; this.lock();
  }
  hold() {
    if (!this.cur || !this.canHold || this.clearing) return;
    const t = this.cur.t; this.canHold = false;
    if (this.holdP) { const h = this.holdP; this.holdP = t; this.spawn(h); } else { this.holdP = t; this.spawn(); }
    this.api.beep('rot');
  }
  lock() {
    const p = this.cur, c = SHAPES[p.t].c;
    let above = true;
    for (const [a, b] of this.cells(p)) { if (b >= 0) this.board[b][a] = c; if (b >= HID) above = false; }
    this.cur = null; this.canHold = true; this.api.beep('drop');
    if (above && this.mode !== 'zen') return this.end(false);
    const full = []; this.board.forEach((r, y) => r.every(Boolean) && full.push(y));
    if (full.length) { this.clearing = {rows: full, t: .22}; this.api.beep('line'); }
    else { this.combo = -1; this.spawn(); }
    this.hud();
  }
  finishClear() {
    const n = this.clearing.rows.length, lvl = this.level;
    for (const y of this.clearing.rows) { this.board.splice(y, 1); this.board.unshift(Array(COLS).fill(null)); }
    this.clearing = null; this.combo++; this.lines += n;
    let pts = [0, 100, 300, 500, 800][n] * lvl; const names = ['', '', 'Двойная!', 'Тройная!', 'МЯУ-ЧЕТВЁРКА!'];
    if (this.combo > 0) { pts += 50 * this.combo * lvl; this.pops.push({t: `КОМБО ×${this.combo + 1}! +${fmt(pts)}`, x: COLS / 2, y: 8, a: 1.3}); }
    else if (n > 1) this.pops.push({t: `${names[n]} +${fmt(pts)}`, x: COLS / 2, y: 8, a: 1.3});
    if (this.board.every(r => r.every(c => !c))) { pts += 2000 * lvl; this.pops.push({t: 'ЧИСТОЕ ПОЛЕ! +' + fmt(2000 * lvl), x: COLS / 2, y: 11, a: 1.6}); }
    this.score += pts;
    if (this.level > lvl) { this.pops.push({t: `УРОВЕНЬ ${this.level}!`, x: COLS / 2, y: 5, a: 1.6}); this.api.beep('win'); }
    this.api.challenge('lines', this.lines);
    if (this.mode === 'sprint' && this.lines >= 40) return this.end(true);
    this.spawn(); this.hud();
  }
  end(won) {
    this.api.hud(...this.hudText());
    if (this.mode === 'sprint') {
      if (won) this.api.over({title: 'ФИНИШ!', big: fmtTime(this.time), score: Math.round(this.time), lowerBetter: true, text: `40 линий за ${fmtTime(this.time)}. Попробуешь быстрее?`});
      else this.api.over({title: 'ПОЛЕ ЗАПОЛНЕНО', big: `${this.lines} / 40`, text: 'Не хватило места. Попробуй ставить фигуры ровнее и держать середину пониже.'});
    } else {
      this.api.over({big: fmt(this.score), score: this.score, text: `Линий: ${this.lines} · Уровень: ${this.level}`});
    }
  }
  hudText() {
    if (this.mode === 'sprint') return ['⏱ ' + fmtTime(this.time), `${this.lines}/40`];
    return ['⭐ ' + fmt(this.score), 'Ур. ' + this.level];
  }
  hud() { this.api.hud(...this.hudText()); }
  key(code, down) {
    const k = KEYMAP[code] || code;
    if (k === 'L' || k === 'R') {
      this.held[k] = down;
      if (down) { this.dir = k === 'L' ? -1 : 1; this.move(this.dir); this.das = 0; }
      else this.dir = this.held.L ? -1 : this.held.R ? 1 : 0;
      return;
    }
    if (k === 'D') { this.held.D = down; return; }
    if (!down) return;
    if (k === 'CW') this.rotate(1); else if (k === 'CCW') this.rotate(-1); else if (k === 'HD') this.hardDrop(); else if (k === 'HOLD') this.hold();
  }
  update(dt) {
    this.time += dt * 1000;
    this.pops.forEach(p => { p.a -= dt; p.y -= dt * 2; }); this.pops = this.pops.filter(p => p.a > 0);
    if (this.flash > 0) this.flash -= dt;
    if (this.clearing) { this.clearing.t -= dt; if (this.clearing.t <= 0) this.finishClear(); if (this.mode === 'sprint') this.hud(); return; }
    if (!this.cur) return;
    if (this.dir) { this.das += dt; if (this.das > .16) { while (this.das > .16 + .045) { this.move(this.dir); this.das -= .045; } } }
    const g = this.held.D ? Math.min(.04, this.gravity() / 8) : this.gravity();
    this.fallT += dt;
    while (this.fallT >= g && this.cur) {
      this.fallT -= g;
      if (this.step()) { if (this.held.D) this.score += 1; } else break;
    }
    if (this.cur && !this.fits(this.cur.x, this.cur.y + 1, this.cur.r)) { this.lockT += dt; if (this.lockT > .5) this.lock(); }
    else this.lockT = 0;
    if (this.mode === 'sprint') this.hud();
  }
  draw(g) {
    const {W, H, cell: s, ox, oy} = this;
    g.clearRect(0, 0, W, H);
    const bw = s * COLS, bh = s * ROWS;
    Mya.rrect(g, ox - 6, oy - 6, bw + 12, bh + 12, 16, '#2b0a3d', INK, 4);
    g.strokeStyle = '#ffffff14'; g.lineWidth = 1;
    for (let x = 1; x < COLS; x++) { g.beginPath(); g.moveTo(ox + x * s, oy); g.lineTo(ox + x * s, oy + bh); g.stroke(); }
    for (let y = 1; y < ROWS; y++) { g.beginPath(); g.moveTo(ox, oy + y * s); g.lineTo(ox + bw, oy + y * s); g.stroke(); }
    for (let y = HID; y < ROWS + HID; y++) for (let x = 0; x < COLS; x++) {
      const c = this.board[y][x]; if (c) Mya.block(g, ox + x * s, oy + (y - HID) * s, s, c);
    }
    if (this.clearing) {
      const a = .5 + .5 * Math.sin(this.clearing.t * 40);
      for (const y of this.clearing.rows) { g.fillStyle = `rgba(255,255,255,${.6 + a * .4})`; g.fillRect(ox, oy + (y - HID) * s, bw, s); }
    }
    if (this.cur) {
      const gy = this.ghostY(), c = SHAPES[this.cur.t].c;
      g.save(); g.setLineDash([5, 4]); g.strokeStyle = '#ffffffaa'; g.lineWidth = 2;
      for (const [a, b] of this.cells(this.cur, this.cur.x, gy)) if (b >= HID) Mya.rrect(g, ox + a * s + 3, oy + (b - HID) * s + 3, s - 6, s - 6, 5, null, '#ffffffaa', 2);
      g.restore();
      for (const [a, b] of this.cells(this.cur)) if (b >= HID) Mya.block(g, ox + a * s, oy + (b - HID) * s, s, c);
    }
    if (this.flash > 0) { g.fillStyle = `rgba(255,255,255,${this.flash * 2})`; g.fillRect(ox, oy, bw, bh); }
    // правая колонка: отложенная, следующие, печать котика
    const px = ox + bw + s * .5, pw = s * 4.6;
    const box = (y, h, label) => { Mya.rrect(g, px, y, pw, h, 14, '#f6e2ff', INK, 3); Mya.text(g, label, px + pw / 2, y + s * .5, Math.max(10, s * .42), '#fff'); };
    const mini = (t, cx, cy, ms) => { const S = SHAPES[t]; const cs = S.rots[0]; const minx = Math.min(...cs.map(c => c[0])), maxx = Math.max(...cs.map(c => c[0])), miny = Math.min(...cs.map(c => c[1])), maxy = Math.max(...cs.map(c => c[1]));
      cs.forEach(([a, b]) => Mya.block(g, cx + (a - (minx + maxx + 1) / 2) * ms, cy + (b - (miny + maxy + 1) / 2) * ms, ms, S.c, t === this.holdP && !this.canHold ? .4 : 1)); };
    box(oy, s * 3, 'ДЕРЖАТЬ'); if (this.holdP) mini(this.holdP, px + pw / 2, oy + s * 1.9, s * .8);
    box(oy + s * 3.4, s * 7.2, 'ДАЛЕЕ'); this.queue.slice(0, 3).forEach((t, i) => mini(t, px + pw / 2, oy + s * (5.4 + i * 2.1), s * (i ? .62 : .8)));
    // печать котика: каждая линия уровня — слой
    const ky = oy + s * 11, kh = s * 5.2;
    Mya.rrect(g, px, ky, pw, kh, 14, '#f6e2ff', INK, 3);
    Mya.text(g, 'ПЕЧАТЬ', px + pw / 2, ky + s * .5, Math.max(10, s * .42), '#fff');
    const im = Mya.catImg(), sz = Math.min(pw - s * .6, kh - s * 1.4), ix = px + (pw - sz) / 2, iy = ky + s * 1.05;
    if (im.complete) {
      g.save(); g.globalAlpha = .18; g.drawImage(im, ix, iy, sz, sz); g.restore();
      const prog = (this.lines % 10) / 10, ch = sz * prog;
      if (ch > 0) { g.save(); g.beginPath(); g.rect(ix, iy + sz - ch, sz, ch); g.clip(); g.drawImage(im, ix, iy, sz, sz); g.restore(); }
    }
    Mya.text(g, `${this.lines % 10}/10`, px + pw / 2, ky + kh - s * .38, Math.max(10, s * .45), '#ffd23f');
    // всплывающие надписи
    for (const p of this.pops) { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, ox + bw / 2, oy + p.y * s, Math.max(14, Math.min(s * .8, bw / (p.t.length * .55))), '#ffd23f'); g.restore(); }
  }
}
})();
