/* Картинки-превью для плиток витрины (SVG). */
'use strict';
(() => {
const cat = (s, b) => Mya.catSVG(s, b), C = Mya.COL;
function blk(x,y,s,c,ghost){if(ghost)return `<rect x="${x+2}" y="${y+2}" width="${s-4}" height="${s-4}" rx="5" fill="none" stroke="#fff" stroke-width="2.5" stroke-dasharray="5 4" opacity=".7"/>`;
return `<g><rect x="${x+1}" y="${y+1}" width="${s-2}" height="${s-2}" rx="6" fill="${c}" stroke="#2b0a3d" stroke-width="3"/><rect x="${x+5}" y="${y+5}" width="${s-16}" height="${s*.22}" rx="3" fill="#fff" opacity=".45"/><rect x="${x+4}" y="${y+s-9}" width="${s-8}" height="4" rx="2" fill="#000" opacity=".15"/></g>`}
function piece(cells,c,s,ox,oy){return cells.map(([a,b])=>blk(ox+a*s,oy+b*s,s,c)).join('')}

function gBlocks(){const s=34,W=10,H=17,ox=10,oy=10;let o=`<svg viewBox="0 0 360 600" preserveAspectRatio="xMidYMax slice" width="100%" height="100%"><rect width="360" height="600" fill="#2b0a3d"/>`;
for(let x=0;x<=W;x++)o+=`<line x1="${ox+x*s}" y1="${oy}" x2="${ox+x*s}" y2="${oy+H*s}" stroke="#ffffff14"/>`;for(let y=0;y<=H;y++)o+=`<line x1="${ox}" y1="${oy+y*s}" x2="${ox+W*s}" y2="${oy+y*s}" stroke="#ffffff14"/>`;
const rows=['..........','v.......p.','vv.y...pp.','yvvyy.ooov','yyoopp.ovv','ccooppyyvv','pcclllyyy.','ppclloovv.'];const k='yopvclb';
rows.forEach((r,ri)=>[...r].forEach((ch,ci)=>{if(ch!=='.')o+=blk(ox+ci*s,oy+(H-rows.length+ri)*s,s,C[ch])}));
// cleared flash row
o+=`<rect x="${ox}" y="${oy+(H-3)*s}" width="${W*s}" height="${s}" fill="#fff" opacity=".85"/><rect x="${ox-6}" y="${oy+(H-3)*s-6}" width="${W*s+12}" height="${s+12}" fill="none" stroke="#ffd23f" stroke-width="4" rx="8"/>`;
o+=piece([[4,2],[5,2],[6,2],[5,3]],C.c,s,ox,oy);
o+=[[4,7],[5,7],[6,7],[5,8]].map(([a,b])=>blk(ox+a*s,oy+b*s,s,0,1)).join('');
o+=`<text x="300" y="60" font-size="22">✨</text><text x="40" y="200" font-size="18">✨</text></svg>`;return o}

function spool(x,y,r,c){return `<g transform="translate(${x},${y})"><ellipse rx="${r}" ry="${r*.42}" cy="${r*.35}" fill="#a64dff" stroke="#2b0a3d" stroke-width="3"/><rect x="${-r*.8}" y="${-r*.35}" width="${r*1.6}" height="${r*.7}" fill="${c}" stroke="#2b0a3d" stroke-width="3"/><path d="M${-r*.8} 0h${r*1.6}" stroke="#fff" stroke-width="2" opacity=".5"/><ellipse rx="${r}" ry="${r*.42}" cy="${-r*.35}" fill="#c98aff" stroke="#2b0a3d" stroke-width="3"/><ellipse rx="${r*.25}" ry="${r*.1}" cy="${-r*.35}" fill="#2b0a3d"/></g>`}

function gSnake(){const s=30,ox=0,oy=0;let o=`<svg viewBox="0 0 360 600" preserveAspectRatio="xMidYMid slice" width="100%" height="100%"><rect width="360" height="600" fill="#3a0f5c"/>`;
for(let x=0;x<12;x++)for(let y=0;y<20;y++)if((x+y)%2)o+=`<rect x="${x*s}" y="${y*s}" width="${s}" height="${s}" fill="#ffffff0d"/>`;
// walls
[[2,5],[3,5],[4,5],[8,12],[8,13],[8,14],[9,14]].forEach(([a,b])=>o+=`<rect x="${a*s+2}" y="${b*s+2}" width="${s-4}" height="${s-4}" rx="6" fill="#6b2bb0" stroke="#2b0a3d" stroke-width="3"/>`);
// portals
o+=`<circle cx="${10.5*s}" cy="${3.5*s}" r="16" fill="none" stroke="#22e0d0" stroke-width="6"/><circle cx="${10.5*s}" cy="${3.5*s}" r="8" fill="#22e0d0" opacity=".5"/><circle cx="${1.5*s}" cy="${17.5*s}" r="16" fill="none" stroke="#22e0d0" stroke-width="6"/><circle cx="${1.5*s}" cy="${17.5*s}" r="8" fill="#22e0d0" opacity=".5"/>`;
const path=[[5,8],[5,9],[5,10],[5,11],[4,11],[3,11],[3,12],[3,13],[3,14],[4,14],[5,14],[6,14],[6,15],[6,16],[7,16],[8,16],[9,16],[10,16],[10,17]];
const cols=['#ff9f1c','#ff4fa3','#ffd23f'];
o+=`<polyline points="${path.map(([a,b])=>`${a*s+s/2},${b*s+s/2}`).join(' ')}" fill="none" stroke="#2b0a3d" stroke-width="28" stroke-linecap="round" stroke-linejoin="round"/>`;
for(let i=path.length-1;i>0;i--){const[a,b]=path[i],[c,d]=path[i-1];o+=`<line x1="${a*s+s/2}" y1="${b*s+s/2}" x2="${c*s+s/2}" y2="${d*s+s/2}" stroke="${cols[Math.floor(i/2)%3]}" stroke-width="20" stroke-linecap="round"/>`}
o+=cat(46).replace('<svg',`<svg x="${5*s+s/2-23}" y="${8*s+s/2-30}"`);
o+=spool(5.5*s,4.5*s,14,'#ff4fa3')+spool(9.5*s,8.5*s,14,'#ff9f1c')+spool(1.5*s,9.5*s,14,'#ffd23f');
o+=`<g transform="translate(${7.5*s},${2.5*s})"><circle r="14" fill="#ffd23f" stroke="#2b0a3d" stroke-width="3"/><text y="6" text-anchor="middle" font-size="16">⚡</text></g>`;
o+=`<text x="${5.5*s}" y="${3.3*s}" text-anchor="middle" font-family="Rubik" font-weight="900" font-size="15" fill="#fff" stroke="#2b0a3d" stroke-width="4" paint-order="stroke">×2 цвет!</text></svg>`;return o}

function gRun(){let o=`<svg viewBox="0 0 360 600" preserveAspectRatio="xMidYMax slice" width="100%" height="100%"><defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff7ac6"/><stop offset="1" stop-color="#ffb35c"/></linearGradient></defs><rect width="360" height="600" fill="url(#sky)"/>`;
// shelves both sides
for(let i=0;i<4;i++){const y=60+i*42;o+=`<rect x="0" y="${y}" width="${110-i*16}" height="10" fill="#8b2fd6" stroke="#2b0a3d" stroke-width="3"/><rect x="${250+i*16}" y="${y}" width="${110-i*16}" height="10" fill="#8b2fd6" stroke="#2b0a3d" stroke-width="3"/>`;
 o+=`<rect x="${14+i*8}" y="${y-20}" width="18" height="20" rx="4" fill="${['#22e0d0','#ffd23f','#9dff4a','#4da6ff'][i]}" stroke="#2b0a3d" stroke-width="2.5"/><rect x="${300+i*6}" y="${y-22}" width="16" height="22" rx="4" fill="${['#ffd23f','#22e0d0','#ff4fa3','#9dff4a'][i]}" stroke="#2b0a3d" stroke-width="2.5"/>`}
// printer gate
o+=`<rect x="120" y="150" width="120" height="80" rx="12" fill="#b45cff" stroke="#2b0a3d" stroke-width="4"/><rect x="138" y="168" width="84" height="62" fill="#3a0f5c"/><rect x="166" y="160" width="28" height="20" rx="5" fill="#fff" stroke="#2b0a3d" stroke-width="3"/>`;
o+=`<polygon points="150,230 210,230 360,600 0,600" fill="#c58cff" stroke="#2b0a3d" stroke-width="4"/>`;
o+=`<line x1="170" y1="230" x2="120" y2="600" stroke="#ffd23f" stroke-width="6"/><line x1="190" y1="230" x2="240" y2="600" stroke="#ffd23f" stroke-width="6"/>`;
o+=spool(120,330,30,'#ff4fa3')+spool(245,320,26,'#ff9f1c')+spool(178,260,14,'#22e0d0');
o+=`<g font-size="30"><text x="166" y="330">⭐</text><text x="170" y="290" font-size="22">⭐</text><text x="172" y="262" font-size="15">⭐</text></g>`;
o+=`<g transform="translate(250,410)"><circle r="22" fill="#22e0d0" stroke="#2b0a3d" stroke-width="4"/><text y="9" text-anchor="middle" font-size="24">🧲</text></g>`;
// barrier to slide under
o+=`<rect x="40" y="395" width="110" height="18" rx="6" fill="#ffd23f" stroke="#2b0a3d" stroke-width="4"/><rect x="48" y="413" width="8" height="40" fill="#2b0a3d"/><rect x="134" y="413" width="8" height="40" fill="#2b0a3d"/>`;
o+=cat(150,1).replace('<svg','<svg x="105" y="420"');
o+=`<path d="M120 580 l-10 18 M240 580 l10 18 M180 585 v14" stroke="#fff" stroke-width="5" stroke-linecap="round"/></svg>`;return o}

const SV=b=>`<svg viewBox="0 0 360 600" preserveAspectRatio="xMidYMid meet" width="100%" height="100%">${b}</svg>`;
const T=(x,y,t,fs,fill='#fff',anc='middle')=>`<text x="${x}" y="${y}" text-anchor="${anc}" font-family="Rubik" font-weight="900" font-size="${fs}" fill="${fill}" stroke="#2b0a3d" stroke-width="${fs/5}" paint-order="stroke">${t}</text>`;

// 1. Stack printing
// 5. Draw bridge
function gBridge(){let o=`<defs><linearGradient id="bs" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb35c"/><stop offset="1" stop-color="#ff7ac6"/></linearGradient></defs><rect width="360" height="600" fill="url(#bs)"/>`;
o+=`<path d="M0 220 h110 v380 h-110z" fill="#a64dff" stroke="#2b0a3d" stroke-width="5"/><path d="M250 400 h110 v200 h-110z" fill="#a64dff" stroke="#2b0a3d" stroke-width="5"/>`;
o+=`<path d="M0 220 h110" stroke="#9dff4a" stroke-width="10"/><path d="M250 400 h110" stroke="#9dff4a" stroke-width="10"/>`;
// spikes
o+=`<path d="M110 600 ${[...Array(7)].map((_,i)=>`l10 -24 l10 24`).join(' ')}z" fill="#fff" stroke="#2b0a3d" stroke-width="3"/>`;
// moving block obstacle
o+=`<rect x="160" y="240" width="60" height="26" rx="8" fill="#22e0d0" stroke="#2b0a3d" stroke-width="4"/><path d="M150 253h-14 M230 253h14" stroke="#fff" stroke-width="4" stroke-linecap="round"/>`;
// drawn line
o+=`<path d="M112 222 C150 300 190 330 250 398" stroke="#2b0a3d" stroke-width="14" fill="none" stroke-linecap="round"/><path d="M112 222 C150 300 190 330 250 398" stroke="#ffd23f" stroke-width="7" fill="none" stroke-linecap="round" stroke-dasharray="1 0"/>`;
o+=`<text x="232" y="390" font-size="34">✏️</text>`;
// yarn ball
o+=`<g transform="translate(70,190)"><circle r="28" fill="#ff4fa3" stroke="#2b0a3d" stroke-width="4"/><path d="M-20 -14 q20 10 36 -6 M-26 4 q26 12 50 -4 M-14 20 q16 4 30 -8" stroke="#fff" stroke-width="3" fill="none" opacity=".7"/></g>`;
// stars
o+=`<text x="148" y="300" font-size="28">⭐</text><text x="198" y="345" font-size="28">⭐</text><text x="290" y="200" font-size="28" opacity=".5">⭐</text>`;
o+=cat(90).replace('<svg','<svg x="262" y="312"');
o+=`<g transform="translate(180,40)"><rect x="-120" y="-16" width="240" height="30" rx="15" fill="#fff" stroke="#2b0a3d" stroke-width="4"/><rect x="-116" y="-12" width="140" height="22" rx="11" fill="#2b0a3d"/></g>`+T(180,85,'Чернила: 60%',18);
return SV(o)}



Mya.previews = {blocks: gBlocks, snake: gSnake, run: gRun, bridge: gBridge};
})();
