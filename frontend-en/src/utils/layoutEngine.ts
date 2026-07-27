import dagre from 'dagre';
import { ProvNode, ProvEdge, FlowNode, FlowEdge } from '../types';

export interface LayoutResult {
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
}

export function createDagreLayout(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
  options: {
    nodeWidth?: number;
    nodeHeight?: number;
    ranksep?: number;
    nodesep?: number;
  } = {}
): LayoutResult {
  const {
    nodeWidth = 220,
    nodeHeight = 96,
    ranksep = 140,
    nodesep = 96,
  } = options;

  // Create a new directed graph
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: 'TB',
    nodesep,
    ranksep,
    edgesep: 40,
  });

  // Default to undefined for node and edge labels
  g.setDefaultEdgeLabel(() => ({}));

  // Track connected nodes to handle isolated ones later
  const connectedNodeIds = new Set<string>();

  // Add edges first to identify connected nodes
  provEdges.forEach((edge) => {
    g.setEdge(edge.from, edge.to);
    connectedNodeIds.add(edge.from);
    connectedNodeIds.add(edge.to);
  });

  // Add all nodes to the graph (including isolated ones)
  provNodes.forEach((node) => {
    g.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  // Calculate layout
  dagre.layout(g);

  // Calculate layout
  const graph = g.graph();
  const layoutWidth = graph?.width || 800;
  const layoutHeight = graph?.height || 600;

  // Convert to FlowNode and FlowEdge
  const flowNodes: FlowNode[] = [];
  const flowEdges: FlowEdge[] = [];

  // Process nodes - handle isolated nodes without positions
  g.nodes().forEach((nodeId) => {
    const node = g.node(nodeId);
    const provNode = provNodes.find((n) => n.id === nodeId);
    if (provNode) {
      // For isolated nodes without positions, place them at the end
      let position = { x: 0, y: 0 };
      if (node && node.x !== undefined && node.y !== undefined) {
        position = { x: node.x, y: node.y };
      } else {
        // Place isolated nodes at the bottom right
        const isolatedCount = flowNodes.filter(n => !connectedNodeIds.has(n.id)).length;
        position = { x: layoutWidth - 300 - isolatedCount * 250, y: layoutHeight + 100 };
      }

      flowNodes.push({
        id: nodeId,
        type: getNodeStyleType(provNode),
        position,
        data: {
          label: formatNodeLabel(provNode),
          nodeType: provNode.type,
          description: provNode.description,
          location: provNode.location,
          provNode,
        },
      });
    }
  });

  // Process edges - directly use provEdges without relying on g.edges()
  provEdges.forEach((provEdge) => {
    // Verify source and target nodes exist
    const sourceExists = provNodes.some(n => n.id === provEdge.from);
    const targetExists = provNodes.some(n => n.id === provEdge.to);

    if (sourceExists && targetExists) {
      flowEdges.push({
        id: `${provEdge.from}-${provEdge.to}`,
        source: provEdge.from,
        target: provEdge.to,
        label: provEdge.relation,
        type: getEdgeType(provEdge.relation),
        animated: provEdge.relation === 'output',
        data: { relation: provEdge.relation },
        style: {
          stroke: provEdge.relation === 'wasDerivedFrom' ? '#d97745' : '#a8a29e',
          strokeWidth: provEdge.relation === 'output' ? 2 : 1.5,
        },
      });
    }
  });

  return {
    nodes: flowNodes,
    edges: flowEdges,
    width: layoutWidth,
    height: layoutHeight,
  };
}

function getNodeStyleType(node: ProvNode): string {
  if (node.type === 'entity') return 'entity';
  if (node.type === 'activity') return 'activity';
  if (node.type === 'agent') return 'agent';
  return 'default';
}

function getEdgeType(_relation: string): string {
  // Use default edge type for all edges to ensure proper rendering
  // Custom edge types require corresponding edge components
  return 'default';
}

function formatNodeLabel(node: ProvNode): string {
  const raw = node.location ? node.location.split(/[\\/]/).pop() : (node.name || node.description || node.id);
  return String(raw)
    .replace(/^node_0*(\d+)_/, 'n$1 · ')
    .replace(/_/g, ' ')
    .replace(/\.(json|py|txt)$/i, '')
    .slice(0, 54);
}
