/* Шарики по баночкам: разложи шарики так, чтобы в каждой баночке был один цвет. */
'use strict';
(() => {
const {INK} = Mya;
const CAP = 4;
const PAL = ['#ff9f1c', '#ff4fa3', '#22e0d0', '#a64dff', '#ffd23f', '#9dff4a', '#4da6ff', '#ff5a3c', '#ffffff', '#8b5a2b'];

Mya.games.sort = {
  id: 'sort', title: 'Шарики',
  modes: [
    {id: 'normal', name: 'Обычный', desc: 'Тапни баночку, потом другую — верхний шарик перепрыгнет. Класть можно на шарик того же цвета или в пустую баночку.'},
    {id: 'hidden', name: 'Скрытые ?', desc: 'Нижние шарики спрятаны под «?». Они открываются, когда над ними никого не осталось.'},
    {id: 'moves', name: 'Мало ходов', desc: 'На уровень даётся ограниченное число ходов. Думай прежде, чем двигать!'},
  ],
  controls: [{k: 'UNDO', l: '↶ Ход назад', wide: true}, {k: 'ADD', l: '+ Баночка', wide: true}, {k: 'RESET', l: '↺ Заново', wide: true}],
  touchOnly: false,
  keys: 'Мышкой: клик по баночке, затем по другой · Z — ход назад · R — заново',
  hint: 'Застрял? Добавь пустую баночку (один раз за уровень) или отмени ход.',
  recordText(mode) { const r = Mya.record('sort', mode || 'normal'); return r ? 'Ур. ' + r : '—'; },
  subText() { return 'Скрытые: ' + this.recordText('hidden'); },
  extra(mode) { return `<p>Уровень: <b>${Mya.store.get('sort.lvl.' + mode, 1)}</b></p>`; },
  create(api) { return new Sort(api); },
};

class Sort {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    this.onDown = e => { if (!api.running) return; const r = this.cv.getBoundingClientRect(); this.tap(e.clientX - r.left, e.clientY - r.top); };
    this.cv.addEventListener('pointerdown', this.onDown);
    this.reset('normal');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); }
  resize(W, H) { this.W = W; this.H = H; this.layout(); }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff;
    this.level = Mya.store.get('sort.lvl.' + mode, 1);
    const extra = {kid: -1, player: 0, pro: 1}[this.diff];
    this.nColors = Math.max(3, Math.min(PAL.length, 3 + Math.floor((this.level - 1) / 3) + extra));
    const rnd = Mya.rng(`sort${mode}${this.diff}${this.level}`);
    let balls = []; for (let c = 0; c < this.nColors; c++) for (let i = 0; i < CAP; i++) balls.push(c);
    let tries = 0;
    do { for (let i = balls.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [balls[i], balls[j]] = [balls[j], balls[i]]; } tries++; }
    while (tries < 20 && this.tooEasy(balls));
    this.tubes = []; for (let t = 0; t < this.nColors; t++) this.tubes.push(balls.slice(t * CAP, t * CAP + CAP));
    this.tubes.push([], []);
    this.hidden = this.tubes.map(t => t.map((_, i) => mode === 'hidden' && i < t.length - 1));
    this.sel = -1; this.hist = []; this.moves = 0; this.added = false; this.anim = null; this.won = false; this.t = 0;
    this.limit = mode === 'moves' ? this.nColors * 6 + 4 - (this.diff === 'pro' ? 4 : 0) + (this.diff === 'kid' ? 8 : 0) : 0;
    this.layout(); this.hud();
  }
  tooEasy(b) { let same = 0; for (let t = 0; t < this.nColors; t++) { const s = b.slice(t * CAP, t * CAP + CAP); if (s.every(x => x === s[0])) same++; } return same > 0; }
  layout() {
    if (!this.W || !this.tubes) return;
    const n = this.tubes.length, perRow = n <= 6 ? n : Math.ceil(n / 2), rows = Math.ceil(n / perRow);
    const tw = Math.min(70, (this.W - 20) / perRow - 12), bs = tw * .74, th = bs * CAP + tw * .5;
    const rowH = th + 36, total = rows * rowH;
    const scale = Math.min(1, (this.H - 70) / total);
    this.tw = tw * scale; this.bs = bs * scale; this.th = th * scale;
    this.pos = this.tubes.map((_, i) => {
      const r = Math.floor(i / perRow), inRow = Math.min(perRow, n - r * perRow), c = i - r * perRow;
      const gap = (this.W - inRow * this.tw) / (inRow + 1);
      return {x: gap + c * (this.tw + gap), y: 60 + (this.H - 60 - rows * rowH * scale) / 2 + r * rowH * scale + 30 * scale};
    });
  }
  hud() { this.api.hud(`Ур. ${this.level}`, this.limit ? `Ходы: ${this.moves}/${this.limit}` : `Ходы: ${this.moves}`); }
  key(code, down) {
    if (!down) return;
    if (code === 'UNDO' || code === 'KeyZ') this.undo();
    if (code === 'ADD' || code === 'KeyA') this.addTube();
    if (code === 'RESET' || code === 'KeyR') { this.reset(this.mode); }
    const n = parseInt(code.replace('Digit', ''), 10); if (code.startsWith('Digit') && n >= 1 && n <= this.tubes.length) this.pick(n - 1);
  }
  tap(x, y) {
    const i = this.pos.findIndex(p => x > p.x - 8 && x < p.x + this.tw + 8 && y > p.y - this.bs && y < p.y + this.th + 10);
    if (i >= 0) this.pick(i); else this.sel = -1;
  }
  canMove(a, b) {
    const A = this.tubes[a], B = this.tubes[b];
    return a !== b && A.length && B.length < CAP && (!B.length || B[B.length - 1] === A[A.length - 1]);
  }
  pick(i) {
    if (this.won || this.anim) return;
    if (this.sel < 0) { if (this.tubes[i].length) { this.sel = i; this.api.beep('move'); } return; }
    if (this.sel === i) { this.sel = -1; return; }
    if (!this.canMove(this.sel, i)) { this.api.beep('hit'); this.sel = this.tubes[i].length ? i : -1; return; }
    const a = this.sel, A = this.tubes[a], c = A[A.length - 1];
    let cnt = 0; while (A.length - cnt > 0 && A[A.length - 1 - cnt] === c && this.tubes[i].length + cnt < CAP && !this.hidden[a][A.length - 1 - cnt]) cnt++;
    this.hist.push({tubes: this.tubes.map(t => t.slice()), hidden: this.hidden.map(h => h.slice())});
    for (let k = 0; k < cnt; k++) { this.tubes[i].push(A.pop()); this.hidden[a].pop(); this.hidden[i].push(false); }
    if (A.length) this.hidden[a][A.length - 1] = false;
    this.anim = {from: a, to: i, t: 0, c}; this.sel = -1; this.moves++; this.api.beep('rot');
    this.hud(); this.check();
  }
  undo() { const h = this.hist.pop(); if (!h || this.won) return; this.tubes = h.tubes; this.hidden = h.hidden; this.moves++; this.sel = -1; this.layout(); this.hud(); }
  addTube() { if (this.added || this.won) return; this.added = true; this.tubes.push([]); this.hidden.push([]); this.layout(); this.api.beep('star'); }
  check() {
    const done = this.tubes.every(t => !t.length || (t.length === CAP && t.every(x => x === t[0])));
    if (done) {
      this.won = true; this.api.beep('win');
      const n = this.level + 1; Mya.store.set('sort.lvl.' + this.mode, n); Mya.saveRecord('sort', this.mode, this.level);
      this.api.challenge('level', this.level);
      setTimeout(() => this.api.over({title: 'РАЗЛОЖЕНО!', big: `Уровень ${this.level} ✔`, text: `Ходов: ${this.moves}. Дальше будет ${this.nColors < PAL.length ? 'больше цветов' : 'ещё запутаннее'}!`, again: 'Следующий уровень'}), 500);
      return;
    }
    if (this.limit && this.moves >= this.limit) setTimeout(() => this.api.over({title: 'ХОДЫ КОНЧИЛИСЬ', text: 'Попробуй ещё раз — план поможет!', again: 'Ещё раз'}), 400);
  }
  update(dt) { this.t += dt; if (this.anim) { this.anim.t += dt * 4; if (this.anim.t >= 1) this.anim = null; } }
  draw(g) {
    const {W, H, tw, bs, th} = this; if (!W) return;
    g.clearRect(0, 0, W, H);
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#3a0f5c'); bg.addColorStop(1, '#5b1a96');
    Mya.rrect(g, 0, 0, W, H, 22, bg);
    Mya.text(g, this.won ? 'Ура! Всё по цветам!' : 'Разложи шарики по цветам!', W / 2, 30, Math.min(22, W / 18), '#ffd23f');
    this.tubes.forEach((t, i) => {
      const p = this.pos[i], lift = i === this.sel ? -bs * .6 : 0, full = t.length === CAP && t.every(x => x === t[0]);
      g.save();
      g.beginPath(); const r = tw / 2;
      g.moveTo(p.x, p.y); g.lineTo(p.x, p.y + th - r); g.arc(p.x + r, p.y + th - r, r, Math.PI, 0, true); g.lineTo(p.x + tw, p.y);
      g.fillStyle = full ? '#9dff4a33' : '#ffffff1f'; g.fill(); g.lineWidth = 4; g.strokeStyle = full ? '#9dff4a' : '#fff'; g.stroke();
      g.restore();
      t.forEach((c, j) => {
        let x = p.x + tw / 2, y = p.y + th - bs * .5 - tw * .12 - j * bs;
        if (j === t.length - 1) y += lift;
        if (this.anim && this.anim.to === i && j === t.length - 1) { const f = p, q = this.pos[this.anim.from], k = 1 - this.anim.t; x += (q.x - f.x) * k; y -= Math.sin(this.anim.t * Math.PI) * bs * 1.2; }
        const hid = this.hidden[i][j];
        g.beginPath(); g.arc(x, y, bs * .42, 0, 7); g.fillStyle = hid ? '#6b2bb0' : PAL[c]; g.fill(); g.lineWidth = 3; g.strokeStyle = INK; g.stroke();
        if (hid) Mya.text(g, '?', x, y + 1, bs * .5); else { g.beginPath(); g.arc(x - bs * .14, y - bs * .14, bs * .12, 0, 7); g.fillStyle = '#ffffff99'; g.fill(); }
      });
    });
    if (this.added === false && this.moves > 12 && !this.won) Mya.text(g, 'Подсказка: «+ Баночка» внизу', W / 2, H - 16, 14, '#fff');
  }
}
})();
