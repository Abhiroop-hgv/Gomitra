import React from 'react';
import { useLang } from '../i18n.jsx';
import { api } from '../api.js';
import { fileToDataURL, framesFromVideo, bufToB64, urlToDataURL } from '../files.js';
import { TopBack, TraceBox, Banner } from '../shared.jsx';

function Bars({ probs }) {
  const { t } = useLang();
  return [['normal', 'p_normal', '#1B6B3A'], ['lumpy', 'p_lumpy', '#C8281E'], ['fmd', 'p_fmd', '#C8281E']].map(([k, lab, col]) => {
    const p = Math.round((probs[k] || 0) * 100);
    return <div key={k} className="bar"><span>{t(lab)}</span><div className="track"><div style={{ width: p + '%', background: col }}></div></div><b>{p}%</b></div>;
  });
}

function PhotoResult({ r }) {
  const { t, lm } = useLang();
  const x = r.results && r.results[0];
  if (!x || !x.usable) return <div className="resbox"><p>{t('unclear')}</p></div>;
  const m = x.message ? lm(x.message) : null;
  return (
    <div className={'resbox ' + (x.finding ? 'bad' : 'good')}><h3 className="display">{t('result')}</h3><Bars probs={x.probs} />
      {x.finding && m ? <Banner m={m} /> : <p style={{ margin: '8px 0 0', fontSize: 17 }}>{t('nothing_found')}</p>}
      {x.cow ? <p className="fine">{t('matched', { name: x.cow.name, how: x.match ? x.match.method : '' })}</p> : <p className="fine">{t('not_recognised')}</p>}
      {x.alert ? <p className="fine"><b>{t('alert_saved')}</b></p> : null}<p className="fine">{t('screening')}</p><TraceBox trace={r.trace} /></div>
  );
}
function SoundResult({ r }) {
  const { t } = useLang();
  const a = r.audio || {};
  if (!a.usable) return <div className="resbox"><p>{t(a.reason === 'silent' ? 'silent' : 'too_short')}</p></div>;
  const d = a.distress || {}, b = a.bite_chew || {};
  const yes = !!r.finding;
  return (
    <div className={'resbox ' + (yes ? 'bad' : 'good')}><h3 className="display">{t('result')}</h3>
      <div className="srow"><div className="l"><b>{t('distress')}</b><span>{yes ? t('distress_yes') : t('distress_no')}</span></div><div className={'pill' + (yes ? ' bad' : '')}><span>{Math.round((d.p_hfc || 0) * 100)}%</span></div></div>
      <div className="srow"><div className="l"><b>{t('chewing')}</b><span>{b.label || ''}</span></div><div className="pill na"><span>{Math.round(Math.max(...Object.values(b.probs || { x: 0 })) * 100)}%</span></div></div>
      {r.alert ? <p className="fine"><b>{t('alert_raised')}</b></p> : (r.note ? <p className="fine">{t('one_clip')}</p> : null)}
      <p className="fine">{t('sound_note')}</p><TraceBox trace={r.trace} /></div>
  );
}
function WalkResult({ r }) {
  const { t, lm } = useLang();
  const g = r.gait || {}, m = r.message ? lm(r.message) : null, label = r.posture && r.posture.label, sc = g.score;
  return (
    <div className={'resbox ' + (sc >= 3 ? 'bad' : sc ? 'good' : '')}><h3 className="display">{t('result')}</h3>
      {r.overlay ? <img className="prev" src={r.overlay} alt="" /> : null}
      {sc ? <div className="srow"><div className="l"><b>{t('walk_score')}</b><span>{t('score_' + sc)}</span></div><div className={'pill' + (sc >= 3 ? ' bad' : '')}><span>{sc} / 5</span></div></div>
        : <p>{t('no_score')}</p>}
      {g.summary ? <p className="fine">{g.summary}</p> : null}
      {['standing', 'sitting', 'lying'].includes(label) ? <div className="srow"><div className="l"><b>{t('posture_word')}</b><span>{t('post_' + label)}</span></div></div> : null}
      {sc >= 3 && m ? <Banner m={m} /> : null}
      {r.alert ? <p className="fine"><b>{t('alert_saved')}</b></p> : null}
      <p className="fine">{r.pose_used ? t('pose_used') : t('gemini_only')}</p>{r.frames === 1 ? <p className="fine">{t('single_note')}</p> : null}
      <p className="fine">{t('screening')}</p><TraceBox trace={r.trace} /></div>
  );
}

const hidden = { position: 'absolute', opacity: 0, width: 1, height: 1 };

