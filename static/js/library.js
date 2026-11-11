/* Медиатека магазина: один список всех фото и видео сайта (админка → «Библиотека»).
   Library.mount(el)            — вкладка «Библиотека» в админке: просмотр, загрузка, переименование, удаление
   Library.pick({kind,multiple,title}) → Promise<[элемент]|null> — окно выбора для других блоков
   Library.file(элемент) → Promise<File> — сам файл, чтобы отдать его в обычную загрузку блока
   Library.upload(files) → Promise<[элемент]> — положить файлы в библиотеку */
(function(){
"use strict";
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=b=>!b?'':b>=1048576?(b/1048576).toFixed(1).replace('.',',')+' МБ':Math.max(1,Math.round(b/1024))+' КБ';
const day=s=>s?new Date(s).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'2-digit'}):'';
async function req(url,o){o=o||{};const opt={method:o.method||'GET',credentials:'same-origin',headers:{}};
  if(o.json!==undefined){opt.headers['content-type']='application/json';opt.body=JSON.stringify(o.json)}
  if(o.form!==undefined)opt.body=o.form;
  const r=await fetch(url,opt);if(!r.ok){let m='Ошибка '+r.status;try{const j=await r.json();if(j.detail)m=typeof j.detail==='string'?j.detail:(j.detail[0]&&j.detail[0].msg)||m}catch(e){}throw new Error(m)}
  return r.status===204?null:r.json()}

const css=`.lib-ov{position:fixed;inset:0;background:rgba(45,26,51,.45);z-index:1000;display:flex;align-items:center;justify-content:center;padding:14px}
.lib-dlg{background:#fff;border-radius:18px;width:min(1100px,100%);max-height:calc(100vh - 28px);display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.25);overflow:hidden}
.lib-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:12px 14px;border-bottom:1px solid #f0e2d6}
.lib-top b{font-size:16px;margin-right:auto}
.lib-body{overflow:auto;padding:12px 14px;flex:1}
.lib-bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.lib-bar input[type=search]{font:inherit;padding:7px 10px;border:1.5px solid #f0e2d6;border-radius:10px;min-width:180px;flex:1;max-width:320px}
.lib-chip{border:1.5px solid #f0e2d6;background:#fff;border-radius:99px;padding:4px 11px;font:inherit;font-size:13px;cursor:pointer;color:inherit}
.lib-chip.on{background:#7a2e8e;border-color:#7a2e8e;color:#fff}
.lib-btn{border:0;border-radius:10px;padding:8px 13px;font:inherit;font-weight:700;cursor:pointer;background:#f7ece2;color:#2d1a33;display:inline-flex;gap:6px;align-items:center;white-space:nowrap}
.lib-btn.pri{background:linear-gradient(135deg,#f59331,#e2600c);color:#fff}.lib-btn:disabled{opacity:.5;cursor:default}
.lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.lib-it{position:relative;border:2px solid #f0e2d6;border-radius:14px;overflow:hidden;background:#fff;cursor:pointer;font-size:12px}
.lib-it.on{border-color:#e2600c;box-shadow:0 0 0 3px rgba(226,96,12,.2)}
.lib-it .th{aspect-ratio:1;background:#f8efe6 repeating-conic-gradient(#f3e6da 0 25%,#fbf5ef 0 50%) 0 0/16px 16px;display:grid;place-items:center;overflow:hidden}
.lib-it .th img,.lib-it .th video{width:100%;height:100%;object-fit:contain}
.lib-it .nm{padding:5px 7px 0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lib-it .mt{padding:0 7px 6px;color:#7f6b7a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lib-it .vb{position:absolute;left:6px;top:6px;background:rgba(45,26,51,.75);color:#fff;border-radius:7px;padding:1px 6px;font-size:11px}
.lib-it .ck{position:absolute;right:6px;top:6px;width:22px;height:22px;border-radius:50%;background:#e2600c;color:#fff;display:none;place-items:center;font-weight:900}
.lib-it.on .ck{display:grid}
.lib-empty{padding:40px;text-align:center;color:#7f6b7a}
.lib-foot{display:flex;gap:8px;align-items:center;padding:10px 14px;border-top:1px solid #f0e2d6}
.lib-side{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:14px;align-items:start}
@media(max-width:900px){.lib-side{grid-template-columns:1fr}}
.lib-info{background:#fff;border:1px solid #f0e2d6;border-radius:16px;padding:14px;position:sticky;top:110px}
.lib-info .pv{background:#f8efe6 repeating-conic-gradient(#f3e6da 0 25%,#fbf5ef 0 50%) 0 0/16px 16px;border-radius:12px;overflow:hidden;margin-bottom:10px;display:grid;place-items:center;max-height:340px}
.lib-info .pv img,.lib-info .pv video{max-width:100%;max-height:340px;display:block}
.lib-info input{width:100%;font:inherit;padding:7px 9px;border:1.5px solid #f0e2d6;border-radius:9px;box-sizing:border-box}
.lib-info .rw{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.lib-drop{border:2px dashed #e6cdb8;border-radius:14px;padding:12px;text-align:center;color:#7f6b7a;margin-bottom:10px}
.lib-drop.over{background:#fff4ea;border-color:#e2600c}`;
let styled=false;function style(){if(styled)return;styled=true;const s=document.createElement('style');s.textContent=css;document.head.appendChild(s)}

