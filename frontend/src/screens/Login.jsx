import React, { useState } from 'react';
import { useLang } from '../i18n.jsx';
import { LOGO, signIn } from '../api.js';
import { LangBar } from '../shared.jsx';

export default function Login({ onSignIn, expired }) {
  const { t } = useLang();
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(expired ? t('session_over') : '');
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try { await signIn(user, pass); onSignIn(); }
    catch (x) { setErr(x.message && !/^HTTP|Failed to fetch/.test(x.message) ? x.message : t('login_failed')); }
    setBusy(false);
  };
  return (
    <>
      <div className="login-top"><img src={LOGO} alt="GoMitra" /><p>{t('tagline')}</p><LangBar /></div>
      <div className="sheet">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <h1 className="display" style={{ margin: 0, fontSize: 30, lineHeight: 1.1 }}>{t('signin')}</h1>
          <p style={{ margin: 0, fontSize: 16, lineHeight: 1.4, color: '#4B5C50' }}>{t('signin_sub')}</p>
        </div>
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className="field"><label htmlFor="username">{t('mobile')}</label>
            <input className="input" id="username" autoComplete="username" autoCapitalize="none" value={user} onChange={(e) => setUser(e.target.value)} /></div>
          <div className="field"><label htmlFor="password">{t('password')}</label>
            <input className="input" id="password" type="password" autoComplete="current-password" value={pass} onChange={(e) => setPass(e.target.value)} />
            <span style={{ fontSize: 14, color: '#4B5C50' }}>{t('demo_hint')}</span></div>
          {err && <div role="alert" style={{ color: '#B3261E', fontSize: 16 }}>{err}</div>}
          <button type="submit" className="btn-dark" disabled={busy || !user || !pass}>{busy ? t('signing_in') : t('signin')}</button>
        </form>
      </div>
    </>
  );
}
