import { UploadProgress } from "./UploadProgress";
import { BatteryProgress } from "./BatteryProgress";
import { SourceArtifacts, SourceKind, SourceMeta, SourcePrimary, SourceState, SourceTitle, sourceAttributes, type SourceViewProps } from "./SourceParts";

export function SourceCard(props: SourceViewProps) {
  return <article className="library-source-card" role="listitem" data-source-id={props.source.sourceId} data-selected={props.selected} data-phase={props.status.phase} {...sourceAttributes(props.source, props.status)} onClick={props.onSelect} onDoubleClick={() => { if (!props.action.disabled) props.onPrimary(); }}>
    <div className="library-source-card-top"><SourceKind source={props.source} /><SourceState {...props} bar={false} />{props.menu}</div><SourceTitle {...props} /><SourceMeta {...props} /><UploadProgress item={props.uploadItem} blog={props.blog ?? props.uploadItem?.blog ?? undefined} />
    <div className="library-source-card-bottom"><BatteryProgress label={`${props.source.title} 精读进度`} progress={props.status.progress} /><SourceArtifacts {...props} /><SourcePrimary {...props} /></div>
  </article>;
}
