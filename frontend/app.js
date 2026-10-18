/* ---------- language + helpers ---------- */
let LANG = 'en';
try { LANG = localStorage.getItem('gm_lang') || 'en'; } catch (e) {}
const t = (k, v) => {
  let s = (T[LANG] && T[LANG][k] !== undefined) ? T[LANG][k] : (T.en[k] !== undefined ? T.en[k] : k);
  if (v && typeof s === 'string') for (const x in v) s = s.replace('{' + x + '}', v[x]);
  return s;
};
const lm = (o) => (o && (o[LANG] || o.en)) || '';
const HEALTHY_TEXT = { en: 'Nothing unusual seen today.', hi: 'आज कुछ असामान्य नहीं दिखा।', te: 'ఈ రోజు అసాధారణంగా ఏమీ కనిపించలేదు.' };
const BCP = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN' };
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let COWS = [];
const state = {
  screen: 'login', filter: 'all', selectedId: null, busy: false, toast: '',
  add: { photos: { front: null, left: null, right: null, back: null }, tag: '', name: '', breed: 'Ongole', age: '', done: null, busy: false },
  lab: { tab: 'photo', cowId: '', img: null, imgName: '', snd: null, sndName: '', frames: [], walkName: '', result: null, busy: false, note: '' },
  ask: { msgs: [], input: '', busy: false, cowId: null, listening: false, note: '' },
  samples: null, status: null, sounds: null, trends: {}
};
const app = document.getElementById('app');

async function api(path, opts) {
  const o = Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {});
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  const r = await fetch(path, o);
  if (!r.ok) { let d = ''; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d || ('HTTP ' + r.status)); }
  return r.json();
}
/* wake the pose service while the person is still on the herd screen; nothing waits for it */
function warmUp() { try { fetch('/api/warmup', { method: 'POST' }).catch(() => {}); } catch (e) {} }
async function loadSounds() { try { state.sounds = await api('/api/sounds'); } catch (e) {} }
async function loadTrend(id) { try { state.trends[id] = await api('/api/cows/' + encodeURIComponent(id) + '/trends'); } catch (e) {} }
async function loadCows() { try { COWS = await api('/api/cows'); } catch (e) { /* keep the last list */ } }

function ago(ts) {
  if (!ts) return '';
  const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (m < 1) return t('just_now');
  if (m < 60) return t('min_ago', { n: m });
  if (m < 1440) return t('h_ago', { n: Math.round(m / 60) });
  return t('d_ago', { n: Math.round(m / 1440) });
}
const cowImg = (c, k) => (k === 'tile' ? (c.tile || IMG[c.id + '-tile']) : (c.scene || IMG[c.id + '-scene'])) || '';

function fileToDataURL(file, maxSide) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onerror = reject;
    fr.onload = () => {
      const im = new Image();
      im.onerror = reject;
      im.onload = () => {
        const s = Math.min(1, (maxSide || 1280) / Math.max(im.width, im.height));
        const c = document.createElement('canvas');
        c.width = Math.round(im.width * s); c.height = Math.round(im.height * s);
        c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      im.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}
function framesFromVideo(file, n) {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto'; v.src = URL.createObjectURL(file);
    v.onerror = () => reject(new Error('video'));
    v.onloadedmetadata = async () => {
      const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : 3, out = [];
      const step = Math.max(0.5, Math.min(0.8, dur / (n + 1))), start = Math.max(0, (dur - step * (n - 1)) / 2);
      try {
        for (let i = 0; i < n; i++) {
          const seeked = new Promise((r) => { v.onseeked = r; });
          v.currentTime = Math.min(Math.max(0, dur - 0.05), start + i * step); await seeked;
          const sc = Math.min(1, 960 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement('canvas');
          c.width = Math.round(v.videoWidth * sc); c.height = Math.round(v.videoHeight * sc);
          c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); out.push(c.toDataURL('image/jpeg', 0.85));
        }
        URL.revokeObjectURL(v.src); resolve(out);
      } catch (e) { reject(e); }
    };
  });
}
function bufToB64(buf) {
  const b = new Uint8Array(buf); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}
async function urlToDataURL(url, maxSide) { const b = await (await fetch(url)).blob(); return fileToDataURL(b, maxSide); }

/* ---------- icons ---------- */
const icoAlert = (n, fill, mark) => `<svg width="${n}" height="${n}" viewBox="0 0 18 18" aria-hidden="true" style="flex-shrink:0"><path d="M9 2 L17 16 H1 Z" fill="${fill}" stroke="${fill}" stroke-width="1.5" stroke-linejoin="round"/><path d="M9 7v4" stroke="${mark}" stroke-width="2" stroke-linecap="round"/><circle cx="9" cy="13.4" r="1" fill="${mark}"/></svg>`;
const icoCheck = (n, bg, ck) => `<svg width="${n}" height="${n}" viewBox="0 0 18 18" aria-hidden="true" style="flex-shrink:0"><circle cx="9" cy="9" r="8" fill="${bg}"/><path d="M5 9.5l2.7 2.7L13 6.8" stroke="${ck}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const icoDash = (n) => `<svg width="${n}" height="${n}" viewBox="0 0 18 18" aria-hidden="true" style="flex-shrink:0"><circle cx="9" cy="9" r="8" fill="#9AA89C"/><path d="M5.5 9h7" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`;
const icoBack = `<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4 6.5 10l6 6" stroke="#15221A" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const icoPlus = `<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 3v14M3 10h14" stroke="#1A1400" stroke-width="2.5" stroke-linecap="round" fill="none"/></svg>`;
const icoPhone = `<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3h4l1.5 4-2.2 1.4a11 11 0 0 0 5.3 5.3L15 11.5l4 1.5v4a2 2 0 0 1-2 2A14 14 0 0 1 3 5a2 2 0 0 1 2-2z" stroke="#fff" stroke-width="2" fill="none" stroke-linejoin="round"/></svg>`;
const icoMic = `<svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><rect x="8" y="2" width="6" height="11" rx="3" fill="#fff"/><path d="M4 10a7 7 0 0 0 14 0M11 17v3" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`;
const tagChip = (tag, lg) => `<span class="tagchip${lg ? ' lg' : ''}"><i></i><span>${esc(tag)}</span></span>`;
const langBar = () => `<div class="langs" role="group" aria-label="Language">${[['en', 'EN'], ['hi', 'हिं'], ['te', 'తె']].map(([k, l]) => `<button type="button" class="lang${LANG === k ? ' on' : ''}" data-action="lang" data-lang="${k}" aria-pressed="${LANG === k}">${l}</button>`).join('')}</div>`;
const topBack = (label) => `<button type="button" class="back" data-action="back">${icoBack}<span>${esc(label || t('back_all'))}</span></button>`;

