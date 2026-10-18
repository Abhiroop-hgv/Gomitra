import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LangProvider } from './i18n.jsx';
import { api, warmUp, getToken } from './api.js';
import Login from './screens/Login.jsx';
import Herd from './screens/Herd.jsx';
import Detail from './screens/Detail.jsx';
import Report from './screens/Report.jsx';
import Add from './screens/Add.jsx';
import Lab from './screens/Lab.jsx';
import Ask from './screens/Ask.jsx';
import System from './screens/System.jsx';

const freshAsk = (cowId = null) => ({ msgs: [], input: '', busy: false, cowId, listening: false, note: '' });

function Shell() {
  const [screen, setScreen] = useState(getToken() ? 'herd' : 'login');
  const [expired, setExpired] = useState(false);
  const [filter, setFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [reportId, setReportId] = useState(null);
  const [cows, setCows] = useState([]);
  const [sounds, setSounds] = useState(null);
  const [trends, setTrends] = useState({});
  const [samples, setSamples] = useState(null);
  const [status, setStatus] = useState(null);
  const [ingest, setIngest] = useState([]);
  const [addKey, setAddKey] = useState(0);
  const [lab, setLab] = useState({ tab: 'photo', cowId: '', img: null, imgName: '', snd: null, sndName: '', frames: [], walkName: '', result: null, busy: false, note: '' });
  const [ask, setAsk] = useState(freshAsk());
  const screenRef = useRef(screen);
  screenRef.current = screen;

  const loadCows = useCallback(async () => { try { setCows(await api('/api/cows')); } catch (e) { /* keep the last list */ } }, []);
  const loadSounds = useCallback(async () => { try { setSounds(await api('/api/sounds')); } catch (e) {} }, []);
  const loadTrend = useCallback(async (id) => { try { const d = await api('/api/cows/' + encodeURIComponent(id) + '/trends'); setTrends((s) => ({ ...s, [id]: d })); } catch (e) {} }, []);

  /* the server said the sign-in is over (expired or wrong token): back to the sign-in screen */
  useEffect(() => {
    const out = () => { setExpired(true); setScreen('login'); };
    window.addEventListener('gomitra-signed-out', out);
    return () => window.removeEventListener('gomitra-signed-out', out);
  }, []);

  const go = (s) => { setScreen(s); window.scrollTo(0, 0); };

  /* what each screen loads when it opens */
  useEffect(() => {
    if (screen === 'herd' || screen === 'detail' || screen === 'lab') warmUp();
    if (screen === 'herd') { loadCows(); loadSounds(); }
    if (screen === 'detail' && selectedId) { loadTrend(selectedId); loadSounds(); }
    if (screen === 'lab' && !samples) {
      fetch('/static/samples/index.json').then((r) => r.json()).then(setSamples).catch(() => setSamples({ photos: [], sounds: [] }));
    }
    if (screen === 'system') {
      api('/api/status').then(setStatus).catch(() => {});
      api('/api/ingest/recent').then(setIngest).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, selectedId]);

  /* the herd screen refreshes itself while it is open */
  useEffect(() => {
    if (screen !== 'herd') return undefined;
    const id = setInterval(() => { loadCows(); loadSounds(); }, 15000);
    return () => clearInterval(id);
  }, [screen, loadCows, loadSounds]);

  const toHerd = () => { setSelectedId(null); if (window.speechSynthesis) speechSynthesis.cancel(); go('herd'); };
  const resolve = async (id) => { try { await api('/api/cows/' + id + '/resolve', { method: 'POST' }); } catch (x) {} setSelectedId(null); go('herd'); };

  let view;
  switch (screen) {
    case 'login': view = <Login expired={expired} onSignIn={() => { setExpired(false); go('herd'); }} />; break;
    case 'herd':
      view = <Herd cows={cows} sounds={sounds} filter={filter} setFilter={setFilter} go={go}
        onOpen={(id) => { setSelectedId(id); go('detail'); }}
        onAdd={() => { setAddKey((k) => k + 1); go('add'); }}
        onLab={() => { setLab((l) => ({ ...l, result: null })); go('lab'); }}
        onAsk={() => { setAsk((a) => ({ ...a, cowId: null })); go('ask'); }}
        onSoundLab={() => { setLab((l) => ({ ...l, tab: 'sound', result: null })); go('lab'); }} />;
      break;
    case 'detail':
      view = <Detail cows={cows} selectedId={selectedId} sounds={sounds} trends={trends} onBack={toHerd}
        onReport={(id) => { setReportId(id); go('report'); }} onResolve={resolve}
        onAskCow={(id) => { setAsk(freshAsk(id)); go('ask'); }} />;
      break;
    case 'report': view = <Report cowId={reportId} cows={cows} onBack={() => go('detail')} />; break;
    case 'add': view = <Add key={addKey} onBack={toHerd} />; break;
    case 'lab': view = <Lab lab={lab} setLab={setLab} samples={samples} cows={cows} onBack={toHerd} />; break;
    case 'ask': view = <Ask ask={ask} setAsk={setAsk} cows={cows} onBack={toHerd} />; break;
    default: view = <System status={status} ingest={ingest} onBack={toHerd} />;
  }
  return <div id="app" className={screen === 'login' ? 'white' : ''}>{view}</div>;
}

export default function App() {
  return <LangProvider><Shell /></LangProvider>;
}
