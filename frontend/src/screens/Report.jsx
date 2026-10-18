import React, { useEffect, useRef, useState } from 'react';
import { useLang } from '../i18n.jsx';
import { api } from '../api.js';
import { IcoBack, TraceBox } from '../shared.jsx';

export default function Report({ cowId, cows, onBack }) {
  const { t, lang } = useLang();
  const [r, setR] = useState({ data: null, busy: true, error: false, copied: false });
  const seq = useRef(0);
  const c = cows.find((x) => x.id === cowId) || {};

  useEffect(() => {
    const my = ++seq.current;
    setR({ data: null, busy: true, error: false, copied: false });
    api('/api/cows/' + encodeURIComponent(cowId) + '/report?lang=' + lang)
      .then((data) => { if (seq.current === my) setR({ data, busy: false, error: false, copied: false }); })
      .catch(() => { if (seq.current === my) setR({ data: null, busy: false, error: true, copied: false }); });
  }, [cowId, lang]);

  const d = r.data;
  const share = () => { if (d) window.open('https://wa.me/?text=' + encodeURIComponent('GoMitra · ' + d.cow + '\n' + d.note), '_blank'); };
  const copy = async () => {
    if (!d) return;
    let ok = false;
    try { await navigator.clipboard.writeText('GoMitra · ' + d.cow + '\n' + d.note); ok = true; } catch (x) { prompt(t('report_copy'), d.note); }
    if (ok) setR((s) => ({ ...s, copied: true }));
  };
  const body = r.busy ? <p style={{ margin: 0, fontSize: 17 }}>{t('report_loading')}</p>
    : r.error || !d ? <p style={{ margin: 0, fontSize: 17, color: '#8F1810' }}>{t('report_failed')}</p>
    : <><h3>{d.cow}</h3><p style={{ margin: 0, fontSize: 17, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{d.note}</p>
        <p className="fine">{d.source === 'gemini' ? t('report_gemini') : t('report_plain')}</p><TraceBox trace={d.trace} /></>;
  return (
    <div className="pad"><button type="button" className="back" onClick={onBack}><IcoBack /><span>{c.name || t('back_all')}</span></button>
      <h1 className="display" style={{ margin: 0, fontSize: 30, lineHeight: 1.1 }}>{t('vet_report')}</h1>
      <p className="fine">{t('report_sub')}</p>
      <div className="resbox">{body}</div>
      {d && !r.busy ? <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button type="button" className="btn-ink" onClick={share}>{t('report_share')}</button>
        <button type="button" className="btn-line" onClick={copy}>{r.copied ? t('report_copied') : t('report_copy')}</button></div> : null}
      <p className="fine">{t('screening')}</p></div>
  );
}
