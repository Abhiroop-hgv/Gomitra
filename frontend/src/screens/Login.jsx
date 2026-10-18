import React from 'react';
import { useLang } from '../i18n.jsx';
import { LOGO } from '../api.js';
import { LangBar } from '../shared.jsx';

export default function Login({ onSignIn }) {
  const { t } = useLang();
  return (
    <>
      <div className="login-top"><img src={LOGO} alt="GoMitra" /><p>{t('tagline')}</p><LangBar /></div>
      <div className="sheet">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <h1 className="display" style={{ margin: 0, fontSize: 30, lineHeight: 1.1 }}>{t('signin')}</h1>
          <p style={{ margin: 0, fontSize: 16, lineHeight: 1.4, color: '#4B5C50' }}>{t('signin_sub')}</p>
        </div>
        <div className="field"><label htmlFor="mobile">{t('mobile')}</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 64, height: 56, border: '2px solid #B9C4B2', borderRadius: 14, background: '#F1F4EC', fontSize: 18, color: '#4B5C50' }}>+91</div>
            <input className="input" id="mobile" type="tel" inputMode="numeric" autoComplete="tel-national" style={{ flex: 1, minWidth: 0 }} />
          </div></div>
        <div className="field"><label htmlFor="password">{t('password')}</label>
          <input className="input" id="password" type="password" autoComplete="current-password" />
          <span style={{ fontSize: 14, color: '#4B5C50' }}>{t('demo_hint')}</span></div>
        <button type="button" className="btn-dark" onClick={onSignIn}>{t('signin')}</button>
      </div>
    </>
  );
}
