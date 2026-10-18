import React from 'react';
import { useLang, HEALTHY_TEXT } from '../i18n.jsx';
import { cowImg } from '../api.js';
import { TopBack, TagChip, IcoAlert, IcoCheck, IcoDash, IcoPhone, eatLow } from '../shared.jsx';

export default function Detail({ cows, selectedId, sounds, trends, onBack, onReport, onResolve, onAskCow }) {
  const { t, lm, ago, lang } = useLang();
  const c = cows.find((x) => x.id === selectedId) || cows[0];
  if (!c) return <div className="pad"><TopBack onClick={onBack} /></div>;
  const sig = c.signals || {}, sc = sounds, tr = trends[c.id] || {}, rt = tr.rest || {}, gt = tr.gait || {};
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
    return (
      <div key={k} className={'srow' + (bad ? ' bad' : '')}><div className="l"><b>{t(k)}</b><span>{txt}</span></div>
        {bad ? <div className="pill bad"><IcoAlert n={16} fill="#fff" mark="#C8281E" /><span>{t('check')}</span></div>
          : kind === 'good' ? <div className="pill"><IcoCheck n={16} bg="#1B6B3A" ck="#fff" /><span>{t('ok')}</span></div>
          : kind === 'group' ? <div className="pill na"><span>{t('group_word')}</span></div>
          : kind === 'warn' ? <div className="pill na"><span>~</span></div>
          : <div className="pill na"><IcoDash n={16} /><span>—</span></div>}
      </div>
    );
  });
  let scene;
  if (c.scene) {
    const b = c.box;
    scene = (
      <div className="scene real" role="img" aria-label={c.name}><img src={c.scene} alt="" />
        {b ? <>
          <div className="box" style={{ left: b[0] * 100 + '%', top: b[1] * 100 + '%', width: (b[2] - b[0]) * 100 + '%', height: (b[3] - b[1]) * 100 + '%' }}></div>
          <div className="lbl" style={{ left: b[0] * 100 + '%', top: `calc(${b[1] * 100}% - 22px)` }}>{lm(c.short)}</div></> : null}
        <div className="cap">{c.camera + ' · ' + ago(c.last_seen)}</div></div>
    );
  } else {
    scene = <div className="scene ph" role="img" aria-label={c.name} style={{ backgroundImage: `url('${cowImg(c, 'scene')}')` }}><div className="cap">{(c.camera || '') + ' · ' + ago(c.last_seen)}</div></div>;
  }
  const m = c.msg ? lm(c.msg) : null;
  const icon = c.alert
    ? <svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true" style={{ flexShrink: 0 }}><path d="M14 3 L26 24 H2 Z" fill="#fff" stroke="#fff" strokeWidth="2" strokeLinejoin="round" /><path d="M14 10v7" stroke="#C8281E" strokeWidth="2.5" strokeLinecap="round" /><circle cx="14" cy="20.5" r="1.6" fill="#C8281E" /></svg>
    : <svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true" style={{ flexShrink: 0 }}><circle cx="14" cy="14" r="12" fill="#fff" /><path d="M8 14.5l4.2 4.2L20 10.5" stroke="#1B6B3A" strokeWidth="2.8" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>;

  const callVet = () => {
    let n = ''; try { n = localStorage.getItem('gm_vet') || ''; } catch (x) {}
    if (!n) { n = prompt(t('vet_prompt')) || ''; try { localStorage.setItem('gm_vet', n); } catch (x) {} }
    if (n) location.href = 'tel:' + n.replace(/[^\d+]/g, '');
  };

  return (
    <div className="pad detail"><TopBack onClick={onBack} /><div className="dcols"><div className="dcol">{scene}
      <div className="row"><div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}><h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>{c.name}</h1>
        <span style={{ fontSize: 16, color: '#4B5C50' }}>{[c.breed, c.age].filter(Boolean).join(' · ')}</span></div><div style={{ flexShrink: 0 }}><TagChip tag={c.tag} lg /></div></div>
      </div><div className="dcol"><div className="banner" style={{ background: c.alert ? '#C8281E' : '#1B6B3A' }}><div className="t display">{icon}<span>{c.alert && m ? m.title : t('healthy')}</span></div>
        <p>{c.alert && m ? m.text : HEALTHY_TEXT[lang]}</p>
        {c.alert && m && m.advice ? <div className="todo"><span style={{ fontSize: 14, fontWeight: 700 }}>{t('what_to_do')}</span><span style={{ fontSize: 16, lineHeight: 1.4 }}>{m.advice}</span></div> : null}</div>
      <h2 className="sec display">{t('camera_sees')}</h2><div className="rows">{rows}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {c.alert ? <>
          <button type="button" className="btn-ink" onClick={callVet}><IcoPhone /><span>{t('call_vet')}</span></button>
          <button type="button" className="btn-line" onClick={() => onReport(c.id)}>{t('vet_report')}</button>
          <button type="button" className="btn-line" onClick={() => onResolve(c.id)}>{t('mark_checked')}</button></> : null}
        <button type="button" className="btn-line" onClick={() => onAskCow(c.id)}>{t('ask_about', { name: c.name })}</button></div>
      {c.alert ? <p className="fine">{t('screening')}</p> : null}
    </div></div></div>
  );
}
