import React from 'react';
import { useLang } from '../i18n.jsx';
import { MARK, cowImg } from '../api.js';
import { LangBar, TagChip, IcoAlert, IcoCheck, IcoPlus, eatLow } from '../shared.jsx';

function SoundsCard({ sounds, onOpen }) {
  const { t, lm, ago } = useLang();
  const sc = sounds, has = sc && sc.clips > 0, low = eatLow(sc);
  return (
    <button type="button" className="soundcard" onClick={onOpen}><b>🎙 {t('sounds_today')}</b>
      <span>{has ? t('chew_group', { m: sc.minutes, n: sc.meals }) : t('no_sounds')}</span>
      {low ? <span style={{ color: '#8F1810', fontWeight: 700 }}>{t('eat_low', { p: low })}</span> : null}
      {sc && sc.check_first ? <span style={{ fontWeight: 700 }}>🔎 {lm(sc.check_first)}</span> : null}
      <span>{sc && sc.last_distress ? t('last_distress', { t: ago(sc.last_distress) }) : t('no_distress')}</span></button>
  );
}

export default function Herd({ cows, sounds, filter, setFilter, go, onOpen, onAdd, onLab, onAsk, onSoundLab }) {
  const { t, lm, ago } = useLang();
  const alerts = cows.filter((c) => c.alert), healthy = cows.filter((c) => !c.alert);
  const list = filter === 'alert' ? alerts : filter === 'ok' ? healthy : cows;
  const chip = (key, label, n) => (
    <button type="button" className={'chip' + (filter === key ? ' on' : '')} onClick={() => setFilter(key)} aria-pressed={filter === key}>{label} {n}</button>
  );
  return (
    <>
      <div className="herd-head">
        <div className="row"><div className="brand"><img src={MARK} alt="" /><span className="display" style={{ fontSize: 20, color: '#fff' }}>GoMitra</span></div><LangBar /></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span style={{ fontSize: 16, color: '#C7DACB' }}>{t('good_morning')}</span>
          <h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1, color: '#fff' }}>North field</h1>
          <span style={{ fontSize: 16, color: '#C7DACB' }}>{cows.length} {t('cows')}</span></div>
        <div className="actions">
          <button type="button" className="addbtn" onClick={onAdd}><IcoPlus /><span>{t('add_cow')}</span></button>
          <button type="button" className="sbtn" onClick={onLab}>{t('lab')}</button>
          <button type="button" className="sbtn" onClick={onAsk}>{t('ask')}</button>
        </div>
      </div>
      <div className="body">
        {alerts.length ? (
          <button type="button" className="alertbar" onClick={() => setFilter('alert')}>
            <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true" style={{ flexShrink: 0 }}><path d="M14 3 L26 24 H2 Z" fill="#C8281E" stroke="#C8281E" strokeWidth="2" strokeLinejoin="round" /><path d="M14 10v7" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" /><circle cx="14" cy="20.5" r="1.6" fill="#fff" /></svg>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}><span style={{ fontSize: 18, fontWeight: 700 }}>{alerts.length === 1 ? t('n_need1') : t('n_need', { n: alerts.length })}</span><span style={{ fontSize: 14 }}>{t('tap_only')}</span></div>
          </button>
        ) : null}
        <SoundsCard sounds={sounds} onOpen={onSoundLab} />
        <div className="chips">{chip('all', t('all'), cows.length)}{chip('alert', t('attention'), alerts.length)}{chip('ok', t('healthy'), healthy.length)}</div>
        <div className="grid">
          {list.map((c) => (
            <button key={c.id} type="button" className={'tile' + (c.alert ? ' alert' : '')} onClick={() => onOpen(c.id)}>
              <div className="photo ph" style={{ backgroundImage: `url('${cowImg(c, 'tile')}')` }}><TagChip tag={c.tag} /></div>
              <div className="info"><span className="display nm">{c.name}</span>
                <div className="st">{c.alert ? <IcoAlert n={18} fill="#fff" mark="#C8281E" /> : <IcoCheck n={18} bg="#1B6B3A" ck="#fff" />}<span>{c.alert ? t('attention') : t('healthy')}</span></div>
                <span className="note">{c.alert ? lm(c.short) : t('seen') + ' ' + ago(c.last_seen)}</span></div>
            </button>
          ))}
        </div>
        <button type="button" className="linkbtn" onClick={() => go('system')}>{t('how_built')}</button>
      </div>
    </>
  );
}