export default function Lab({ lab, setLab, samples, cows, onBack }) {
  const { t, lm } = useLang();
  const l = lab, S = samples || { photos: [], sounds: [] };
  const patch = (o) => setLab((s) => ({ ...s, ...o }));
  const tabBtn = (k, label) => <button type="button" className={'chip' + (l.tab === k ? ' on' : '')} onClick={() => patch({ tab: k, result: null })}>{label}</button>;
  const cowSelect = (first) => (
    <div className="field"><label htmlFor="lab-cow">{t('which_cow')}</label>
      <select className="input" id="lab-cow" style={{ padding: '0 12px' }} value={l.cowId} onChange={(e) => patch({ cowId: e.target.value })}>
        <option value="">{first}</option>{cows.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.tag}</option>)}</select></div>
  );

  const samplePhoto = async (file) => { patch({ imgName: file, result: null }); const img = await urlToDataURL('/static/samples/' + file, 1280); patch({ img }); };
  const sampleWalk = async (file) => { patch({ walkName: file, result: null, note: '' }); const f = await urlToDataURL('/static/samples/' + file, 960); patch({ frames: [f] }); };
  const sampleSound = async (file) => { patch({ sndName: file, result: null }); const snd = bufToB64(await (await fetch('/static/samples/' + file)).arrayBuffer()); patch({ snd }); };

  const onPhoto = async (f) => { if (!f) return; patch({ imgName: f.name, result: null }); patch({ img: await fileToDataURL(f, 1280) }); };
  const onWalk = async (fl) => {
    if (!fl.length) return;
    const files = Array.from(fl); patch({ result: null, walkName: files[0].name });
    try {
      let frames;
      if (files[0].type.startsWith('video')) { patch({ note: t('reading_video') }); frames = await framesFromVideo(files[0], 5); }
      else frames = await Promise.all(files.slice(0, 5).map((f) => fileToDataURL(f, 960)));
      patch({ frames, note: '' });
    } catch (e) { patch({ frames: [], note: t('err') }); }
  };
  const onSound = async (f) => { if (!f) return; patch({ sndName: f.name, result: null }); patch({ snd: bufToB64(await f.arrayBuffer()) }); };

  const run = async () => {
    patch({ busy: true, result: null });
    let result = null;
    try {
      result = l.tab === 'photo'
        ? await api('/api/analyze', { method: 'POST', body: { image: l.img, mode: 'photo', cow_id: l.cowId || null } })
        : l.tab === 'walk' ? await api('/api/posture', { method: 'POST', body: { images: l.frames, cow_id: l.cowId || null } })
        : await api('/api/audio', { method: 'POST', body: { audio: l.snd, camera: 'North field camera', immediate: true } });
    } catch (x) { alert(t('err')); }
    patch({ busy: false, result });
  };

  let body;
  if (l.tab === 'photo') {
    body = <>
      <h2 className="sec display">{t('samples')}</h2>
      <div className="samps">{S.photos.map((s) => <button key={s.file} type="button" className={'samp' + (l.imgName === s.file ? ' on' : '')} onClick={() => samplePhoto(s.file)}><img src={'/static/samples/' + s.file} alt="" /><span>{lm(s.label)}</span></button>)}</div>
      <label className="upl" htmlFor="lab-photo">{t('upload_photo')}<input id="lab-photo" type="file" accept="image/*" style={hidden} onChange={(e) => onPhoto(e.target.files[0])} /></label>
      {l.img ? <img className="prev" src={l.img} alt="" /> : null}
      {cowSelect(t('find_face'))}</>;
  } else if (l.tab === 'walk') {
    body = <>
      <h2 className="sec display">{t('samples')}</h2>
      <div className="samps">{(S.walk || []).map((w) => <button key={w.file} type="button" className={'samp' + (l.walkName === w.file ? ' on' : '')} onClick={() => sampleWalk(w.file)}><img src={'/static/samples/' + w.file} alt="" /><span>{lm(w.label)}</span></button>)}</div>
      <label className="upl" htmlFor="lab-walk">{t('upload_walk')}<input id="lab-walk" type="file" accept="video/*,image/*" multiple style={hidden} onChange={(e) => onWalk(e.target.files)} /></label>
      {l.note ? <p className="fine"><b>{l.note}</b></p> : null}
      {l.frames.length ? <div className="thumbs">{l.frames.map((f, i) => <img key={i} src={f} alt="" />)}</div> : null}
      {cowSelect('—')}</>;
  } else {
    body = <>
      <h2 className="sec display">{t('samples')}</h2>
      <div className="samps">{S.sounds.map((s) => <button key={s.file} type="button" className={'samp wide' + (l.sndName === s.file ? ' on' : '')} onClick={() => sampleSound(s.file)}><span>🔊 {lm(s.label)}</span></button>)}</div>
      <label className="upl" htmlFor="lab-snd">{t('upload_sound')}<input id="lab-snd" type="file" accept="audio/*" style={hidden} onChange={(e) => onSound(e.target.files[0])} /></label>
      {l.sndName ? <p className="fine">🔊 {l.sndName}</p> : null}</>;
  }
  const ready = l.tab === 'photo' ? !!l.img : l.tab === 'walk' ? l.frames.length > 0 : !!l.snd;
  const res = l.result ? (l.tab === 'photo' ? <PhotoResult r={l.result} /> : l.tab === 'walk' ? <WalkResult r={l.result} /> : <SoundResult r={l.result} />) : null;
  return (
    <div className="pad" style={{ gap: 16 }}><TopBack onClick={onBack} /><div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>{t('lab_title')}</h1>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.45, color: '#4B5C50' }}>{t('lab_sub')}</p></div>
      <div className="chips">{tabBtn('photo', t('tab_photo'))}{tabBtn('sound', t('tab_sound'))}{tabBtn('walk', t('tab_walk'))}</div>{body}
      <button type="button" className="btn-dark" onClick={run} disabled={!(ready && !l.busy)} style={ready && !l.busy ? undefined : { opacity: 0.5 }}>{l.busy ? t('checking') : t('run_check')}</button>
      {l.busy && l.tab === 'walk' ? <p className="fine">{t('walk_wait')}</p> : null}{res}</div>
  );
}