let cache=null;
async function list(force){if(!cache||force)cache=await req('/api/admin/library');return cache}
async function upload(files,category){files=[...files];if(!files.length)return[];const out=[];
  for(let i=0;i<files.length;i+=10){const fd=new FormData();files.slice(i,i+10).forEach(f=>fd.append('files',f,f.name||'файл'));if(category)fd.append('category',category);
    out.push(...(await req('/api/admin/library',{method:'POST',form:fd})).items)}
  cache=null;return out}
async function file(it){const r=await fetch(it.url,{credentials:'same-origin'});if(!r.ok)throw new Error('Не получилось взять «'+it.name+'» из библиотеки');
  const b=await r.blob(),type=b.type||it.mime||'',ext=(type.split('/')[1]||'').replace('jpeg','jpg').replace('quicktime','mov').replace(/[^a-z0-9]/g,'');
  let name=it.name||'файл';if(ext&&!/\.[a-z0-9]{2,5}$/i.test(name))name+='.'+ext;return new File([b],name,{type})}
/* delete from the place where the file is kept; returns {deleted:[keys], skipped:[{key,why}]} */
async function removeMany(items){const r=await req('/api/admin/library/delete',{method:'POST',json:{keys:items.map(it=>it.key)}});cache=null;return r}
async function remove(it){const r=await removeMany([it]);if(r.skipped.length)throw new Error(r.skipped[0].why);return r}
// what else changes when a file goes away
const WARN={card:'карточка пропадёт из библиотеки конструктора (копия в магазине останется)',photo:'фото пропадёт из раздела «Фото» конструктора',
  cutout:'в визитках и буклете на месте этой картинки станет пусто',media:'фото или видео пропадёт из карусели товара',color:'у цвета пластика не будет фото',
  customer:'файл пропадёт из заявки или отзыва покупателя'};
function warnText(items){const n=items.length,srcs=[...new Set(items.map(it=>it.src))].filter(s=>WARN[s]);
  return (n===1?'Удалить «'+items[0].name+'»?':'Удалить файлы: '+n+'?')+(srcs.length?'\n\nУчти: '+srcs.map(s=>WARN[s]).join('; ')+'.':'')+'\n\nОтменить удаление нельзя.'}

/* a category is what the library filters by: uploaded files get the one the admin chose, the rest the place they come from */
const NOCAT='Без категории';
function catOf(it,data){return it.src==='upload'?(it.cat||NOCAT):(data.sources[it.src]||it.src)}
function catOrder(data){const o=[...(data.categories||[])];Object.entries(data.sources).forEach(([k,l])=>{if(k!=='upload'&&!o.includes(l))o.push(l)});o.push(NOCAT);return o}
async function setCategory(items,category){const r=await req('/api/admin/library/category',{method:'POST',json:{keys:items.map(it=>it.key),category}});cache=null;return r}
function catList(data){return'<datalist id="libCats">'+(data.categories||[]).map(c=>`<option value="${esc(c)}">`).join('')+'</datalist>'}
function thumbHtml(it){if(it.thumb)return`<img src="${esc(it.thumb)}" loading="lazy" alt="">`;
  if(it.kind==='video')return`<video src="${esc(it.url)}#t=0.5" muted preload="metadata" playsinline></video>`;
  return`<img src="${esc(it.url)}" loading="lazy" alt="">`}
function tile(it,on){return`<div class="lib-it ${on?'on':''}" data-k="${esc(it.key)}" title="${esc(it.name)}${it.where?' · '+esc(it.where):''}"><div class="th">${thumbHtml(it)}</div>
  ${it.kind==='video'?'<span class="vb">▶ видео</span>':''}<span class="ck">✓</span><div class="nm">${esc(it.name)}</div><div class="mt">${esc(size(it.size))}${it.t?' · '+esc(day(it.t)):''}</div></div>`}

