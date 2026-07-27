import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getMarkerEnd } from 'reactflow';
import type { EdgeProps } from 'reactflow';

interface CustomEdgeData {
  isSequential?: boolean;
  relation?: string;
  sourceRow?: number;
  targetRow?: number;
}

const CustomEdge = ({
  id,
  label,
  data,
  markerEnd,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  style,
}: EdgeProps<CustomEdgeData>) => {
  const edgeData = data as CustomEdgeData;
  const isSequential = edgeData?.isSequential || false;
  const sourceRow = edgeData?.sourceRow || 0;
  const targetRow = edgeData?.targetRow || 0;

  // Use provided style or default
  const edgeStyle = style || {};

  // For sequential edges: draw vertical straight line
  if (isSequential) {
    const path = `M ${sourceX} ${sourceY} L ${targetX} ${targetY}`;

    const labelX = (sourceX + targetX) / 2;
    const labelY = (sourceY + targetY) / 2;

    return (
      <>
        <BaseEdge
          id={id}
          path={path}
          markerEnd={getMarkerEnd(markerEnd as any)}
          style={edgeStyle}
        />
        {label && (
          <EdgeLabelRenderer>
            <div
              className="edge-label"
              style={{
                position: 'absolute',
                transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
                fontSize: '10px',
                fontFamily: 'monospace',
                background: '#fffaf5',
                padding: '2px 6px',
                borderRadius: '4px',
                border: '1px solid rgba(184,165,143,0.58)',
                pointerEvents: 'none',
                userSelect: 'none',
                opacity: edgeStyle.opacity || 1,
              }}
            >
              {label}
            </div>
          </EdgeLabelRenderer>
        )}
      </>
    );
  }

  // For cross-node edges: draw polyline with offset proportional to distance
  const rowDistance = Math.abs(targetRow - sourceRow);
  const baseOffset = 60; // Base offset for distance of 1
  const offset = baseOffset * rowDistance; // Proportional offset

  // Determine which side (left or right) based on handle position
  const isLeftSide = sourcePosition === 'left';
  const sideX = isLeftSide ? sourceX - offset : sourceX + offset;

  // Create polyline path
  // Start from source node handle
  // Go horizontally to side
  // Go vertically to target Y level
  // Go horizontally back to target node handle
  const path = `M ${sourceX} ${sourceY} L ${sideX} ${sourceY} L ${sideX} ${targetY} L ${targetX} ${targetY}`;

  // Calculate label position (on the vertical segment)
  const labelX = sideX;
  const labelY = (sourceY + targetY) / 2;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={getMarkerEnd(markerEnd as any)}
        style={edgeStyle}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="edge-label"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              fontSize: '10px',
              fontFamily: 'monospace',
              background: '#fffaf5',
              padding: '2px 6px',
              borderRadius: '4px',
              border: '1px solid rgba(184,165,143,0.58)',
              pointerEvents: 'none',
              userSelect: 'none',
              opacity: edgeStyle.opacity || 1,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export default memo(CustomEdge);