/* ---------- screens ---------- */
function loginScreen() {
  return `
  <div class="login-top"><img src="${IMG.logo}" alt="GoMitra"><p>${t('tagline')}</p>${langBar()}</div>
  <div class="sheet">
    <div style="display:flex;flex-direction:column;gap:6px">
      <h1 class="display" style="margin:0;font-size:30px;line-height:1.1">${t('signin')}</h1>
      <p style="margin:0;font-size:16px;line-height:1.4;color:#4B5C50">${t('signin_sub')}</p>
    </div>
    <div class="field"><label for="mobile">${t('mobile')}</label>
      <div style="display:flex;gap:8px"><div style="display:flex;align-items:center;justify-content:center;width:64px;height:56px;border:2px solid #B9C4B2;border-radius:14px;background:#F1F4EC;font-size:18px;color:#4B5C50">+91</div>
      <input class="input" id="mobile" type="tel" inputmode="numeric" autocomplete="tel-national" style="flex:1;min-width:0"></div></div>
    <div class="field"><label for="password">${t('password')}</label><input class="input" id="password" type="password" autocomplete="current-password">
      <span style="font-size:14px;color:#4B5C50">${t('demo_hint')}</span></div>
    <button type="button" class="btn-dark" data-action="signin">${t('signin')}</button>
  </div>`;
}

function soundsCard() {
  const sc = state.sounds, has = sc && sc.clips > 0;
  return `<button type="button" class="soundcard" data-action="soundlab"><b>🎙 ${t('sounds_today')}</b>
    <span>${has ? t('chew_group', { m: sc.minutes, n: sc.meals }) : t('no_sounds')}</span>
    ${eatLow(sc) ? `<span style="color:#8F1810;font-weight:700">${t('eat_low', { p: eatLow(sc) })}</span>` : ''}
    ${sc && sc.check_first ? `<span style="font-weight:700">🔎 ${esc(lm(sc.check_first))}</span>` : ''}
    <span>${sc && sc.last_distress ? t('last_distress', { t: ago(sc.last_distress) }) : t('no_distress')}</span></button>`;
}
/* % below the group's usual chewing, or 0 when there is no clear drop */
const eatLow = (sc) => (sc && sc.trend && sc.trend.flag && sc.trend.ratio != null ? Math.round((1 - sc.trend.ratio) * 100) : 0);
function herdScreen() {
  const alerts = COWS.filter((c) => c.alert), healthy = COWS.filter((c) => !c.alert);
  const list = state.filter === 'alert' ? alerts : state.filter === 'ok' ? healthy : COWS;
  const chip = (key, label, n) => `<button type="button" class="chip${state.filter === key ? ' on' : ''}" data-action="filter" data-filter="${key}" aria-pressed="${state.filter === key}">${label} ${n}</button>`;
  const banner = alerts.length ? `
    <button type="button" class="alertbar" data-action="filter" data-filter="alert">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true" style="flex-shrink:0"><path d="M14 3 L26 24 H2 Z" fill="#C8281E" stroke="#C8281E" stroke-width="2" stroke-linejoin="round"/><path d="M14 10v7" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/><circle cx="14" cy="20.5" r="1.6" fill="#fff"/></svg>
      <div style="display:flex;flex-direction:column;gap:2px;flex:1;min-width:0"><span style="font-size:18px;font-weight:700">${alerts.length === 1 ? t('n_need1') : t('n_need', { n: alerts.length })}</span><span style="font-size:14px">${t('tap_only')}</span></div>
    </button>` : '';
  const tiles = list.map((c) => `
    <button type="button" class="tile${c.alert ? ' alert' : ''}" data-action="open" data-id="${esc(c.id)}">
      <div class="photo ph" style="background-image:url('${cowImg(c, 'tile')}')">${tagChip(c.tag)}</div>
      <div class="info"><span class="display nm">${esc(c.name)}</span>
        <div class="st">${c.alert ? icoAlert(18, '#fff', '#C8281E') : icoCheck(18, '#1B6B3A', '#fff')}<span>${c.alert ? t('attention') : t('healthy')}</span></div>
        <span class="note">${esc(c.alert ? lm(c.short) : t('seen') + ' ' + ago(c.last_seen))}</span></div>
    </button>`).join('');
  return `
  <div class="herd-head">
    <div class="row"><div class="brand"><img src="${IMG.mark}" alt=""><span class="display" style="font-size:20px;color:#fff">GoMitra</span></div>${langBar()}</div>
    <div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:16px;color:#C7DACB">${t('good_morning')}</span>
      <h1 class="display" style="margin:0;font-size:32px;line-height:1.1;color:#fff">North field</h1>
      <span style="font-size:16px;color:#C7DACB">${COWS.length} ${t('cows')}</span></div>
    <div class="actions">
      <button type="button" class="addbtn" data-action="add">${icoPlus}<span>${t('add_cow')}</span></button>
      <button type="button" class="sbtn" data-action="lab">${t('lab')}</button>
      <button type="button" class="sbtn" data-action="ask">${t('ask')}</button>
    </div>
  </div>
  <div class="body">${banner}
    ${soundsCard()}
    <div class="chips">${chip('all', t('all'), COWS.length)}${chip('alert', t('attention'), alerts.length)}${chip('ok', t('healthy'), healthy.length)}</div>
    <div class="grid">${tiles}</div>
    <button type="button" class="linkbtn" data-action="system">${t('how_built')}</button>
  </div>`;
}

