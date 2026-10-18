import React, { useState } from 'react';
import { useLang } from '../i18n.jsx';
import { api } from '../api.js';
import { fileToDataURL } from '../files.js';
import { TopBack, TagChip, IcoCheck } from '../shared.jsx';

const SLOTS = ['front', 'left', 'right', 'back'];
const BREEDS = ['Ongole', 'Gir', 'Sahiwal', 'Deoni', 'Holstein-Friesian cross', 'Jersey cross', 'Other'];

function SlotIcon({ k }) {
  const p = { width: 80, height: 56, viewBox: '0 0 80 56', fill: 'none', stroke: '#4B5C50', strokeWidth: 2.5, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
  if (k === 'front') return <svg {...p}><path d="M30 8 Q40 4 50 8 Q56 22 48 40 Q40 46 32 40 Q24 22 30 8Z" /><path d="M28 12 Q18 8 14 14 M52 12 Q62 8 66 14" /><path d="M32 6 Q28 0 24 2 M48 6 Q52 0 56 2" /><ellipse cx="40" cy="38" rx="9" ry="6" /></svg>;
  if (k === 'back') return <svg {...p}><rect x="26" y="10" width="28" height="30" rx="13" /><path d="M33 40v12M47 40v12" /><path d="M40 12v22" /><path d="M26 14l-6-4M54 14l6-4" /></svg>;
  return <svg {...p} style={k === 'right' ? { transform: 'scaleX(-1)' } : undefined}><rect x="24" y="14" width="44" height="22" rx="10" /><path d="M30 36v14M38 36v14M56 36v14M62 36v14" /><ellipse cx="16" cy="22" rx="9" ry="8" /><path d="M68 18q6 8 4 20" /></svg>;
}

export default function Add({ onBack }) {
  const { t } = useLang();
  const [a, setA] = useState({ photos: { front: null, left: null, right: null, back: null }, tag: '', name: '', breed: 'Ongole', age: '', done: null, busy: false });
  const patch = (o) => setA((s) => ({ ...s, ...o }));
  const top = <TopBack onClick={onBack} />;

  if (a.done) {
    const d = a.done;
    return (
      <div className="pad">{top}<div className="donecard">
        <svg width="48" height="48" viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="13" fill="#1B6B3A" /><path d="M8 14.5l4.2 4.2L20 10.5" stroke="#fff" strokeWidth="2.8" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
        <h2 className="display" style={{ margin: 0, fontSize: 28, lineHeight: 1.15 }}>{t('cow_added')}</h2><TagChip tag={d.cow.tag} lg />
        <p style={{ margin: 0, fontSize: 17, lineHeight: 1.45, color: '#4B5C50' }}>{t('is_registered', { name: d.cow.name })} {t('faces_found', { n: d.faces_found })}</p>
        {d.faces_found === 0 ? <p className="fine" style={{ color: '#8F1810' }}>{t('no_face')}</p> : null}
        <button type="button" className="btn-dark" onClick={onBack}>{t('back_herd')}</button></div></div>
    );
  }

  const count = SLOTS.filter((k) => a.photos[k]).length, missing = 4 - count, hasTag = a.tag.trim().length > 0;
  const ready = missing === 0 && hasTag && !a.busy;
  let label = t('register');
  if (a.busy) label = t('registering'); else if (missing > 0) label = t('more_photos', { n: missing }); else if (!hasTag) label = t('enter_tag');

  const pick = async (k, file) => {
    if (!file) return;
    const src = await fileToDataURL(file, 1280);
    setA((s) => ({ ...s, photos: { ...s.photos, [k]: src } }));
  };
  const register = async () => {
    if (!ready) return;
    patch({ busy: true });
    let done = null;
    try { done = await api('/api/cows', { method: 'POST', body: { name: a.name, tag: a.tag, breed: a.breed, age: a.age, photos: a.photos } }); }
    catch (x) { alert(t('err')); }
    patch({ busy: false, done });
    window.scrollTo(0, 0);
  };

  return (
    <div className="pad" style={{ gap: 20 }}>{top}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>{t('add_title')}</h1>
        <p style={{ margin: 0, fontSize: 16, lineHeight: 1.45, color: '#4B5C50' }}>{t('add_sub')}</p></div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}><div className="row"><span style={{ fontSize: 16, fontWeight: 700 }}>{t('photos')}</span><span style={{ fontSize: 16, fontWeight: 700, color: '#1E4A2F' }}>{count} / 4</span></div>
        <div className="progress"><div style={{ width: count * 25 + '%' }}></div></div></div>
      <div className="slots">
        {SLOTS.map((k) => {
          const src = a.photos[k];
          return (
            <div key={k} className="slotwrap"><input id={'photo-' + k} type="file" accept="image/*" onChange={(e) => pick(k, e.target.files[0])} />
              <label htmlFor={'photo-' + k} className={'slot' + (src ? ' done' : '')}>{src
                ? <><img src={src} alt="" /><div className="ok"><IcoCheck n={16} bg="#fff" ck="#1B6B3A" /><span>{t(k)}</span></div></>
                : <><SlotIcon k={k} /><span style={{ fontSize: 18, fontWeight: 700 }}>{t(k)}</span><span style={{ fontSize: 14, color: '#4B5C50' }}>{t('tap_add')}</span></>}</label></div>
          );
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}><h2 className="display" style={{ margin: 0, fontSize: 20, lineHeight: 1.2 }}>{t('details')}</h2>
        <div className="field"><label htmlFor="tag">{t('ear_tag')}</label>
          <input id="tag" type="text" inputMode="numeric" placeholder="0417" value={a.tag} onChange={(e) => patch({ tag: e.target.value })} style={{ width: '100%', height: 60, border: '2px solid #8A6F00', borderRadius: 14, background: '#FFD21F', padding: '0 16px', fontFamily: "'Archivo',system-ui,sans-serif", fontWeight: 800, fontSize: 26, letterSpacing: '.06em', color: '#1A1400' }} />
          <span style={{ fontSize: 14, color: '#4B5C50' }}>{t('tag_help')}</span></div>
        <div className="field"><label htmlFor="cow-name">{t('name_opt')}</label><input className="input" id="cow-name" type="text" value={a.name} onChange={(e) => patch({ name: e.target.value })} /></div>
        <div className="field"><label htmlFor="breed">{t('breed')}</label><select className="input" id="breed" style={{ padding: '0 12px' }} value={a.breed} onChange={(e) => patch({ breed: e.target.value })}>{BREEDS.map((b) => <option key={b} value={b}>{b}</option>)}</select></div>
        <div className="field"><label htmlFor="age">{t('age')}</label><input className="input" id="age" type="number" min="0" inputMode="numeric" value={a.age} onChange={(e) => patch({ age: e.target.value })} /></div></div>
      <button type="button" className="regbtn" id="register-btn" onClick={register} disabled={!ready}
        style={{ background: ready ? '#1E4A2F' : '#C9D2C4', color: ready ? '#fff' : '#4B5C50', cursor: ready ? 'pointer' : 'not-allowed' }}>{label}</button></div>
  );
}
