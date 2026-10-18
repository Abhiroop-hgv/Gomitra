import React, { useEffect, useRef } from 'react';
import { useLang, BCP } from '../i18n.jsx';
import { api } from '../api.js';
import { TopBack, TraceBox, IcoMic } from '../shared.jsx';

export default function Ask({ ask, setAsk, cows, onBack }) {
  const { t, lang, chips: askChips } = useLang();
  const k = ask, cow = k.cowId ? cows.find((c) => c.id === k.cowId) : null;
  const patch = (o) => setAsk((s) => ({ ...s, ...o }));
  const chatRef = useRef(null);
  const busyRef = useRef(false);
  const inputRef = useRef(null);
  busyRef.current = k.busy;

  useEffect(() => { const c = chatRef.current; if (c && c.lastElementChild) c.lastElementChild.scrollIntoView({ block: 'center' }); }, [k.msgs.length, k.busy]);

  const send = async (q) => {
    q = (q || '').trim(); if (!q || busyRef.current) return;
    busyRef.current = true;
    setAsk((s) => ({ ...s, msgs: [...s.msgs, { role: 'user', text: q }], input: '', busy: true }));
    let msg;
    try {
      const r = await api('/api/ask', { method: 'POST', body: { question: q, lang, cow_id: k.cowId } });
      msg = { role: 'bot', text: r.answer, sources: r.sources, grounded: r.grounded, trace: r.trace };
    } catch (e) { msg = { role: 'bot', text: t('err') }; }
    busyRef.current = false;
    setAsk((s) => ({ ...s, msgs: [...s.msgs, msg], busy: false }));
  };

  const listen = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { patch({ note: t('no_speech') }); return; }
    if (k.listening) return;
    const rec = new SR(); rec.lang = BCP[lang]; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    let heard = '', failed = false, note = t('listening');
    patch({ listening: true, note });
    rec.onresult = (e) => { heard = Array.from(e.results).map((r) => r[0].transcript).join(' ').trim(); patch({ input: heard }); };   // show the words as they are recognised
    rec.onerror = (e) => { failed = true; note = (e.error === 'no-speech' ? t('no_voice') : e.error === 'not-allowed' ? t('mic_blocked') : 'Voice: ' + e.error); };
    rec.onend = () => {
      patch({ listening: false, note: failed ? note : '' });
      if (!failed && heard) send(heard);
    };
    try { rec.start(); } catch (x) { patch({ listening: false, note: 'Voice: ' + x.message }); }
  };
  const speak = (text) => {
    if (!('speechSynthesis' in window)) return;
    speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = BCP[lang]; speechSynthesis.speak(u);
  };

  return (
    <div className="pad" style={{ gap: 14 }}><TopBack onClick={onBack} /><div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>{t('ask_title')}</h1>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.45, color: '#4B5C50' }}>{t('ask_sub')}</p>{cow ? <p className="fine"><b>{cow.name} · {cow.tag}</b></p> : null}</div>
      {!k.msgs.length ? <div className="chips">{askChips.map((q, i) => <button key={i} type="button" className="chip wrap" onClick={() => send(q)}>{q}</button>)}</div> : null}
      {k.note ? <p className="fine" style={{ fontWeight: 700 }}>{k.note}</p> : null}
      <div className="chat" id="chat" ref={chatRef}>
        {k.msgs.map((m, i) => m.role === 'user' ? <div key={i} className="bubble me">{m.text}</div>
          : <div key={i} className="bubble bot">{m.text}{m.sources && m.sources.length ? <div className="src">{t('sources')}: {m.sources.join(', ')}</div> : (m.grounded === false ? <div className="src">{t('not_grounded')}</div> : null)}<TraceBox trace={m.trace} />
            <button type="button" className="say" onClick={() => speak(m.text)}>🔊 {t('read_aloud')}</button></div>)}
        {k.busy ? <div className="bubble bot">{t('thinking')}</div> : null}
      </div>
      <div className="askbar"><input className="input" id="ask-in" type="text" ref={inputRef} placeholder={t('ask_ph')} value={k.input} onChange={(e) => patch({ input: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') send(k.input); }} style={{ flex: 1, minWidth: 0 }} />
        <button type="button" className={'mic' + (k.listening ? ' on' : '')} onClick={listen} aria-label={t('speak')}><IcoMic /></button>
        <button type="button" className="send" onClick={() => send(k.input)}>{t('send')}</button></div></div>
  );
}
