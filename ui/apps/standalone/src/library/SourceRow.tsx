import { SourceArtifacts, SourceKind, SourceMeta, SourcePrimary, SourceState, SourceTitle, sourceAttributes, type SourceViewProps } from "./SourceParts";

export function SourceRow(props: SourceViewProps) {
  return <article className="library-source-row" role="listitem" data-source-id={props.source.sourceId} data-selected={props.selected} data-phase={props.status.phase} {...sourceAttributes(props.source)} onClick={props.onSelect} onDoubleClick={() => { if (!props.action.disabled) props.onPrimary(); }}>
    <SourceKind source={props.source} /><div className="library-source-main"><SourceTitle {...props} /><SourceMeta {...props} /></div><SourceState {...props} /><SourceArtifacts {...props} /><SourcePrimary {...props} />{props.menu}
  </article>;
}
