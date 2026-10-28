import type { EventArtifactLink } from '../utils/eventArtifacts';

export function ArtifactIcon({ type }: { type: string }) {
  return <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {type === 'code' ? <><path d="m6 5-4 5 4 5m8-10 4 5-4 5m-3-12-2 14" /></> :
      type === 'dataset' ? <><ellipse cx="10" cy="4.5" rx="6.5" ry="2.5" /><path d="M3.5 4.5v11c0 3.3 13 3.3 13 0v-11M3.5 10c0 3.3 13 3.3 13 0" /></> :
      type === 'visualization' ? <><path d="M3 2v15h15M6 13l4-5 3 2 4-6" /><circle cx="10" cy="8" r="1" /></> :
      <><path d="M5 2h7l4 4v12H5ZM12 2v5h4M8 10h5m-5 3h5" /></>}
  </svg>;
}

export default function EventArtifactBadges({ links, onOpen, onMore }: { links: EventArtifactLink[]; onOpen: (id: string) => void; onMore: () => void }) {
  if (!links.length) return null;
  return <div className="event-artifact-badges nodrag nopan" aria-label="关联文件">
    {links.slice(0, 2).map(({ artifact, operations }) => <button key={artifact.artifact_id} type="button" disabled={!artifact.exists} style={{ color: artifact.color }}
      title={`${artifact.label} · ${operations.join('、')}\n${artifact.path}${artifact.exists ? '\n点击打开文件' : '\n文件已不存在或不可用'}`}
      aria-label={`${artifact.exists ? '打开' : '不可打开'}${artifact.label}：${artifact.name}（${operations.join('、')}）`}
      onClick={event => { event.stopPropagation(); onOpen(artifact.artifact_id); }}>
      <ArtifactIcon type={artifact.artifact_type} /><span>{artifact.label}</span>
    </button>)}
    {links.length > 2 && <button type="button" aria-label={`查看全部 ${links.length} 个关联文件`} onClick={event => { event.stopPropagation(); onMore(); }}>+{links.length - 2}</button>}
  </div>;
}

export function EventArtifactList({ links, onOpen }: { links: EventArtifactLink[]; onOpen: (id: string) => void }) {
  return <div className="event-artifact-list">{links.map(({ artifact, operations }) => <button key={artifact.artifact_id} type="button" disabled={!artifact.exists}
    title={artifact.path} aria-label={`打开${artifact.label}：${artifact.name}`} onClick={() => onOpen(artifact.artifact_id)}>
    <span className="event-artifact-list-title" style={{ color: artifact.color }}><ArtifactIcon type={artifact.artifact_type} /><strong>{artifact.label}</strong><span>{artifact.exists ? '打开 ↗' : '文件不可用'}</span></span>
    <span className="event-artifact-list-name">{artifact.name}</span><span className="event-artifact-list-path">{artifact.path}</span>
    <span className="event-artifact-list-operations">{operations.join('、')}</span>
  </button>)}</div>;
}
