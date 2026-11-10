/* Филаментная змейка: собирай катушки, расти и не врезайся. */
'use strict';
(() => {
const {COL, INK} = Mya;
const SPOOLS = [COL.o, COL.p, COL.c];
const DIRS = {U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0]};
const KEYMAP = {ArrowUp: 'U', KeyW: 'U', ArrowDown: 'D', KeyS: 'D', ArrowLeft: 'L', KeyA: 'L', ArrowRight: 'R', KeyD: 'R'};
const lvlName = n => `Мир ${Math.floor((n - 1) / 4) + 1}-${(n - 1) % 4 + 1}`;
const target = n => 6 + n * 2;

Mya.games.snake = {
  id: 'snake', title: 'Филаментная змейка',
  modes: [
    {id: 'levels', name: 'Уровни', desc: 'Собери нужное число катушек, чтобы пройти уровень. Дальше — стены, порталы и скорость.'},
    {id: 'endless', name: 'Бесконечный', desc: 'Расти как можно длиннее. Со временем на поле появляются новые стены.'},
  ],
  controls: [{k: 'L', l: '←'}, {k: 'U', l: '↑'}, {k: 'D', l: '↓'}, {k: 'R', l: '→'}],
  keys: 'Стрелки или WASD — поворот · Esc пауза · 3 катушки одного цвета подряд — очки ×2',
  hint: 'Проводи пальцем по полю в нужную сторону или жми стрелки. Съешь 3 катушки одного цвета подряд — очки ×2!',
  recordText(mode) {
    mode = mode || 'levels'; const r = Mya.record('snake', mode);
    return !r ? '—' : mode === 'levels' ? lvlName(r) : `${r} длина`;
  },
  subText() { return 'Длина: ' + this.recordText('endless'); },
  extra(mode) { return mode === 'levels' ? `<p>Начнёшь с: <b>${lvlName(Mya.store.get('snake.lvl', 1))}</b> <button class="chip" onclick="Mya.store.set('snake.lvl',1);this.parentNode.querySelector('b').textContent='${lvlName(1)}'">с начала</button></p>` : ''; },
  create(api) { return new Snake(api); },
};

class Snake {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    this.sw = (dir) => { if (!api.running) return; const m = {up: 'U', down: 'D', left: 'L', right: 'R'}[dir]; if (m) this.turn(m); };
    Mya.swipes(this.cv, this.sw);
    this.reset('levels');
  }
  resize(W, H) {
    this.W = W; this.H = H;
    this.s = Math.floor(Math.min((W - 12) / this.cols, (H - 12) / this.rows));
    this.ox = Math.round((W - this.s * this.cols) / 2); this.oy = Math.round((H - this.s * this.rows) / 2);
  }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff;
    const wide = this.W > this.H * 1.15; this.cols = wide ? 24 : 15; this.rows = wide ? 15 : 21;
    this.level = mode === 'levels' ? Mya.store.get('snake.lvl', 1) : 1;
    if (mode === 'levels' && this.replay && !this.goNext) this.level = this.replay;
    this.replay = 0; this.goNext = false;
    this.wrap = this.diff === 'kid';
    this.walls = new Set(); this.portals = [];
    if (mode === 'levels') this.buildLevel(this.level);
    const cx = Math.floor(this.cols / 2), cy = Math.floor(this.rows * .7);
    this.body = [[cx, cy], [cx, cy + 1], [cx, cy + 2]].map(([x, y]) => ({x, y, px: x, py: y, c: SPOOLS[0]}));
    this.walls.forEach(k => { const [x, y] = k.split(',').map(Number); if (Math.abs(x - cx) <= 1 && y >= cy - 3) this.walls.delete(k); });
    this.dir = 'U'; this.queue = []; this.items = []; this.eaten = 0; this.score = 0; this.streak = 0; this.lastC = null;
    this.bolt = 0; this.boltItem = null; this.t = 0; this.pops = []; this.dead = false; this.grow = 0;
    for (let i = 0; i < 3; i++) this.addSpool();
    if (this.W) this.resize(this.W, this.H);
    this.hud();
  }
  baseTick() {
    const sp = {kid: .19, player: .13, pro: .095}[this.diff];
    const lvl = this.mode === 'levels' ? this.level : 1 + Math.floor(this.eaten / 6);
    return Math.max(sp * .55, sp * Math.pow(.96, lvl - 1));
  }
  key(code, down) { if (!down) return; const d = KEYMAP[code] || code; if (DIRS[d]) this.turn(d); }
  turn(d) {
    const last = this.queue.length ? this.queue[this.queue.length - 1] : this.dir;
    const [a, b] = DIRS[d], [c, e] = DIRS[last];
    if (d === last || (a === -c && b === -e) || this.queue.length >= 2) return;
    this.queue.push(d);
  }
  k(x, y) { return x + ',' + y; }
  free(x, y) {
    return !this.walls.has(this.k(x, y)) && !this.body.some(p => p.x === x && p.y === y) && !this.items.some(i => i.x === x && i.y === y)
      && !this.portals.some(p => p.x === x && p.y === y) && !(this.boltItem && this.boltItem.x === x && this.boltItem.y === y);
  }
  randFree() { for (let i = 0; i < 400; i++) { const x = Math.floor(Math.random() * this.cols), y = Math.floor(Math.random() * this.rows); if (this.free(x, y)) return [x, y]; } return null; }
  addSpool() {
    const p = this.randFree(); if (!p) return;
    this.items.push({x: p[0], y: p[1], c: SPOOLS[Math.floor(Math.random() * 3)], life: this.diff === 'pro' ? 9 : Infinity});
  }
  buildLevel(n) {
    const C = this.cols, R = this.rows, w = (x, y) => { if (x >= 0 && y >= 0 && x < C && y < R) this.walls.add(this.k(x, y)); };
    const hline = (y, x0, x1) => { for (let x = x0; x <= x1; x++) w(x, y); }, vline = (x, y0, y1) => { for (let y = y0; y <= y1; y++) w(x, y); };
    const kind = (n - 1) % 8, rnd = Mya.rng('snake' + n);
    if (kind === 1) { [[2, 2, 1, 1], [C - 3, 2, -1, 1], [2, R - 3, 1, -1], [C - 3, R - 3, -1, -1]].forEach(([x, y, dx, dy]) => { for (let i = 0; i < 3; i++) { w(x + i * dx, y); w(x, y + i * dy); } }); }
    if (kind === 2) { hline(Math.floor(R / 2), 3, C - 4); this.portals = [{x: 1, y: 1}, {x: C - 2, y: R - 2}]; }
    if (kind === 3) { vline(Math.floor(C / 3), 2, R - 6); vline(Math.floor(2 * C / 3), 5, R - 3); }
    if (kind === 4) { const x0 = 3, x1 = C - 4, y0 = 3, y1 = R - 6; hline(y0, x0, x1); hline(y1, x0, x1); vline(x0, y0, y1); vline(x1, y0, y1);
      const mx = Math.floor(C / 2), my = Math.floor((y0 + y1) / 2); this.walls.delete(this.k(mx, y0)); this.walls.delete(this.k(mx, y1)); this.walls.delete(this.k(x0, my)); this.walls.delete(this.k(x1, my));
      this.portals = [{x: mx, y: my}, {x: 1, y: R - 2}]; }
    if (kind === 5) { const mx = Math.floor(C / 2), my = Math.floor(R / 2) - 2; hline(my, mx - 4, mx + 4); vline(mx, my - 4, my + 4); }
    if (kind >= 6) { const cnt = 10 + n; for (let i = 0; i < cnt; i++) { const x = 1 + Math.floor(rnd() * (C - 2)), y = 1 + Math.floor(rnd() * (R - 6)); w(x, y); if (rnd() < .5) w(x + 1, y); else w(x, y + 1); }
      if (kind === 7) this.portals = [{x: 1, y: Math.floor(R / 3)}, {x: C - 2, y: Math.floor(2 * R / 3)}]; }
  }
  hud() {
    if (this.mode === 'levels') this.api.hud(`🧵 ${this.eaten}/${target(this.level)}`, lvlName(this.level));
    else this.api.hud(`⭐ ${this.score}`, `Длина ${this.body.length}`);
  }
  tick() {
    if (this.queue.length) this.dir = this.queue.shift();
    const [dx, dy] = DIRS[this.dir], h = this.body[0];
    let nx = h.x + dx, ny = h.y + dy;
    if (nx < 0 || ny < 0 || nx >= this.cols || ny >= this.rows) {
      if (!this.wrap) return this.die('Ой! Змейка врезалась в стенку.');
      nx = (nx + this.cols) % this.cols; ny = (ny + this.rows) % this.rows;
    }
    const pi = this.portals.findIndex(p => p.x === nx && p.y === ny);
    if (pi >= 0) { const o = this.portals[1 - pi]; nx = o.x + dx; ny = o.y + dy; nx = (nx + this.cols) % this.cols; ny = (ny + this.rows) % this.rows; this.api.beep('jump'); }
    if (this.walls.has(this.k(nx, ny))) return this.die('Бум! Впереди была стена.');
    const tailWillMove = this.grow === 0;
    if (this.body.some((p, i) => p.x === nx && p.y === ny && !(tailWillMove && i === this.body.length - 1))) return this.die('Змейка запуталась в своём филаменте!');
    this.body.forEach(p => { p.px = p.x; p.py = p.y; });
    // сдвиг тела
    const tail = this.body[this.body.length - 1];
    for (let i = this.body.length - 1; i > 0; i--) { this.body[i].x = this.body[i - 1].x; this.body[i].y = this.body[i - 1].y; }
    h.x = nx; h.y = ny;
    if (this.grow > 0) { this.grow--; this.body.push({x: tail.px, y: tail.py, px: tail.px, py: tail.py, c: this.newC || SPOOLS[0]}); }
    // еда
    const ii = this.items.findIndex(i => i.x === nx && i.y === ny);
    if (ii >= 0) this.eat(this.items.splice(ii, 1)[0]);
    if (this.boltItem && this.boltItem.x === nx && this.boltItem.y === ny) {
      this.boltItem = null; this.bolt = 6; this.api.beep('star'); this.pops.push({t: '⚡ МОЛНИЯ: очки ×3!', x: nx, y: ny, a: 1.4});
    }
  }
  eat(it) {
    this.eaten++; this.grow++; this.newC = it.c;
    this.streak = it.c === this.lastC ? this.streak + 1 : 1; this.lastC = it.c;
    let mult = (this.streak >= 3 ? 2 : 1) * (this.bolt > 0 ? 3 : 1);
    const pts = 10 * mult; this.score += pts;
    if (this.streak === 3) this.pops.push({t: '×2 цвет!', x: it.x, y: it.y, a: 1.2}); else this.pops.push({t: '+' + pts, x: it.x, y: it.y, a: .8});
    this.api.beep('eat');
    this.addSpool();
    if (this.eaten % 8 === 0 && !this.boltItem) { const p = this.randFree(); if (p) this.boltItem = {x: p[0], y: p[1], life: 7}; }
    if (this.mode === 'endless' && this.eaten % 5 === 0) { for (let i = 0; i < 2; i++) { const p = this.randFree(); if (p && Math.hypot(p[0] - it.x, p[1] - it.y) > 4) this.walls.add(this.k(p[0], p[1])); } }
    this.api.challenge('length', this.body.length + this.grow);
    this.hud();
    if (this.mode === 'levels' && this.eaten >= target(this.level)) this.win();
  }
  win() {
    this.dead = true; this.api.beep('win');
    const n = this.level + 1; Mya.store.set('snake.lvl', n);
    Mya.saveRecord('snake', 'levels', n);
    this.api.over({title: 'УРОВЕНЬ ПРОЙДЕН!', big: lvlName(this.level) + ' ✔', text: `Очки: ${this.score}. Дальше — ${lvlName(n)}${(n - 1) % 8 === 1 ? ': появятся стены' : (n - 1) % 8 === 2 ? ': появятся порталы' : ''}.`, next: () => { this.goNext = true; }, again: 'Переиграть'});
    this.replay = this.level; this.goNext = false; // «Переиграть» — тот же уровень, «Дальше» — следующий
  }
  die(msg) {
    this.dead = true; this.api.beep('hit');
    if (this.mode === 'levels') this.api.over({title: 'ОЙ!', big: lvlName(this.level), text: `${msg} Собрано ${this.eaten} из ${target(this.level)}.`});
    else this.api.over({title: 'ОЙ!', big: `Длина ${this.body.length}`, score: this.body.length, text: `${msg} Очки: ${this.score}.`});
  }
  update(dt) {
    if (this.dead) return;
    this.pops.forEach(p => { p.a -= dt; p.y -= dt * 1.5; }); this.pops = this.pops.filter(p => p.a > 0);
    if (this.bolt > 0) this.bolt -= dt;
    for (const it of this.items) it.life -= dt;
    if (this.items.some(i => i.life <= 0)) { this.items = this.items.filter(i => i.life > 0); while (this.items.length < 3) this.addSpool(); }
    if (this.boltItem && (this.boltItem.life -= dt) <= 0) this.boltItem = null;
    const tk = this.baseTick() * (this.bolt > 0 ? .8 : 1);
    this.t += dt;
    while (this.t >= tk && !this.dead) { this.t -= tk; this.tick(); }
    this.frac = Math.min(1, this.t / tk);
  }
  draw(g) {
    const {W, H, s, ox, oy, cols, rows} = this; if (!s) return;
    g.clearRect(0, 0, W, H);
    Mya.rrect(g, ox - 6, oy - 6, cols * s + 12, rows * s + 12, 16, '#3a0f5c', INK, 4);
    g.fillStyle = '#ffffff0d';
    for (let x = 0; x < cols; x++) for (let y = 0; y < rows; y++) if ((x + y) % 2) g.fillRect(ox + x * s, oy + y * s, s, s);
    if (this.wrap) { g.save(); g.setLineDash([8, 6]); Mya.rrect(g, ox - 2, oy - 2, cols * s + 4, rows * s + 4, 12, null, '#22e0d088', 3); g.restore(); }
    this.walls.forEach(k => { const [x, y] = k.split(',').map(Number); Mya.rrect(g, ox + x * s + 2, oy + y * s + 2, s - 4, s - 4, s * .22, '#6b2bb0', INK, 2.5); });
    const tm = performance.now() / 1000;
    for (const p of this.portals) {
      const cx = ox + (p.x + .5) * s, cy = oy + (p.y + .5) * s;
      g.beginPath(); g.arc(cx, cy, s * .42, 0, 7); g.lineWidth = s * .18; g.strokeStyle = '#22e0d0'; g.stroke();
      g.beginPath(); g.arc(cx, cy, s * (.15 + .08 * Math.sin(tm * 5)), 0, 7); g.fillStyle = '#22e0d088'; g.fill();
    }
    for (const it of this.items) {
      const blink = it.life < 2.5 && Math.sin(tm * 18) > 0; if (blink) continue;
      const im = Mya.spoolImg(it.c); if (im.complete) g.drawImage(im, ox + it.x * s - s * .1, oy + it.y * s - s * .1, s * 1.2, s * 1.2);
    }
    if (this.boltItem) { const b = this.boltItem, cx = ox + (b.x + .5) * s, cy = oy + (b.y + .5) * s; g.beginPath(); g.arc(cx, cy, s * .46, 0, 7); g.fillStyle = '#ffd23f'; g.fill(); g.lineWidth = 2.5; g.strokeStyle = INK; g.stroke(); Mya.text(g, '⚡', cx, cy + 1, s * .6, '#fff'); }
    // тело
    const f = this.dead ? 1 : (this.frac || 0);
    const pos = this.body.map(p => { const jump = Math.abs(p.x - p.px) + Math.abs(p.y - p.py) > 1; const k = jump ? 1 : f; return [ox + (p.px + (p.x - p.px) * k + .5) * s, oy + (p.py + (p.y - p.py) * k + .5) * s]; });
    g.lineCap = 'round'; g.lineJoin = 'round';
    const seg = (w, colorFn) => { for (let i = pos.length - 1; i > 0; i--) { const [a, b] = pos[i], [c, d] = pos[i - 1]; if (Math.hypot(a - c, b - d) > s * 1.5) continue; g.beginPath(); g.moveTo(a, b); g.lineTo(c, d); g.lineWidth = w; g.strokeStyle = colorFn(i); g.stroke(); } };
    seg(s * .86, () => INK);
    seg(s * .6, i => this.body[i].c);
    seg(s * .18, () => 'rgba(255,255,255,.35)');
    const [hx, hy] = pos[0], im = Mya.catImg(), hs = s * 1.55;
    if (this.bolt > 0) { g.beginPath(); g.arc(hx, hy, s * (.9 + .1 * Math.sin(tm * 20)), 0, 7); g.fillStyle = '#ffd23f66'; g.fill(); }
    if (im.complete) g.drawImage(im, hx - hs / 2, hy - hs * .56, hs, hs);
    for (const p of this.pops) { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, Math.min(Math.max(ox + (p.x + .5) * s, ox + 60), ox + cols * s - 60), oy + (p.y + .5) * s - s, Math.max(14, s * .7), '#ffd23f'); g.restore(); }
  }
}
})();
