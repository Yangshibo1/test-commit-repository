import { ProvNode, ProvEdge, FlowNode, FlowEdge } from '../types';

export interface LayoutResult {
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
}

export function createNodeLayout(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
  options: {
    nodeWidth?: number;
    rowHeight?: number;
    nodeGap?: number;
    rowGap?: number;
  } = {}
): LayoutResult {
  const {
    nodeWidth = 220,
    rowHeight = 140,
    nodeGap = 96,
    rowGap = 40,
  } = options;

  // Helper to extract node number from location or name
  function getNodeNumber(node: ProvNode): number {
    // Try to extract from location first
    if (node.location) {
      const match = node.location.match(/node_0*(\d+)_/i);
      if (match) {
        return parseInt(match[1], 10); // 1 for node_01, 2 for node_02, etc.
      }

      // Check if it's a report or visualization file (belongs to last row)
      if (node.location.match(/(final_report|visualization|validation_result)/i)) {
        // Try to extract node number from these files
        const nodeMatch = node.location.match(/node_0*(\d+)_/i);
        if (nodeMatch) {
          return parseInt(nodeMatch[1], 10);
        }
        return 999; // Put in last row
      }

      // Original data files
      if (node.location.match(/MC2 data\.json|org_chart\.json/i)) {
        return 0;
      }
    }

    // For agent nodes, try to extract from name
    if (node.type === 'agent' && node.name) {
      const match = node.name.match(/node_0*(\d+)/i);
      if (match) {
        return parseInt(match[1], 10); // 1 for node_01, 2 for node_02, etc.
      }
    }

    return 0; // Default to first row
  }

  // Helper to determine module type for sorting within same node
  function getModuleType(node: ProvNode): number {
    // 0 = python script (agent)
    // 1 = dataset (entity)
    // 2 = report (entity with report/visualization keywords)

    if (node.type === 'agent') {
      return 0; // Python scripts first
    }

    if (node.type === 'entity') {
      if (node.location && node.location.match(/(report|visualization|validation|final)/i)) {
        return 2; // Reports last
      }
      return 1; // Datasets in middle
    }

    if (node.type === 'activity') {
      return 0; // Activities with scripts
    }

    return 1; // Default to middle
  }

  // Group nodes by their row number
  const rows = new Map<number, ProvNode[]>();
  provNodes.forEach((node) => {
    const rowNumber = getNodeNumber(node);
    if (!rows.has(rowNumber)) {
      rows.set(rowNumber, []);
    }
    rows.get(rowNumber)!.push(node);
  });

  // Sort row numbers
  const sortedRows = Array.from(rows.keys()).sort((a, b) => {
    if (a === 999) return 1; // Put row 999 at the end
    if (b === 999) return -1;
    return a - b;
  });

  // Calculate node positions - all nodes in a single vertical column
  const flowNodes: FlowNode[] = [];
  const centerX = 400; // Center X position for all nodes

  // Flatten all nodes and sort by row number, then by module type
  const allNodes: { node: ProvNode; rowNumber: number; moduleType: number }[] = [];
  sortedRows.forEach((rowNumber) => {
    const rowNodes = rows.get(rowNumber)!;
    rowNodes.forEach((node) => {
      allNodes.push({ node, rowNumber, moduleType: getModuleType(node) });
    });
  });

  // Sort by row number first, then by module type (script -> dataset -> report)
  allNodes.sort((a, b) => {
    if (a.rowNumber === 999) return 1;
    if (b.rowNumber === 999) return -1;
    if (a.rowNumber !== b.rowNumber) {
      return a.rowNumber - b.rowNumber;
    }
    return a.moduleType - b.moduleType;
  });

  allNodes.forEach(({ node }, nodeIndex) => {
    const y = nodeIndex * (rowHeight + rowGap) + 50; // Start at y=50

    flowNodes.push({
      id: node.id,
      type: node.type === 'entity' ? 'entity' : node.type === 'activity' ? 'activity' : 'agent',
      position: { x: centerX, y },
      data: {
        label: formatNodeLabel(node),
        nodeType: node.type,
        description: node.description,
        location: node.location,
        provNode: node,
      },
    });
  });

  // Calculate graph dimensions
  const maxRowWidth = Math.max(...Array.from(rows.values()).map(row => row.length * (nodeWidth + nodeGap)));
  const totalHeight = sortedRows.length * (rowHeight + rowGap) + 100;

  // Build a map of node ID to vertical index
  const nodeIndexMap = new Map<string, number>();
  allNodes.forEach(({ node }, index) => {
    nodeIndexMap.set(node.id, index);
  });

  // Filter edges: exclude wasDerivedFrom
  const filteredEdges = provEdges.filter(e => e.relation !== 'wasDerivedFrom');

  // Helper function to determine edge type and handles
  function getEdgeHandles(sourceId: string, targetId: string): { sourceHandle: string; targetHandle: string; isSequential: boolean; sourceRow: number; targetRow: number } {
    const sourceNode = provNodes.find(n => n.id === sourceId);
    const targetNode = provNodes.find(n => n.id === targetId);

    if (!sourceNode || !targetNode) {
      return { sourceHandle: 'right', targetHandle: 'left', isSequential: false, sourceRow: 0, targetRow: 0 };
    }

    const sourceRow = getNodeNumber(sourceNode);
    const targetRow = getNodeNumber(targetNode);

    // Get vertical indices to check if nodes are adjacent in the layout
    const sourceIndex = nodeIndexMap.get(sourceId) ?? 0;
    const targetIndex = nodeIndexMap.get(targetId) ?? 0;
    const indexDiff = targetIndex - sourceIndex;

    // Sequential edge: adjacent in vertical layout (including same-node relationships)
    // Use bottom->top for all sequential edges
    if (indexDiff === 1) {
      return { sourceHandle: 'bottom', targetHandle: 'top', isSequential: true, sourceRow, targetRow };
    }

    // Cross-node edge: use left for odd starting nodes, right for even
    const useLeft = sourceRow % 2 === 1;
    return {
      sourceHandle: useLeft ? 'left' : 'right',
      targetHandle: useLeft ? 'left' : 'right',
      isSequential: false,
      sourceRow,
      targetRow
    };
  }

  // Create flow edges
  const flowEdges: FlowEdge[] = [];
  const edgeIdSet = new Set<string>();

  filteredEdges.forEach((provEdge) => {
    const sourceExists = provNodes.some(n => n.id === provEdge.from);
    const targetExists = provNodes.some(n => n.id === provEdge.to);

    if (sourceExists && targetExists) {
      const edgeId = `${provEdge.from}-${provEdge.to}`;
      if (!edgeIdSet.has(edgeId)) {
        edgeIdSet.add(edgeId);
        const { sourceHandle, targetHandle, isSequential, sourceRow, targetRow } = getEdgeHandles(provEdge.from, provEdge.to);

        flowEdges.push({
          id: edgeId,
          source: provEdge.from,
          target: provEdge.to,
          sourceHandle,
          targetHandle,
          label: provEdge.relation,
          type: isSequential ? 'straight' : 'default',
          animated: provEdge.relation === 'output',
          data: { relation: provEdge.relation, isSequential, sourceRow, targetRow },
        });
      }
    }
  });

  return {
    nodes: flowNodes,
    edges: flowEdges,
    width: maxRowWidth + 100,
    height: totalHeight,
  };
}

function formatNodeLabel(node: ProvNode): string {
  const raw = node.location ? node.location.split(/[\\/]/).pop() : (node.name || node.description || node.id);
  return String(raw)
    .replace(/^node_0*(\d+)_/, 'n$1 · ')
    .replace(/_/g, ' ')
    .replace(/\.(json|py|txt)$/i, '')
    .slice(0, 54);
}
