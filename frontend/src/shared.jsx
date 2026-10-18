import React from 'react';
import { useLang } from './i18n.jsx';

const svgBase = { 'aria-hidden': true };
export const IcoAlert = ({ n, fill, mark }) => (
  <svg width={n} height={n} viewBox="0 0 18 18" {...svgBase} style={{ flexShrink: 0 }}><path d="M9 2 L17 16 H1 Z" fill={fill} stroke={fill} strokeWidth="1.5" strokeLinejoin="round" /><path d="M9 7v4" stroke={mark} strokeWidth="2" strokeLinecap="round" /><circle cx="9" cy="13.4" r="1" fill={mark} /></svg>
);
export const IcoCheck = ({ n, bg, ck }) => (
  <svg width={n} height={n} viewBox="0 0 18 18" {...svgBase} style={{ flexShrink: 0 }}><circle cx="9" cy="9" r="8" fill={bg} /><path d="M5 9.5l2.7 2.7L13 6.8" stroke={ck} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const IcoDash = ({ n }) => (
  <svg width={n} height={n} viewBox="0 0 18 18" {...svgBase} style={{ flexShrink: 0 }}><circle cx="9" cy="9" r="8" fill="#9AA89C" /><path d="M5.5 9h7" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg>
);
export const IcoBack = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" {...svgBase}><path d="M12.5 4 6.5 10l6 6" stroke="#15221A" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const IcoPlus = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" {...svgBase}><path d="M10 3v14M3 10h14" stroke="#1A1400" strokeWidth="2.5" strokeLinecap="round" fill="none" /></svg>
);
export const IcoPhone = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" {...svgBase}><path d="M5 3h4l1.5 4-2.2 1.4a11 11 0 0 0 5.3 5.3L15 11.5l4 1.5v4a2 2 0 0 1-2 2A14 14 0 0 1 3 5a2 2 0 0 1 2-2z" stroke="#fff" strokeWidth="2" fill="none" strokeLinejoin="round" /></svg>
);
export const IcoMic = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" {...svgBase}><rect x="8" y="2" width="6" height="11" rx="3" fill="#fff" /><path d="M4 10a7 7 0 0 0 14 0M11 17v3" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" /></svg>
);

export const TagChip = ({ tag, lg }) => (
  <span className={'tagchip' + (lg ? ' lg' : '')}><i></i><span>{tag}</span></span>
);

export function LangBar() {
  const { lang, setLang } = useLang();
  return (
    <div className="langs" role="group" aria-label="Language">
      {[['en', 'EN'], ['hi', 'हिं'], ['te', 'తె']].map(([k, l]) => (
        <button key={k} type="button" className={'lang' + (lang === k ? ' on' : '')} onClick={() => setLang(k)} aria-pressed={lang === k}>{l}</button>
      ))}
    </div>
  );
}

export function TopBack({ label, onClick }) {
  const { t } = useLang();
  return <button type="button" className="back" onClick={onClick}><IcoBack /><span>{label || t('back_all')}</span></button>;
}

/* "Behind this result": the real services this request used and how long each step took (measured by the router) */
export function TraceBox({ trace }) {
  const { t } = useLang();
  if (!trace || !trace.length) return null;
  const total = trace.reduce((s, x) => s + x.ms, 0);
  return (
    <details className="trace"><summary>{t('behind')}</summary>
      {trace.map((x, i) => <div key={i} className="trow"><b>{x.service}</b><span>{x.detail}</span><i>{(x.ms / 1000).toFixed(1)} s</i></div>)}
      <div className="trow"><b>{t('trace_total')}</b><span></span><i>{(total / 1000).toFixed(1)} s</i></div>
      <p className="fine">{t('trace_note')}</p>
    </details>
  );
}

/* % below the group's usual chewing, or 0 when there is no clear drop */
export const eatLow = (sc) => (sc && sc.trend && sc.trend.flag && sc.trend.ratio != null ? Math.round((1 - sc.trend.ratio) * 100) : 0);

export function Banner({ m }) {
  const { t } = useLang();
  return (
    <div className="banner" style={{ background: '#C8281E' }}>
      <div className="t display"><span>{m.title}</span></div><p>{m.text}</p>
      <div className="todo"><span style={{ fontSize: 14, fontWeight: 700 }}>{t('what_to_do')}</span><span style={{ fontSize: 16, lineHeight: 1.4 }}>{m.advice}</span></div>
    </div>
  );
}
