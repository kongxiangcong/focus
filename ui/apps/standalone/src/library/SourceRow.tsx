import type { DragEventHandler } from "react";
import { SourceArtifacts, SourceKind, SourceMeta, SourcePrimary, SourceState, SourceTitle, sourceAttributes, type SourceViewProps } from "./SourceParts";

export function SourceRow(props: SourceViewProps & { ordinal?: number; sortingReason: string; onDragStart: DragEventHandler; onDragOver: DragEventHandler; onDrop: DragEventHandler; onDragEnd: DragEventHandler }) {
  return <article className="library-source-row" role="listitem" data-ordered={props.ordinal !== undefined} onDragOver={props.onDragOver} onDrop={props.onDrop} data-source-id={props.source.sourceId} data-selected={props.selected} data-phase={props.status.phase} {...sourceAttributes(props.source)} onClick={props.onSelect} onDoubleClick={() => { if (!props.action.disabled) props.onPrimary(); }}>
    {props.ordinal !== undefined && <span className="library-source-ordinal" draggable={!props.sortingReason} title={props.sortingReason || "拖动调整专题顺序"} onDragStart={props.onDragStart} onDragEnd={props.onDragEnd} onClick={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()}><span className="library-source-grip" aria-hidden="true">⋮⋮</span><span aria-label={`专题顺序 ${props.ordinal}`}>{props.ordinal}</span></span>}<SourceKind source={props.source} /><div className="library-source-main"><SourceTitle {...props} /><SourceMeta {...props} /></div><SourceState {...props} /><SourceArtifacts {...props} /><SourcePrimary {...props} />{props.menu}
  </article>;
}
