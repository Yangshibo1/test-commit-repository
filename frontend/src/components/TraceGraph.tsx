import { useCallback, useEffect, useMemo, useRef, useState, useImperativeHandle, forwardRef } from 'react';
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
import { createNodeLayout, createDAGPages, DAGPage } from '../utils/nodeLayoutEngine';

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

export interface TraceGraphRef {
  zoomIn: () => void;
  zoomOut: () => void;
  toggleFullscreen: () => void;
  goToPage: (page: number) => void;
  getCurrentPage: () => number;
  getTotalPages: () => number;
}

interface TraceGraphProps {
  provNodes: ProvNode[];
  provEdges: ProvEdge[];
  onNodeClick?: (node: ProvNode) => void;
  onPageChange?: (page: number, totalPages: number) => void;
}

const TraceGraph = forwardRef<TraceGraphRef, TraceGraphProps>(({ provNodes, provEdges, onNodeClick, onPageChange }, ref) => {
  const reactFlowInstance = useRef<any>(null);

  // Page and fullscreen state
  const [currentPage, setCurrentPage] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);

  // Create all DAG pages
  const dagPages = useMemo(() => {
    return createDAGPages(provNodes, provEdges, {
      nodeWidth: 220,
      rowHeight: 140,
      nodeGap: 96,
      rowGap: 40,
    });
  }, [provNodes, provEdges]);

  // Get current page data
  const currentPageData = useMemo(() => {
    if (Array.isArray(dagPages)) {
      return dagPages[currentPage] || dagPages[0];
    }
    return dagPages;
  }, [dagPages, currentPage]);

  const totalPages = Array.isArray(dagPages) ? dagPages.length : 1;

  const [nodes, setNodes, onNodesChange] = useNodesState(currentPageData.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(currentPageData.edges);

  // Notify parent component of page changes
  useEffect(() => {
    if (onPageChange) {
      onPageChange(currentPage, totalPages);
    }
  }, [currentPage, totalPages, onPageChange]);

  // Update nodes and edges when page changes
  useEffect(() => {
    setNodes(currentPageData.nodes);
    setEdges(currentPageData.edges);
    setHighlightedNodeId(null); // Reset highlight when page changes
  }, [currentPage, currentPageData, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: any) => {
      const provNode = node.data.provNode as ProvNode;

      // Toggle highlight
      if (highlightedNodeId === node.id) {
        setHighlightedNodeId(null);
      } else {
        setHighlightedNodeId(node.id);
      }

      if (provNode && onNodeClick) {
        onNodeClick(provNode);
      }
    },
    [onNodeClick, highlightedNodeId]
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

  const goToPage = useCallback((page: number) => {
    setCurrentPage(Math.max(0, Math.min(totalPages - 1, page)));
  }, [totalPages]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    zoomIn: handleZoomIn,
    zoomOut: handleZoomOut,
    toggleFullscreen,
    goToPage,
    getCurrentPage: () => currentPage,
    getTotalPages: () => totalPages,
  }), [handleZoomIn, handleZoomOut, toggleFullscreen, goToPage, currentPage, totalPages]);

  // Apply highlight styles to edges
  const styledEdges = useMemo(() => {
    if (!highlightedNodeId) return edges;

    return edges.map(edge => {
      const isRelated = edge.source === highlightedNodeId || edge.target === highlightedNodeId;
      return {
        ...edge,
        style: {
          ...edge.style,
          opacity: isRelated ? 1 : 0.15,
          stroke: isRelated ? '#d97745' : '#a8a29e',
          strokeWidth: isRelated ? 2.5 : 1.5,
        },
      };
    });
  }, [edges, highlightedNodeId]);

  // Apply highlight styles to nodes
  const styledNodes = useMemo(() => {
    if (!highlightedNodeId) return nodes;

    return nodes.map(node => {
      const isRelated = node.id === highlightedNodeId ||
        edges.some(e => (e.source === highlightedNodeId && e.target === node.id) ||
                          (e.target === highlightedNodeId && e.source === node.id));
      return {
        ...node,
        style: {
          ...node.style,
          opacity: isRelated ? 1 : 0.3,
        },
      };
    });
  }, [nodes, edges, highlightedNodeId]);

  const containerClass = isFullscreen
    ? 'fixed inset-0 z-50 bg-[#fffaf5]'
    : 'w-full h-full bg-[#fffaf5]';

  return (
    <div className={containerClass}>
      {isFullscreen && totalPages > 1 && (
        <div className="absolute top-4 left-4 flex items-center gap-3 bg-[rgba(255,250,240,0.95)] px-4 py-2 rounded-xl border border-[rgba(184,165,143,0.58)] shadow-sm z-10">
          <button
            onClick={toggleFullscreen}
            className="px-3 py-1 rounded-lg border border-[rgba(184,165,143,0.58)] bg-white text-sm font-mono hover:border-accent transition-colors"
            title="Exit fullscreen"
          >
            ⛶ Exit
          </button>

          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage === 0}
            className="px-3 py-1 rounded-lg border border-[rgba(184,165,143,0.58)] bg-white text-sm font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ◀
          </button>
          <span className="text-sm font-mono text-[#6b5b4f]">
            Page {currentPage + 1}/{totalPages}
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage === totalPages - 1}
            className="px-3 py-1 rounded-lg border border-[rgba(184,165,143,0.58)] bg-white text-sm font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ▶
          </button>

          {Array.isArray(dagPages) && dagPages[currentPage]?.sourceInfo && (
            <span className="text-xs text-[#6b5b4f] border-l border-[rgba(184,165,143,0.58)] pl-3">
              {dagPages[currentPage].sourceInfo}
            </span>
          )}
        </div>
      )}

      <ReactFlow
        nodes={styledNodes}
        edges={styledEdges}
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

      {/* Custom Zoom Controls (hidden in fullscreen) */}
      {!isFullscreen && (
        <div className="absolute bottom-4 right-4 flex gap-2 z-10">
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
      )}
    </div>
  );
});

TraceGraph.displayName = 'TraceGraph';

export default TraceGraph;
