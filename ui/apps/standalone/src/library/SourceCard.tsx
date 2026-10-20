import { SourceArtifacts, SourceKind, SourceMeta, SourcePrimary, SourceState, SourceTitle, sourceAttributes, type SourceViewProps } from "./SourceParts";

export function SourceCard(props: SourceViewProps) {
  return <article className="library-source-card" role="listitem" data-source-id={props.source.sourceId} data-selected={props.selected} data-phase={props.status.phase} {...sourceAttributes(props.source)} onClick={props.onSelect} onDoubleClick={() => { if (!props.action.disabled) props.onPrimary(); }}>
    <div className="library-source-card-top"><SourceKind source={props.source} /><SourceState {...props} bar={false} />{props.menu}</div><SourceTitle {...props} /><SourceMeta {...props} />
    <div className="library-source-card-bottom"><progress aria-label={`${props.source.title} 阅读进度`} value={props.status.ratio * Math.max(1, props.source.progress.total)} max={props.source.progress.total || 1} /><SourceArtifacts {...props} /><SourcePrimary {...props} /></div>
  </article>;
}