/* a filterable grid; used both in the picker window and on the admin tab */
function grid(root,o){const st={cat:o.cat||'',kind:o.kind&&o.kind!=='any'?o.kind:'',q:'',data:null};
  root.innerHTML=`<div class="lib-drop">Перетащи сюда ${o.kind==='image'?'фото':o.kind==='video'?'видео':'фото или видео'}, или <label class="lib-btn pri" style="padding:5px 11px">⬆️ Загрузить<input type="file" multiple hidden accept="${o.kind==='image'?'image/*':o.kind==='video'?'video/*,.mp4,.mov,.webm':'image/*,video/*,.mp4,.mov,.webm'}"></label> <span class="lib-up"></span></div>
    <div class="lib-bar"><input type="search" placeholder="Поиск по названию"><span class="lib-srcs" style="display:contents"></span>${o.kind&&o.kind!=='any'?'':'<span style="flex:1"></span><span class="lib-kinds" style="display:contents"></span>'}</div><div class="lib-grid"></div>`;
  const q=root.querySelector('input[type=search]'),g=root.querySelector('.lib-grid'),up=root.querySelector('input[type=file]'),upS=root.querySelector('.lib-up'),drop=root.querySelector('.lib-drop');
  const items=()=>st.data.items.filter(it=>(!st.cat||catOf(it,st.data)===st.cat)&&(!st.kind||it.kind===st.kind)&&(!st.q||(it.name+' '+it.where).toLowerCase().includes(st.q)));
  function draw(){if(!st.data){g.innerHTML='<div class="lib-empty">Загружаю…</div>';return}
    const all=st.data.items.filter(it=>!st.kind||it.kind===st.kind),cnt={};all.forEach(it=>cnt[it.src]=(cnt[it.src]||0)+1);
    const cc={};all.forEach(it=>{const c=catOf(it,st.data);cc[c]=(cc[c]||0)+1});
    root.querySelector('.lib-srcs').innerHTML=[['','Все',all.length]].concat(catOrder(st.data).filter(c=>cc[c]||c===st.cat).map(c=>[c,c,cc[c]||0]))
      .map(([k,l,n])=>`<button type="button" class="lib-chip ${st.cat===k?'on':''}" data-src="${esc(k)}">${esc(l)} · ${n}</button>`).join('');
    upS.dataset.hint=st.cat&&st.cat!==NOCAT?'Новые файлы попадут в категорию «'+st.cat+'»':'';if(!upS.dataset.busy)upS.textContent=upS.dataset.hint;
    const kb=root.querySelector('.lib-kinds');if(kb)kb.innerHTML=[['','Всё'],['image','📷 Фото'],['video','🎬 Видео']].map(([k,l])=>`<button type="button" class="lib-chip ${st.kind===k?'on':''}" data-kind="${k}">${l}</button>`).join('');
    const list=items();g.innerHTML=list.length?list.map(it=>tile(it,o.isOn(it))).join(''):`<div class="lib-empty" style="grid-column:1/-1">${st.data.items.length?'Ничего не нашлось':'Библиотека пуста. Загрузи фото или видео, или сохрани карточку в конструкторе.'}</div>`}
  async function load(force){try{st.data=await list(force)}catch(e){g.innerHTML='<div class="lib-empty">'+esc(e.message)+'</div>';return}draw()}
  async function add(files){files=[...files].filter(f=>/^(image|video)\//.test(f.type)||/\.(mp4|mov|webm|jpe?g|png|webp|gif|heic)$/i.test(f.name));if(!files.length)return;
    const cat=st.cat&&st.cat!==NOCAT?st.cat:'';upS.dataset.busy=1;
    upS.textContent='⏳ Загружаю '+files.length+'…';try{const added=await upload(files,cat);upS.textContent='✓ Загружено: '+added.length+(cat?' в «'+cat+'»':'');if(!cat)st.cat='';st.q='';q.value='';await load(true);o.added&&o.added(added)}catch(e){upS.textContent='⚠️ '+e.message}
    setTimeout(()=>{delete upS.dataset.busy},4000)}
  root.addEventListener('click',e=>{const s=e.target.closest('[data-src]');if(s){st.cat=s.dataset.src;return draw()}const k=e.target.closest('[data-kind]');if(k){st.kind=k.dataset.kind;return draw()}
    const t=e.target.closest('.lib-it');if(t){const it=st.data.items.find(x=>x.key===t.dataset.k);if(it)o.click(it)}});
  q.oninput=()=>{st.q=q.value.trim().toLowerCase();draw()};up.onchange=()=>{const f=[...up.files];up.value='';add(f)};
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('over')});drop.addEventListener('dragleave',()=>drop.classList.remove('over'));
  drop.addEventListener('drop',e=>{e.preventDefault();e.stopPropagation();drop.classList.remove('over');add(e.dataTransfer.files||[])});
  load(false);return{draw,load,visible:()=>st.data?items():[],data:()=>st.data,get:k=>st.data&&st.data.items.find(x=>x.key===k)}}