function detailScreen() {
  const c = COWS.find((x) => x.id === state.selectedId) || COWS[0];
  if (!c) return `<div class="pad">${topBack()}</div>`;
  const sig = c.signals || {}, sc = state.sounds, tr = state.trends[c.id] || {}, rt = tr.rest || {}, gt = tr.gait || {};
  const rowOf = (k) => {
    if (k === 'skin') return sig.skin === 'check' ? ['bad', t('skin_check')] : sig.skin === 'ok' ? ['good', t('skin_ok')] : ['na', t('not_checked')];
    if (k === 'walking') {
      if (sig.walking === 'check') return ['bad', t('limping_signs')];
      if (gt.flag) return ['bad', t('gait_rising', { s: gt.scores.join(' → ') })];
      return sig.walking === 'watch' ? ['warn', t('steps_uneven')] : sig.walking === 'ok' ? ['good', t('walk_ok')] : ['na', t('not_checked')];
    }
    if (k === 'resting') {
      if (rt.today != null && rt.base != null) return [rt.flag ? 'bad' : 'good', t(rt.flag ? 'rest_high' : 'rest_usual', { a: Math.round(rt.today * 100), b: Math.round(rt.base * 100) })];
      return ['standing', 'sitting', 'lying'].includes(sig.resting) ? ['good', t('post_' + sig.resting)] : ['na', t('not_checked')];
    }
    if (eatLow(sc)) return ['bad', t('eat_low_group', { p: eatLow(sc) })];
    return sc && sc.clips > 0 ? ['group', t('chew_group', { m: sc.minutes, n: sc.meals })] : ['na', t('not_checked')];
  };
  const rows = ['walking', 'eating', 'resting', 'skin'].map((k) => {
    const [kind, txt] = rowOf(k), bad = kind === 'bad';
    return `<div class="srow${bad ? ' bad' : ''}"><div class="l"><b>${t(k)}</b><span>${esc(txt)}</span></div>
      ${bad ? `<div class="pill bad">${icoAlert(16, '#fff', '#C8281E')}<span>${t('check')}</span></div>`
        : kind === 'good' ? `<div class="pill">${icoCheck(16, '#1B6B3A', '#fff')}<span>${t('ok')}</span></div>`
        : kind === 'group' ? `<div class="pill na"><span>${t('group_word')}</span></div>`
        : kind === 'warn' ? `<div class="pill na"><span>~</span></div>`
        : `<div class="pill na">${icoDash(16)}<span>—</span></div>`}</div>`;
  }).join('');
  let scene;
  if (c.scene) {
    const b = c.box;
    const box = b ? `<div class="box" style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${(b[2] - b[0]) * 100}%;height:${(b[3] - b[1]) * 100}%"></div>
      <div class="lbl" style="left:${b[0] * 100}%;top:calc(${b[1] * 100}% - 22px)">${esc(lm(c.short))}</div>` : '';
    scene = `<div class="scene real" role="img" aria-label="${esc(c.name)}"><img src="${c.scene}" alt="">${box}<div class="cap">${esc(c.camera + ' · ' + ago(c.last_seen))}</div></div>`;
  } else {
    scene = `<div class="scene ph" role="img" aria-label="${esc(c.name)}" style="background-image:url('${cowImg(c, 'scene')}')"><div class="cap">${esc((c.camera || '') + ' · ' + ago(c.last_seen))}</div></div>`;
  }
  const m = c.msg ? lm(c.msg) : null;
  const icon = c.alert
    ? `<svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true" style="flex-shrink:0"><path d="M14 3 L26 24 H2 Z" fill="#fff" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M14 10v7" stroke="#C8281E" stroke-width="2.5" stroke-linecap="round"/><circle cx="14" cy="20.5" r="1.6" fill="#C8281E"/></svg>`
    : `<svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true" style="flex-shrink:0"><circle cx="14" cy="14" r="12" fill="#fff"/><path d="M8 14.5l4.2 4.2L20 10.5" stroke="#1B6B3A" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  return `<div class="pad">${topBack()}${scene}
    <div class="row"><div style="display:flex;flex-direction:column;gap:2px;min-width:0"><h1 class="display" style="margin:0;font-size:32px;line-height:1.1">${esc(c.name)}</h1>
      <span style="font-size:16px;color:#4B5C50">${esc([c.breed, c.age].filter(Boolean).join(' · '))}</span></div><div style="flex-shrink:0">${tagChip(c.tag, true)}</div></div>
    <div class="banner" style="background:${c.alert ? '#C8281E' : '#1B6B3A'}"><div class="t display">${icon}<span>${esc(c.alert && m ? m.title : t('healthy'))}</span></div>
      <p>${esc(c.alert && m ? m.text : HEALTHY_TEXT[LANG])}</p>
      ${c.alert && m && m.advice ? `<div class="todo"><span style="font-size:14px;font-weight:700">${t('what_to_do')}</span><span style="font-size:16px;line-height:1.4">${esc(m.advice)}</span></div>` : ''}</div>
    <h2 class="sec display">${t('camera_sees')}</h2><div class="rows">${rows}</div>
    <div style="display:flex;flex-direction:column;gap:12px">
      ${c.alert ? `<button type="button" class="btn-ink" data-action="callvet">${icoPhone}<span>${t('call_vet')}</span></button>
      <button type="button" class="btn-line" data-action="report" data-id="${esc(c.id)}">${t('vet_report')}</button>
      <button type="button" class="btn-line" data-action="resolve" data-id="${esc(c.id)}">${t('mark_checked')}</button>` : ''}
      <button type="button" class="btn-line" data-action="askcow" data-id="${esc(c.id)}">${t('ask_about', { name: esc(c.name) })}</button></div>
    ${c.alert ? `<p class="fine">${t('screening')}</p>` : ''}
  </div>`;
}

async function loadReport() {
  const r = state.report; if (!r) return;
  r.busy = true; r.error = false; r.copied = false; render(false);
  try { r.data = await api('/api/cows/' + encodeURIComponent(r.id) + '/report?lang=' + LANG); }
  catch (e) { r.error = true; }
  r.busy = false; if (state.screen === 'report' && state.report === r) render(false);
}
function reportScreen() {
  const r = state.report || {}, c = COWS.find((x) => x.id === r.id) || {}, d = r.data;
  const body = r.busy ? `<p style="margin:0;font-size:17px">${t('report_loading')}</p>`
    : r.error || !d ? `<p style="margin:0;font-size:17px;color:#8F1810">${t('report_failed')}</p>`
    : `<h3>${esc(d.cow)}</h3><p style="margin:0;font-size:17px;line-height:1.5;white-space:pre-wrap">${esc(d.note)}</p>
       <p class="fine">${d.source === 'gemini' ? t('report_gemini') : t('report_plain')}</p>${traceBox(d.trace)}`;
  return `<div class="pad"><button type="button" class="back" data-action="backcow">${icoBack}<span>${esc(c.name || t('back_all'))}</span></button>
    <h1 class="display" style="margin:0;font-size:30px;line-height:1.1">${t('vet_report')}</h1>
    <p class="fine">${t('report_sub')}</p>
    <div class="resbox">${body}</div>
    ${d && !r.busy ? `<div style="display:flex;flex-direction:column;gap:12px">
      <button type="button" class="btn-ink" data-action="sharereport">${t('report_share')}</button>
      <button type="button" class="btn-line" data-action="copyreport">${r.copied ? t('report_copied') : t('report_copy')}</button></div>` : ''}
    <p class="fine">${t('screening')}</p></div>`;
}

const SLOTS = [['front', 'front'], ['left', 'left'], ['right', 'right'], ['back', 'back']];
const slotIcon = (k) => {
  const open = '<svg width="80" height="56" viewBox="0 0 80 56" fill="none" stroke="#4B5C50" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  if (k === 'front') return open + '><path d="M30 8 Q40 4 50 8 Q56 22 48 40 Q40 46 32 40 Q24 22 30 8Z"/><path d="M28 12 Q18 8 14 14 M52 12 Q62 8 66 14"/><path d="M32 6 Q28 0 24 2 M48 6 Q52 0 56 2"/><ellipse cx="40" cy="38" rx="9" ry="6"/></svg>';
  if (k === 'back') return open + '><rect x="26" y="10" width="28" height="30" rx="13"/><path d="M33 40v12M47 40v12"/><path d="M40 12v22"/><path d="M26 14l-6-4M54 14l6-4"/></svg>';
  return open + (k === 'right' ? ' style="transform:scaleX(-1)"' : '') + '><rect x="24" y="14" width="44" height="22" rx="10"/><path d="M30 36v14M38 36v14M56 36v14M62 36v14"/><ellipse cx="16" cy="22" rx="9" ry="8"/><path d="M68 18q6 8 4 20"/></svg>';
};
const BREEDS = ['Ongole', 'Gir', 'Sahiwal', 'Deoni', 'Holstein-Friesian cross', 'Jersey cross', 'Other'];

function addState() {
  const a = state.add, count = SLOTS.filter((s) => a.photos[s[0]]).length, missing = 4 - count, hasTag = a.tag.trim().length > 0;
  let label = t('register');
  if (a.busy) label = t('registering'); else if (missing > 0) label = t('more_photos', { n: missing }); else if (!hasTag) label = t('enter_tag');
  return { count, ready: missing === 0 && hasTag && !a.busy, label };
}

function addScreen() {
  const a = state.add, top = topBack();
  if (a.done) {
    const d = a.done;
    return `<div class="pad">${top}<div class="donecard">
      <svg width="48" height="48" viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="13" fill="#1B6B3A"/><path d="M8 14.5l4.2 4.2L20 10.5" stroke="#fff" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <h2 class="display" style="margin:0;font-size:28px;line-height:1.15">${t('cow_added')}</h2>${tagChip(d.cow.tag, true)}
      <p style="margin:0;font-size:17px;line-height:1.45;color:#4B5C50">${t('is_registered', { name: esc(d.cow.name) })} ${t('faces_found', { n: d.faces_found })}</p>
      ${d.faces_found === 0 ? `<p class="fine" style="color:#8F1810">${t('no_face')}</p>` : ''}
      <button type="button" class="btn-dark" data-action="back">${t('back_herd')}</button></div></div>`;
  }
  const st = addState();
  const slots = SLOTS.map(([k]) => {
    const src = a.photos[k];
    return `<div class="slotwrap"><input id="photo-${k}" type="file" accept="image/*" data-slot="${k}">
      <label for="photo-${k}" class="slot${src ? ' done' : ''}">${src
        ? `<img src="${src}" alt=""><div class="ok">${icoCheck(16, '#fff', '#1B6B3A')}<span>${t(k)}</span></div>`
        : `${slotIcon(k)}<span style="font-size:18px;font-weight:700">${t(k)}</span><span style="font-size:14px;color:#4B5C50">${t('tap_add')}</span>`}</label></div>`;
  }).join('');
  return `<div class="pad" style="gap:20px">${top}
    <div style="display:flex;flex-direction:column;gap:6px"><h1 class="display" style="margin:0;font-size:32px;line-height:1.1">${t('add_title')}</h1>
      <p style="margin:0;font-size:16px;line-height:1.45;color:#4B5C50">${t('add_sub')}</p></div>
    <div style="display:flex;flex-direction:column;gap:8px"><div class="row"><span style="font-size:16px;font-weight:700">${t('photos')}</span><span style="font-size:16px;font-weight:700;color:#1E4A2F">${st.count} / 4</span></div>
      <div class="progress"><div style="width:${st.count * 25}%"></div></div></div>
    <div class="slots">${slots}</div>
    <div style="display:flex;flex-direction:column;gap:16px"><h2 class="display" style="margin:0;font-size:20px;line-height:1.2">${t('details')}</h2>
      <div class="field"><label for="tag">${t('ear_tag')}</label>
        <input id="tag" type="text" inputmode="numeric" placeholder="0417" value="${esc(a.tag)}" style="width:100%;height:60px;border:2px solid #8A6F00;border-radius:14px;background:#FFD21F;padding:0 16px;font-family:'Archivo',system-ui,sans-serif;font-weight:800;font-size:26px;letter-spacing:.06em;color:#1A1400">
        <span style="font-size:14px;color:#4B5C50">${t('tag_help')}</span></div>
      <div class="field"><label for="cow-name">${t('name_opt')}</label><input class="input" id="cow-name" type="text" value="${esc(a.name)}"></div>
      <div class="field"><label for="breed">${t('breed')}</label><select class="input" id="breed" style="padding:0 12px">${BREEDS.map((b) => `<option value="${b}"${a.breed === b ? ' selected' : ''}>${b}</option>`).join('')}</select></div>
      <div class="field"><label for="age">${t('age')}</label><input class="input" id="age" type="number" min="0" inputmode="numeric" value="${esc(a.age)}"></div></div>
    <button type="button" class="regbtn" id="register-btn" data-action="register"></button></div>`;
}
function refreshRegister() {
  const btn = document.getElementById('register-btn'); if (!btn) return;
  const st = addState(); btn.textContent = st.label; btn.disabled = !st.ready;
  btn.style.background = st.ready ? '#1E4A2F' : '#C9D2C4'; btn.style.color = st.ready ? '#fff' : '#4B5C50'; btn.style.cursor = st.ready ? 'pointer' : 'not-allowed';
}

/* ---------- test lab ---------- */
function bars(probs) {
  const rows = [['normal', 'p_normal', '#1B6B3A'], ['lumpy', 'p_lumpy', '#C8281E'], ['fmd', 'p_fmd', '#C8281E']];
  return rows.map(([k, lab, col]) => { const p = Math.round((probs[k] || 0) * 100);
    return `<div class="bar"><span>${t(lab)}</span><div class="track"><div style="width:${p}%;background:${col}"></div></div><b>${p}%</b></div>`; }).join('');
}
/* "Behind this result": the real services this request used and how long each step took (measured by the router) */
function traceBox(tr) {
  if (!tr || !tr.length) return '';
  const total = tr.reduce((s, x) => s + x.ms, 0);
  return `<details class="trace"><summary>${t('behind')}</summary>${tr.map((x) => `<div class="trow"><b>${esc(x.service)}</b><span>${esc(x.detail)}</span><i>${(x.ms / 1000).toFixed(1)} s</i></div>`).join('')}
    <div class="trow"><b>${t('trace_total')}</b><span></span><i>${(total / 1000).toFixed(1)} s</i></div><p class="fine">${t('trace_note')}</p></details>`;
}
function photoResult(r) {
  const x = r.results && r.results[0];
  if (!x) return `<div class="resbox"><p>${t('unclear')}</p></div>`;
  if (!x.usable) return `<div class="resbox"><p>${t('unclear')}</p></div>`;
  const m = x.message ? lm(x.message) : null;
  const who = x.cow ? `<p class="fine">${t('matched', { name: esc(x.cow.name), how: esc(x.match ? x.match.method : '') })}</p>` : `<p class="fine">${t('not_recognised')}</p>`;
  return `<div class="resbox ${x.finding ? 'bad' : 'good'}"><h3 class="display">${t('result')}</h3>${bars(x.probs)}
    ${x.finding && m ? `<div class="banner" style="background:#C8281E"><div class="t display"><span>${esc(m.title)}</span></div><p>${esc(m.text)}</p><div class="todo"><span style="font-size:14px;font-weight:700">${t('what_to_do')}</span><span style="font-size:16px;line-height:1.4">${esc(m.advice)}</span></div></div>`
      : `<p style="margin:8px 0 0;font-size:17px">${t('nothing_found')}</p>`}
    ${who}${x.alert ? `<p class="fine"><b>${t('alert_saved')}</b></p>` : ''}<p class="fine">${t('screening')}</p>${traceBox(r.trace)}</div>`;
}
function soundResult(r) {
  const a = r.audio || {};
  if (!a.usable) return `<div class="resbox"><p>${t(a.reason === 'silent' ? 'silent' : 'too_short')}</p></div>`;
  const d = a.distress || {}, b = a.bite_chew || {};
  const yes = !!r.finding;
  return `<div class="resbox ${yes ? 'bad' : 'good'}"><h3 class="display">${t('result')}</h3>
    <div class="srow"><div class="l"><b>${t('distress')}</b><span>${yes ? t('distress_yes') : t('distress_no')}</span></div><div class="pill ${yes ? 'bad' : ''}"><span>${Math.round((d.p_hfc || 0) * 100)}%</span></div></div>
    <div class="srow"><div class="l"><b>${t('chewing')}</b><span>${esc(b.label || '')}</span></div><div class="pill na"><span>${Math.round(Math.max(...Object.values(b.probs || { x: 0 })) * 100)}%</span></div></div>
    ${r.alert ? `<p class="fine"><b>${t('alert_raised')}</b></p>` : (r.note ? `<p class="fine">${t('one_clip')}</p>` : '')}
    <p class="fine">${t('sound_note')}</p>${traceBox(r.trace)}</div>`;
}
function walkResult(r) {
  const g = r.gait || {}, m = r.message ? lm(r.message) : null, label = r.posture && r.posture.label, sc = g.score;
  return `<div class="resbox ${sc >= 3 ? 'bad' : sc ? 'good' : ''}"><h3 class="display">${t('result')}</h3>
    ${r.overlay ? `<img class="prev" src="${r.overlay}" alt="">` : ''}
    ${sc ? `<div class="srow"><div class="l"><b>${t('walk_score')}</b><span>${esc(t('score_' + sc))}</span></div><div class="pill ${sc >= 3 ? 'bad' : ''}"><span>${sc} / 5</span></div></div>`
         : `<p>${t('no_score')}</p>`}
    ${g.summary ? `<p class="fine">${esc(g.summary)}</p>` : ''}
    ${['standing', 'sitting', 'lying'].includes(label) ? `<div class="srow"><div class="l"><b>${t('posture_word')}</b><span>${t('post_' + label)}</span></div></div>` : ''}
    ${sc >= 3 && m ? `<div class="banner" style="background:#C8281E"><div class="t display"><span>${esc(m.title)}</span></div><p>${esc(m.text)}</p><div class="todo"><span style="font-size:14px;font-weight:700">${t('what_to_do')}</span><span style="font-size:16px;line-height:1.4">${esc(m.advice)}</span></div></div>` : ''}
    ${r.alert ? `<p class="fine"><b>${t('alert_saved')}</b></p>` : ''}
    <p class="fine">${r.pose_used ? t('pose_used') : t('gemini_only')}</p>${r.frames === 1 ? `<p class="fine">${t('single_note')}</p>` : ''}
    <p class="fine">${t('screening')}</p>${traceBox(r.trace)}</div>`;
}
function labScreen() {
  const l = state.lab, S = state.samples || { photos: [], sounds: [] };
  const tabs = `<div class="chips"><button type="button" class="chip${l.tab === 'photo' ? ' on' : ''}" data-action="labtab" data-tab="photo">${t('tab_photo')}</button><button type="button" class="chip${l.tab === 'sound' ? ' on' : ''}" data-action="labtab" data-tab="sound">${t('tab_sound')}</button><button type="button" class="chip${l.tab === 'walk' ? ' on' : ''}" data-action="labtab" data-tab="walk">${t('tab_walk')}</button></div>`;
  let body;
  if (l.tab === 'photo') {
    const th = S.photos.map((s) => `<button type="button" class="samp${l.imgName === s.file ? ' on' : ''}" data-action="samplephoto" data-file="${esc(s.file)}"><img src="/static/samples/${esc(s.file)}" alt=""><span>${esc(lm(s.label))}</span></button>`).join('');
    body = `<h2 class="sec display">${t('samples')}</h2><div class="samps">${th}</div>
      <label class="upl" for="lab-photo">${t('upload_photo')}<input id="lab-photo" type="file" accept="image/*" style="position:absolute;opacity:0;width:1px;height:1px"></label>
      ${l.img ? `<img class="prev" src="${l.img}" alt="">` : ''}
      <div class="field"><label for="lab-cow">${t('which_cow')}</label><select class="input" id="lab-cow" style="padding:0 12px"><option value="">${t('find_face')}</option>${COWS.map((c) => `<option value="${esc(c.id)}"${l.cowId === c.id ? ' selected' : ''}>${esc(c.name)} · ${esc(c.tag)}</option>`).join('')}</select></div>`;
  } else if (l.tab === 'walk') {
    const th = (S.walk || []).map((w) => `<button type="button" class="samp${l.walkName === w.file ? ' on' : ''}" data-action="samplewalk" data-file="${esc(w.file)}"><img src="/static/samples/${esc(w.file)}" alt=""><span>${esc(lm(w.label))}</span></button>`).join('');
    body = `<h2 class="sec display">${t('samples')}</h2><div class="samps">${th}</div>
      <label class="upl" for="lab-walk">${t('upload_walk')}<input id="lab-walk" type="file" accept="video/*,image/*" multiple style="position:absolute;opacity:0;width:1px;height:1px"></label>
      ${l.note ? `<p class="fine"><b>${esc(l.note)}</b></p>` : ''}
      ${l.frames.length ? `<div class="thumbs">${l.frames.map((f) => `<img src="${f}" alt="">`).join('')}</div>` : ''}
      <div class="field"><label for="lab-cow">${t('which_cow')}</label><select class="input" id="lab-cow" style="padding:0 12px"><option value="">—</option>${COWS.map((c) => `<option value="${esc(c.id)}"${l.cowId === c.id ? ' selected' : ''}>${esc(c.name)} · ${esc(c.tag)}</option>`).join('')}</select></div>`;
  } else {
    const th = S.sounds.map((s) => `<button type="button" class="samp wide${l.sndName === s.file ? ' on' : ''}" data-action="samplesound" data-file="${esc(s.file)}"><span>🔊 ${esc(lm(s.label))}</span></button>`).join('');
    body = `<h2 class="sec display">${t('samples')}</h2><div class="samps">${th}</div>
      <label class="upl" for="lab-snd">${t('upload_sound')}<input id="lab-snd" type="file" accept="audio/*" style="position:absolute;opacity:0;width:1px;height:1px"></label>
      ${l.sndName ? `<p class="fine">🔊 ${esc(l.sndName)}</p>` : ''}`;
  }
  const ready = l.tab === 'photo' ? !!l.img : l.tab === 'walk' ? l.frames.length > 0 : !!l.snd;
  const res = l.result ? (l.tab === 'photo' ? photoResult(l.result) : l.tab === 'walk' ? walkResult(l.result) : soundResult(l.result)) : '';
  return `<div class="pad" style="gap:16px">${topBack()}<div style="display:flex;flex-direction:column;gap:6px"><h1 class="display" style="margin:0;font-size:32px;line-height:1.1">${t('lab_title')}</h1>
    <p style="margin:0;font-size:16px;line-height:1.45;color:#4B5C50">${t('lab_sub')}</p></div>${tabs}${body}
    <button type="button" class="btn-dark" data-action="runlab" ${ready && !l.busy ? '' : 'disabled'} style="${ready && !l.busy ? '' : 'opacity:.5'}">${l.busy ? t('checking') : t('run_check')}</button>${l.busy && l.tab === 'walk' ? `<p class="fine">${t('walk_wait')}</p>` : ''}${res}</div>`;
}

/* ---------- ask GoMitra ---------- */
function askScreen() {
  const k = state.ask, cow = k.cowId ? COWS.find((c) => c.id === k.cowId) : null;
  const msgs = k.msgs.map((m, i) => m.role === 'user' ? `<div class="bubble me">${esc(m.text)}</div>`
    : `<div class="bubble bot">${esc(m.text)}${m.sources && m.sources.length ? `<div class="src">${t('sources')}: ${m.sources.map(esc).join(', ')}</div>` : (m.grounded === false ? `<div class="src">${t('not_grounded')}</div>` : '')}${traceBox(m.trace)}
      <button type="button" class="say" data-action="say" data-i="${i}">🔊 ${t('read_aloud')}</button></div>`).join('');
  const chips = !k.msgs.length ? `<div class="chips">${T[LANG].ask_chips.map((q, i) => `<button type="button" class="chip wrap" data-action="chip" data-i="${i}">${esc(q)}</button>`).join('')}</div>` : '';
  return `<div class="pad" style="gap:14px">${topBack()}<div style="display:flex;flex-direction:column;gap:6px"><h1 class="display" style="margin:0;font-size:32px;line-height:1.1">${t('ask_title')}</h1>
    <p style="margin:0;font-size:16px;line-height:1.45;color:#4B5C50">${t('ask_sub')}</p>${cow ? `<p class="fine"><b>${esc(cow.name)} · ${esc(cow.tag)}</b></p>` : ''}</div>
    ${chips}${k.note ? `<p class="fine" style="font-weight:700">${esc(k.note)}</p>` : ''}<div class="chat" id="chat">${msgs}${k.busy ? `<div class="bubble bot">${t('thinking')}</div>` : ''}</div>
    <div class="askbar"><input class="input" id="ask-in" type="text" placeholder="${esc(t('ask_ph'))}" value="${esc(k.input)}" style="flex:1;min-width:0">
      <button type="button" class="mic${k.listening ? ' on' : ''}" data-action="mic" aria-label="${t('speak')}">${icoMic}</button>
      <button type="button" class="send" data-action="send">${t('send')}</button></div></div>`;
}
async function sendQuestion(q) {
  q = (q || '').trim(); if (!q || state.ask.busy) return;
  state.ask.msgs.push({ role: 'user', text: q }); state.ask.input = ''; state.ask.busy = true; render(false); scrollChat();
  try {
    const r = await api('/api/ask', { method: 'POST', body: { question: q, lang: LANG, cow_id: state.ask.cowId } });
    state.ask.msgs.push({ role: 'bot', text: r.answer, sources: r.sources, grounded: r.grounded, trace: r.trace });
  } catch (e) { state.ask.msgs.push({ role: 'bot', text: t('err') }); }
  state.ask.busy = false; render(false); scrollChat();
}
function scrollChat() { const c = document.getElementById('chat'); if (c && c.lastElementChild) c.lastElementChild.scrollIntoView({ block: 'center' }); }
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { state.ask.note = t('no_speech'); render(false); return; }
  if (state.ask.listening) return;
  const rec = new SR(); rec.lang = BCP[LANG]; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
  let heard = '', failed = false;
  state.ask.listening = true; state.ask.note = t('listening'); render(false);
  rec.onresult = (e) => {
    heard = Array.from(e.results).map((r) => r[0].transcript).join(' ').trim();
    state.ask.input = heard;
    const el = document.getElementById('ask-in'); if (el) el.value = heard;      // show the words as they are recognised
  };
  rec.onerror = (e) => { failed = true; state.ask.note = (e.error === 'no-speech' ? t('no_voice') : e.error === 'not-allowed' ? t('mic_blocked') : 'Voice: ' + e.error); };
  rec.onend = () => {
    state.ask.listening = false;
    if (!failed) state.ask.note = '';
    render(false);
    if (!failed && heard) sendQuestion(heard);
  };
  try { rec.start(); } catch (x) { state.ask.listening = false; state.ask.note = 'Voice: ' + x.message; render(false); }
}
function speak(text) {
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = BCP[LANG]; speechSynthesis.speak(u);
}

/* ---------- system ---------- */
function systemScreen() {
  const s = state.status;
  const run = s ? ({ vertex: 'Vertex AI endpoint', cloudrun: 'Cloud Run', local: 'local' }[s.infer_backend] || s.infer_backend) : '…';
  const live = s ? `<div class="rows"><div class="srow"><div class="l"><b>${t('models_on')}</b><span>${esc(run)}</span></div></div>
    <div class="srow"><div class="l"><b>${t('gemini_on')}</b><span>${esc(s.gemini_model)} (Vertex AI)</span></div></div>
    <div class="srow"><div class="l"><b>${t('cowsn')}</b><span>${s.cows}</span></div></div>
    <div class="srow"><div class="l"><b>${t('docs')}</b><span>${Object.keys(s.kb_sources || {}).length}</span></div></div></div>` : `<p>${t('loading')}</p>`;
  const flow = [['Raspberry Pi', 'Captures frames and sound, uploads them. No AI on the device.'], ['Cloud Run (router)', 'Receives uploads, matches the cow, applies alert rules, keeps history.'],
    ['Vertex AI / Cloud Run (models)', 'Lumpy skin and foot-and-mouth screening, cow face recognition, distress and chewing sounds.'], ['Gemini on Vertex AI', 'Writes the alert and next steps in English, Hindi and Telugu, using vet documents.'],
    ['Firestore', 'Cows, alerts and the vet-document library.'], ['Vertex AI embeddings', 'Finds the right vet-document passage, even when the question is in Telugu or Hindi.'],
    ['Cloud Build + Artifact Registry', 'Builds and stores the model containers.']];
  return `<div class="pad" style="gap:16px">${topBack()}<h1 class="display" style="margin:0;font-size:32px;line-height:1.1">${t('sys_title')}</h1>
    <h2 class="sec display">${t('sys_live')}</h2>${live}
    <h2 class="sec display">${t('dev_title')}</h2>
    <div class="rows">${(state.ingest || []).length ? state.ingest.map((e) => `<div class="srow"><div class="l"><b>${esc(e.camera)} · ${ago(e.ts)}</b><span>${esc(e.summary)}</span><span class="fine">→ ${esc((e.steps || []).join(' → '))}</span>${(e.decisions || []).length ? `<details class="trace"><summary>${t('agent_decisions')}</summary>${e.decisions.map((d) => `<div class="trow"><span>${esc(d)}</span></div>`).join('')}</details>` : ''}</div></div>`).join('')
      : `<div class="srow"><div class="l"><span>${t('dev_none')}</span></div></div>`}</div>
    <div class="rows">${flow.map(([a, b]) => `<div class="srow"><div class="l"><b>${a}</b><span>${b}</span></div></div>`).join('')}</div>
    <p class="fine">Screening aid only. Not a diagnosis. Sound models are not yet validated on real farms.</p></div>`;
}

/* ---------- render + events ---------- */
function render(scrollTop) {
  app.className = state.screen === 'login' ? 'white' : '';
  const s = state.screen;
  app.innerHTML = s === 'login' ? loginScreen() : s === 'herd' ? herdScreen() : s === 'detail' ? detailScreen() : s === 'add' ? addScreen()
    : s === 'lab' ? labScreen() : s === 'ask' ? askScreen() : s === 'report' ? reportScreen() : systemScreen();
  if (s === 'add') refreshRegister();
  if (scrollTop) window.scrollTo(0, 0);
}
async function go(screen) {
  state.screen = screen; render(true);
  if (screen === 'herd' || screen === 'detail' || screen === 'lab') warmUp();
  if (screen === 'herd') { await Promise.all([loadCows(), loadSounds()]); if (state.screen === 'herd') render(false); }
  if (screen === 'detail' && state.selectedId) { const id = state.selectedId; await Promise.all([loadTrend(id), loadSounds()]); if (state.screen === 'detail' && state.selectedId === id) render(false); }
  if (screen === 'lab' && !state.samples) { try { state.samples = await (await fetch('/static/samples/index.json')).json(); render(false); } catch (e) { state.samples = { photos: [], sounds: [] }; } }
  if (screen === 'system') {
    try { state.status = await api('/api/status'); render(false); } catch (e) {}
    try { state.ingest = await api('/api/ingest/recent'); if (state.screen === 'system') render(false); } catch (e) {}
  }
}

app.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]'); if (!el) return;
  const a = el.dataset.action;
  if (a === 'lang') { LANG = el.dataset.lang; try { localStorage.setItem('gm_lang', LANG); } catch (x) {} render(false); if (state.screen === 'report') loadReport(); }
  else if (a === 'report') { state.report = { id: el.dataset.id, data: null, busy: true, error: false, copied: false }; go('report'); loadReport(); }
  else if (a === 'backcow') go('detail');
  else if (a === 'sharereport') { const d = state.report.data; if (d) window.open('https://wa.me/?text=' + encodeURIComponent('GoMitra · ' + d.cow + '\n' + d.note), '_blank'); }
  else if (a === 'copyreport') {
    const d = state.report.data; if (!d) return;
    try { await navigator.clipboard.writeText('GoMitra · ' + d.cow + '\n' + d.note); state.report.copied = true; } catch (x) { prompt(t('report_copy'), d.note); }
    render(false);
  }
  else if (a === 'signin') go('herd');
  else if (a === 'filter') { state.filter = el.dataset.filter; render(false); }
  else if (a === 'open') { state.selectedId = el.dataset.id; go('detail'); }
  else if (a === 'back') { state.selectedId = null; state.add.done = null; if (window.speechSynthesis) speechSynthesis.cancel(); go('herd'); }
  else if (a === 'add') { state.add = { photos: { front: null, left: null, right: null, back: null }, tag: '', name: '', breed: 'Ongole', age: '', done: null, busy: false }; go('add'); }
  else if (a === 'lab') { state.lab.result = null; go('lab'); }
  else if (a === 'ask') { state.ask.cowId = null; go('ask'); }
  else if (a === 'askcow') { state.ask = { msgs: [], input: '', busy: false, cowId: el.dataset.id, listening: false }; go('ask'); }
  else if (a === 'system') go('system');
  else if (a === 'soundlab') { state.lab.tab = 'sound'; state.lab.result = null; go('lab'); }
  else if (a === 'callvet') {
    let n = ''; try { n = localStorage.getItem('gm_vet') || ''; } catch (x) {}
    if (!n) { n = prompt(t('vet_prompt')) || ''; try { localStorage.setItem('gm_vet', n); } catch (x) {} }
    if (n) location.href = 'tel:' + n.replace(/[^\d+]/g, '');
  }
  else if (a === 'resolve') { try { await api('/api/cows/' + el.dataset.id + '/resolve', { method: 'POST' }); } catch (x) {} state.selectedId = null; go('herd'); }
  else if (a === 'register') {
    if (!addState().ready) return;
    state.add.busy = true; refreshRegister();
    try { state.add.done = await api('/api/cows', { method: 'POST', body: { name: state.add.name, tag: state.add.tag, breed: state.add.breed, age: state.add.age, photos: state.add.photos } }); }
    catch (x) { alert(t('err')); }
    state.add.busy = false; render(true);
  }
  else if (a === 'labtab') { state.lab.tab = el.dataset.tab; state.lab.result = null; render(false); }
  else if (a === 'samplephoto') { state.lab.imgName = el.dataset.file; state.lab.result = null; state.lab.img = await urlToDataURL('/static/samples/' + el.dataset.file, 1280); render(false); }
  else if (a === 'samplewalk') { state.lab.walkName = el.dataset.file; state.lab.result = null; state.lab.note = ''; state.lab.frames = [await urlToDataURL('/static/samples/' + el.dataset.file, 960)]; render(false); }
  else if (a === 'samplesound') { state.lab.sndName = el.dataset.file; state.lab.result = null; state.lab.snd = bufToB64(await (await fetch('/static/samples/' + el.dataset.file)).arrayBuffer()); render(false); }
  else if (a === 'runlab') {
    const l = state.lab; l.busy = true; l.result = null; render(false);
    try {
      l.result = l.tab === 'photo'
        ? await api('/api/analyze', { method: 'POST', body: { image: l.img, mode: 'photo', cow_id: l.cowId || null } })
        : l.tab === 'walk' ? await api('/api/posture', { method: 'POST', body: { images: l.frames, cow_id: l.cowId || null } })
        : await api('/api/audio', { method: 'POST', body: { audio: l.snd, camera: 'North field camera', immediate: true } });
    } catch (x) { l.result = null; alert(t('err')); }
    l.busy = false; render(false);
  }
  else if (a === 'send') sendQuestion(state.ask.input);
  else if (a === 'chip') sendQuestion(T[LANG].ask_chips[+el.dataset.i]);
  else if (a === 'mic') listen();
  else if (a === 'say') speak(state.ask.msgs[+el.dataset.i].text);
});
app.addEventListener('input', (e) => {
  const x = e.target;
  if (state.screen === 'add') { if (x.id === 'tag') state.add.tag = x.value; else if (x.id === 'cow-name') state.add.name = x.value; else if (x.id === 'age') state.add.age = x.value; else return; refreshRegister(); }
  else if (state.screen === 'ask' && x.id === 'ask-in') state.ask.input = x.value;
});
app.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.id === 'ask-in') sendQuestion(state.ask.input); });
app.addEventListener('change', async (e) => {
  const x = e.target;
  if (state.screen === 'add') {
    if (x.id === 'breed') { state.add.breed = x.value; return; }
    if (x.matches('input[type=file][data-slot]') && x.files[0]) { state.add.photos[x.dataset.slot] = await fileToDataURL(x.files[0], 1280); render(false); }
  } else if (state.screen === 'lab') {
    if (x.id === 'lab-cow') state.lab.cowId = x.value;
    else if (x.id === 'lab-photo' && x.files[0]) { state.lab.imgName = x.files[0].name; state.lab.result = null; state.lab.img = await fileToDataURL(x.files[0], 1280); render(false); }
    else if (x.id === 'lab-walk' && x.files.length) {
      const files = Array.from(x.files); state.lab.result = null; state.lab.walkName = files[0].name;
      try {
        if (files[0].type.startsWith('video')) { state.lab.note = t('reading_video'); render(false); state.lab.frames = await framesFromVideo(files[0], 5); }
        else state.lab.frames = await Promise.all(files.slice(0, 5).map((f) => fileToDataURL(f, 960)));
        state.lab.note = '';
      } catch (e) { state.lab.frames = []; state.lab.note = t('err'); }
      render(false);
    }
    else if (x.id === 'lab-snd' && x.files[0]) { state.lab.sndName = x.files[0].name; state.lab.result = null; state.lab.snd = bufToB64(await x.files[0].arrayBuffer()); render(false); }
  }
});
setInterval(async () => { if (state.screen === 'herd') { const before = JSON.stringify(COWS.map((c) => [c.id, c.alert, c.last_seen])); await Promise.all([loadCows(), loadSounds()]); if (state.screen === 'herd' && before !== JSON.stringify(COWS.map((c) => [c.id, c.alert, c.last_seen]))) render(false); } }, 15000);
render(true);
