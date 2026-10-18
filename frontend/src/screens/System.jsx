import React from 'react';
import { useLang } from '../i18n.jsx';
import { TopBack } from '../shared.jsx';

const FLOW = [['Raspberry Pi', 'Captures frames and sound, uploads them. No AI on the device.'], ['Cloud Run (router)', 'Receives uploads, matches the cow, applies alert rules, keeps history.'],
  ['Vertex AI / Cloud Run (models)', 'Lumpy skin and foot-and-mouth screening, cow face recognition, distress and chewing sounds.'], ['Gemini on Vertex AI', 'Writes the alert and next steps in English, Hindi and Telugu, using vet documents.'],
  ['Firestore', 'Cows, alerts and the vet-document library.'], ['Vertex AI embeddings', 'Finds the right vet-document passage, even when the question is in Telugu or Hindi.'],
  ['Cloud Build + Artifact Registry', 'Builds and stores the model containers.']];

export default function System({ status: s, ingest, onBack }) {
  const { t, ago } = useLang();
  const run = s ? ({ vertex: 'Vertex AI endpoint', cloudrun: 'Cloud Run', local: 'local' }[s.infer_backend] || s.infer_backend) : '…';
  const live = s ? (
    <div className="rows"><div className="srow"><div className="l"><b>{t('models_on')}</b><span>{run}</span></div></div>
      <div className="srow"><div className="l"><b>{t('gemini_on')}</b><span>{s.gemini_model} (Vertex AI)</span></div></div>
      <div className="srow"><div className="l"><b>{t('cowsn')}</b><span>{s.cows}</span></div></div>
      <div className="srow"><div className="l"><b>{t('docs')}</b><span>{Object.keys(s.kb_sources || {}).length}</span></div></div></div>
  ) : <p>{t('loading')}</p>;
  return (
    <div className="pad" style={{ gap: 16 }}><TopBack onClick={onBack} /><h1 className="display" style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>{t('sys_title')}</h1>
      <h2 className="sec display">{t('sys_live')}</h2>{live}
      <h2 className="sec display">{t('dev_title')}</h2>
      <div className="rows">{(ingest || []).length ? ingest.map((e, i) => (
        <div key={i} className="srow"><div className="l"><b>{e.camera} · {ago(e.ts)}</b><span>{e.summary}</span><span className="fine">→ {(e.steps || []).join(' → ')}</span>
          {(e.decisions || []).length ? <details className="trace"><summary>{t('agent_decisions')}</summary>{e.decisions.map((d, j) => <div key={j} className="trow"><span>{d}</span></div>)}</details> : null}</div></div>
      )) : <div className="srow"><div className="l"><span>{t('dev_none')}</span></div></div>}</div>
      <div className="rows">{FLOW.map(([a, b]) => <div key={a} className="srow"><div className="l"><b>{a}</b><span>{b}</span></div></div>)}</div>
      <p className="fine">Screening aid only. Not a diagnosis. Sound models are not yet validated on real farms.</p></div>
  );
}