/* the picker window */
function pick(o){o=o||{};style();return new Promise(res=>{const sel=new Map();
  const ov=document.createElement('div');ov.className='lib-ov';
  ov.innerHTML=`<div class="lib-dlg" role="dialog" aria-label="Библиотека"><div class="lib-top"><b>📚 ${esc(o.title||'Выбери из библиотеки')}</b>${(o.extra||[]).map((x,i)=>`<button type="button" class="lib-btn" data-x="${i}">${esc(x.label)}</button>`).join('')}<button type="button" class="lib-btn" data-close>✕</button></div>
    <div class="lib-body"></div>${o.multiple?'<div class="lib-foot"><span class="lib-n" style="color:#7f6b7a;margin-right:auto">Ничего не выбрано</span><button type="button" class="lib-btn" data-close>Отмена</button><button type="button" class="lib-btn pri" data-ok disabled>Выбрать</button></div>':''}</div>`;
  document.body.appendChild(ov);
  const done=v=>{ov.remove();document.removeEventListener('keydown',key);res(v)},key=e=>{if(e.key==='Escape')done(null)};document.addEventListener('keydown',key);
  const foot=()=>{if(!o.multiple)return;ov.querySelector('.lib-n').textContent=sel.size?'Выбрано: '+sel.size:'Ничего не выбрано';ov.querySelector('[data-ok]').disabled=!sel.size};
  const G=grid(ov.querySelector('.lib-body'),{kind:o.kind,cat:o.cat,isOn:it=>sel.has(it.key),
    click:it=>{if(!o.multiple)return done([it]);sel.has(it.key)?sel.delete(it.key):sel.set(it.key,it);foot();G.draw()},
    added:items=>{if(!o.multiple){const ok=items.filter(it=>!o.kind||o.kind==='any'||it.kind===o.kind);if(ok.length===1)return done(ok)}else{items.forEach(it=>sel.set(it.key,it));foot();G.draw()}}});
  ov.addEventListener('click',e=>{if(e.target===ov||e.target.closest('[data-close]'))return done(null);if(e.target.closest('[data-ok]'))return done([...sel.values()]);
    const x=e.target.closest('[data-x]');if(x)done(o.extra[+x.dataset.x].value)})})}

