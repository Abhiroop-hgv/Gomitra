import React, { createContext, useContext, useMemo, useState } from 'react';
import T from './strings.js';

export const BCP = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN' };
export const HEALTHY_TEXT = { en: 'Nothing unusual seen today.', hi: 'आज कुछ असामान्य नहीं दिखा।', te: 'ఈ రోజు అసాధారణంగా ఏమీ కనిపించలేదు.' };

const Ctx = createContext(null);
export const useLang = () => useContext(Ctx);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(() => { try { return localStorage.getItem('gm_lang') || 'en'; } catch (e) { return 'en'; } });
  const value = useMemo(() => {
    const t = (k, v) => {
      let s = (T[lang] && T[lang][k] !== undefined) ? T[lang][k] : (T.en[k] !== undefined ? T.en[k] : k);
      if (v && typeof s === 'string') for (const x in v) s = s.replace('{' + x + '}', v[x]);
      return s;
    };
    const lm = (o) => (o && (o[lang] || o.en)) || '';
    const setLang = (l) => { setLangState(l); try { localStorage.setItem('gm_lang', l); } catch (e) {} };
    const ago = (ts) => {
      if (!ts) return '';
      const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
      if (m < 1) return t('just_now');
      if (m < 60) return t('min_ago', { n: m });
      if (m < 1440) return t('h_ago', { n: Math.round(m / 60) });
      return t('d_ago', { n: Math.round(m / 1440) });
    };
    return { lang, setLang, t, lm, ago, chips: T[lang].ask_chips };
  }, [lang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
