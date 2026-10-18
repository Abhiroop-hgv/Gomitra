/* the sign-in token lives in this browser only; the server checks it on every call */
const KEY = 'gomitra_token';
export const getToken = () => { try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; } };
export const setToken = (t) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch (e) {} };
export const signOut = () => setToken('');

export async function api(path, opts) {
  const o = Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {});
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  const tok = getToken();
  if (tok) o.headers = Object.assign({}, o.headers, { Authorization: 'Bearer ' + tok });
  const r = await fetch(path, o);
  if (r.status === 401 && path !== '/api/auth/login') { signOut(); window.dispatchEvent(new Event('gomitra-signed-out')); }
  if (!r.ok) { let d = ''; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d || ('HTTP ' + r.status)); }
  return r.json();
}

/* wake the pose service while the person is still on the herd screen; nothing waits for it */
export function warmUp() { try { api('/api/warmup', { method: 'POST' }).catch(() => {}); } catch (e) {} }

const BASE = import.meta.env.BASE_URL;
const img = (name, ext) => BASE + 'img/' + name + '.' + ext;
export const LOGO = img('logo', 'png');
export const MARK = img('mark', 'png');
/* the demo herd's pictures; cows added later carry their own tile and scene */
export const cowImg = (c, k) => (k === 'tile' ? (c.tile || img(c.id + '-tile', 'jpg')) : (c.scene || img(c.id + '-scene', 'jpg')));

export const signIn = (username, password) => api('/api/auth/login', { method: 'POST', body: { username, password } })
  .then((d) => { setToken(d.token); return d; });