/* the admin tab */
function mount(el,o){o=o||{};style();let cur=null,multi=false,catVal='';const sel=new Map();
  const say=m=>o.toast?o.toast(m):alert(m);
  el.innerHTML=`<div class="lib-side"><div><div class="lib-bar lib-selbar"></div><div class="lib-main"></div></div><div class="lib-info"><div style="color:#7f6b7a;text-align:center;padding:30px 0">Выбери файл, чтобы посмотреть, переименовать или удалить</div></div></div>`;
  const info=el.querySelector('.lib-info'),bar=el.querySelector('.lib-selbar');
  const G=grid(el.querySelector('.lib-main'),{kind:'any',isOn:it=>multi?sel.has(it.key):cur&&cur.key===it.key,
    click:it=>{if(multi){if(!it.del)return say('«'+it.name+'» здесь удалить нельзя: '+(it.src==='card'?'это главная картинка товара, она удаляется вместе с товаром в разделе «Товары»':'он удаляется в своём разделе'));
        sel.has(it.key)?sel.delete(it.key):sel.set(it.key,it);drawBar();return G.draw()}
      cur=it;G.draw();show(it)},added:()=>{}});
  function drawBar(){bar.innerHTML=multi?`<b>Выбрано: ${sel.size}</b><button type="button" class="lib-btn" data-s="all">Выбрать все показанные</button><button type="button" class="lib-btn" data-s="none">Снять выбор</button>
      <span style="display:inline-flex;gap:4px"><input class="lib-catin" list="libCats" placeholder="Категория" value="${esc(catVal)}" style="font:inherit;padding:7px 9px;border:1.5px solid #f0e2d6;border-radius:10px;width:160px"><button type="button" class="lib-btn" data-s="cat" ${sel.size?'':'disabled'}>📁 Переместить</button></span>
      <button type="button" class="lib-btn" data-s="del" style="background:#fee2e2;color:#dc2626" ${sel.size?'':'disabled'}>🗑 Удалить выбранные</button><button type="button" class="lib-btn" data-s="off">Готово</button>`
    :`<button type="button" class="lib-btn" data-s="on">☑️ Выбрать несколько</button><span style="color:#7f6b7a;font-size:13px">чтобы удалить сразу много файлов</span>`}
  bar.oninput=e=>{if(e.target.classList.contains('lib-catin'))catVal=e.target.value};
  bar.onclick=async e=>{const b=e.target.closest('[data-s]');if(!b)return;const a=b.dataset.s;
    if(a==='on'){multi=true;sel.clear()}else if(a==='off'){multi=false;sel.clear()}else if(a==='none')sel.clear();
    else if(a==='cat'){const items=[...sel.values()],c=bar.querySelector('.lib-catin').value.trim();
      const up=items.filter(it=>it.src==='upload');if(!up.length)return say('Категорию можно задать только файлам, загруженным в библиотеку');
      try{const r=await setCategory(up,c);say((c?'Перемещено в «'+c+'»: ':'Убрано из категорий: ')+r.updated+(items.length>up.length?' · остальные живут в своих разделах':''));sel.clear();await G.load(true)}catch(er){say(er.message)}}
    else if(a==='all')G.visible().filter(it=>it.del).forEach(it=>sel.set(it.key,it));
    else if(a==='del'){const items=[...sel.values()];if(!items.length||!confirm(warnText(items)))return;
      try{const r=await removeMany(items);say('Удалено: '+r.deleted.length+(r.skipped.length?' · пропущено: '+r.skipped.length:''));sel.clear();
        if(cur&&r.deleted.includes(cur.key)){cur=null;info.innerHTML='<div style="color:#7f6b7a;text-align:center;padding:30px 0">Удалено</div>'}await G.load(true)}catch(er){say(er.message)}}
    drawBar();G.draw()};
  drawBar();
  const dl=document.createElement('div');dl.style.display='none';el.appendChild(dl);list().then(d=>{dl.innerHTML=catList(d)}).catch(()=>{});
  function show(it){const src=(cache&&cache.sources[it.src])||'';
    info.innerHTML=`<div class="pv">${it.kind==='video'?`<video src="${esc(it.url)}" controls playsinline preload="metadata"></video>`:`<img src="${esc(it.url)}" alt="">`}</div>
      ${it.src==='upload'?`<input id="libName" value="${esc(it.name)}" maxlength="300" placeholder="Название">
        <div style="margin-top:6px;font-size:13px;color:#7f6b7a">Категория</div><input id="libCat" list="libCats" value="${esc(it.cat||'')}" maxlength="60" placeholder="Например, Фото пластика">`:`<b>${esc(it.name)}</b>`}
      <div style="color:#7f6b7a;font-size:13px;margin-top:6px">${it.src==='upload'?'Загружено в библиотеку':'📁 '+esc(src)}${it.where?'<br>📍 '+esc(it.where):''}<br>${esc(size(it.size))}${it.w?' · '+it.w+'×'+it.h+' px':''}${it.t?' · '+esc(day(it.t)):''}</div>
      <div class="rw">${it.src==='upload'?'<button type="button" class="lib-btn" data-a="ren">💾 Сохранить</button>':''}<a class="lib-btn" href="${esc(it.url)}" download="${esc(it.name)}" target="_blank">⬇️ Скачать</a>${it.del?'<button type="button" class="lib-btn" data-a="del" style="background:#fee2e2;color:#dc2626">🗑 Удалить</button>':''}</div>
      ${it.del?(WARN[it.src]?`<div style="color:#7f6b7a;font-size:12.5px;margin-top:8px">При удалении ${esc(WARN[it.src])}.</div>`:''):'<div style="color:#7f6b7a;font-size:12.5px;margin-top:8px">Это главная картинка товара в магазине: она удаляется вместе с товаром в разделе «Товары».</div>'}`;
    info.onclick=async e=>{const b=e.target.closest('[data-a]');if(!b)return;
      try{if(b.dataset.a==='ren'){const id=it.key.slice(3);await req('/api/admin/library/files/'+id,{method:'PATCH',json:{name:info.querySelector('#libName').value,category:info.querySelector('#libCat').value}});cache=null;o.toast&&o.toast('Сохранено')}
        else{if(!confirm(warnText([it])))return;await remove(it);cur=null;info.innerHTML='<div style="color:#7f6b7a;text-align:center;padding:30px 0">Удалено</div>';o.toast&&o.toast('Удалено')}
        await G.load(true);if(cur){cur=G.get(cur.key)||null;cur&&show(cur)}}catch(er){o.toast?o.toast(er.message):alert(er.message)}}}
  return G}

window.Library={list,pick,file,upload,mount,remove,removeMany,warnText,setCategory};
})();
