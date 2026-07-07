import { useCallback, useMemo, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  NodeTypes,
  EdgeTypes,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import CustomEdge from './CustomEdge';
import { ProvNode, ProvEdge } from '../types';
import { createNodeLayout } from '../utils/nodeLayoutEngine';

const nodeTypes: NodeTypes = {
  entity: CustomNode,
  activity: CustomNode,
  agent: CustomNode,
  default: CustomNode,
};

const edgeTypes: EdgeTypes = {
  straight: CustomEdge,
  default: CustomEdge,
};

interface TraceGraphProps {
  provNodes: ProvNode[];
  provEdges: ProvEdge[];
  onNodeClick?: (node: ProvNode) => void;
}

export default function TraceGraph({ provNodes, provEdges, onNodeClick }: TraceGraphProps) {
  const reactFlowInstance = useRef<any>(null);

  // Use custom node layout (rows by node number)
  const layout = useMemo(() => {
    return createNodeLayout(provNodes, provEdges, {
      nodeWidth: 220,
      rowHeight: 140,
      nodeGap: 96,
      rowGap: 40,
    });
  }, [provNodes, provEdges]);

  const [nodes, , onNodesChange] = useNodesState(layout.nodes);
  const [edges, , onEdgesChange] = useEdgesState(layout.edges);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: any) => {
      const provNode = node.data.provNode as ProvNode;
      if (provNode && onNodeClick) {
        onNodeClick(provNode);
      }
    },
    [onNodeClick]
  );

  const handleZoomIn = useCallback(() => {
    if (reactFlowInstance.current) {
      reactFlowInstance.current.zoomIn();
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    if (reactFlowInstance.current) {
      reactFlowInstance.current.zoomOut();
    }
  }, []);

  return (
    <div className="w-full h-full bg-[#fffaf5]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.5}
        maxZoom={2}
        defaultEdgeOptions={{
          type: 'default',
          animated: false,
          style: { stroke: '#a8a29e', strokeWidth: 1.5 },
        }}
        onInit={(instance) => {
          reactFlowInstance.current = instance;
        }}
      >
        <Background
          color="rgba(217,119,69,0.06)"
          gap={28}
          style={{
            background:
              'radial-gradient(circle at 18% 12%, rgba(217, 119, 69, 0.06), transparent 24rem), radial-gradient(circle at 82% 18%, rgba(255, 248, 241, 0.92), transparent 28rem)',
          }}
        />
        <Controls
          className="!bg-[rgba(255,250,240,0.9)] !border-[rgba(184,165,143,0.58)]"
          showZoom={false}
        />
        <MiniMap
          className="!bg-[rgba(255,255,255,0.8)]"
          nodeColor="#d97745"
          maskColor="rgba(217,119,69,0.1)"
        />
      </ReactFlow>

      {/* Custom Zoom Controls */}
      <div className="absolute top-4 right-4 flex gap-2">
        <button
          onClick={handleZoomOut}
          className="px-3 py-1 rounded-lg border border-[rgba(184,165,143,0.58)] bg-[rgba(255,255,255,0.9)] text-sm font-mono hover:border-accent transition-colors"
        >
          −
        </button>
        <button
          onClick={handleZoomIn}
          className="px-3 py-1 rounded-lg border border-[rgba(184,165,143,0.58)] bg-[rgba(255,255,255,0.9)] text-sm font-mono hover:border-accent transition-colors"
        >
          +
        </button>
      </div>
    </div>
  );
}
