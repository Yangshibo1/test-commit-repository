import { ProvNode, ProvEdge, FlowNode, FlowEdge } from '../types';

export interface LayoutResult {
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
}

export interface DAGPage {
  pageNum: number;
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
  sourceInfo?: string;
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

/**
 * Create multiple DAG pages from PROV data
 * Page 0: Full overview (all modules)
 * Page 1+: Split pages based on module relationships
 */
export function createDAGPages(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
  options: {
    nodeWidth?: number;
    rowHeight?: number;
    nodeGap?: number;
    rowGap?: number;
  } = {}
): DAGPage[] {
  const {
    nodeWidth = 220,
    rowHeight = 140,
    nodeGap: _nodeGap = 96,  // Passed to createNodeLayout
    rowGap = 40,
  } = options;

  // Helper functions (copied from createNodeLayout)
  function getNodeNumber(node: ProvNode): number {
    if (node.location) {
      const match = node.location.match(/node_0*(\d+)_/i);
      if (match) return parseInt(match[1], 10);
      if (node.location.match(/(final_report|visualization|validation_result)/i)) {
        const nodeMatch = node.location.match(/node_0*(\d+)_/i);
        if (nodeMatch) return parseInt(nodeMatch[1], 10);
        return 999;
      }
      if (node.location.match(/MC2 data\.json|org_chart\.json/i)) return 0;
    }
    if (node.type === 'agent' && node.name) {
      const match = node.name.match(/node_0*(\d+)/i);
      if (match) return parseInt(match[1], 10);
    }
    return 0;
  }

  function getModuleType(node: ProvNode): number {
    if (node.type === 'agent') return 0;
    if (node.type === 'entity') {
      if (node.location && node.location.match(/(report|visualization|validation|final)/i)) return 2;
      return 1;
    }
    if (node.type === 'activity') return 0;
    return 1;
  }

  // Build node ID set for quick lookup
  const nodeIdSet = new Set(provNodes.map(n => n.id));

  // Filter edges: exclude wasDerivedFrom
  const filteredEdges = provEdges.filter(e => e.relation !== 'wasDerivedFrom');

  // Build adjacency map for checking connections
  const connectedTo = new Map<string, Set<string>>();
  provNodes.forEach(node => connectedTo.set(node.id, new Set()));
  filteredEdges.forEach(edge => {
    if (nodeIdSet.has(edge.from) && nodeIdSet.has(edge.to)) {
      connectedTo.get(edge.from)!.add(edge.to);
      connectedTo.get(edge.to)!.add(edge.from);
    }
  });

  // Group and sort nodes
  const rows = new Map<number, ProvNode[]>();
  provNodes.forEach((node) => {
    const rowNumber = getNodeNumber(node);
    if (!rows.has(rowNumber)) rows.set(rowNumber, []);
    rows.get(rowNumber)!.push(node);
  });

  const sortedRows = Array.from(rows.keys()).sort((a, b) => {
    if (a === 999) return 1;
    if (b === 999) return -1;
    return a - b;
  });

  // Flatten and sort nodes
  const allNodes: { node: ProvNode; rowNumber: number; moduleType: number }[] = [];
  sortedRows.forEach((rowNumber) => {
    const rowNodes = rows.get(rowNumber)!;
    rowNodes.forEach((node) => {
      allNodes.push({ node, rowNumber, moduleType: getModuleType(node) });
    });
  });

  allNodes.sort((a, b) => {
    if (a.rowNumber === 999) return 1;
    if (b.rowNumber === 999) return -1;
    if (a.rowNumber !== b.rowNumber) return a.rowNumber - b.rowNumber;
    return a.moduleType - b.moduleType;
  });

  // Page 0: Full overview (already computed by createNodeLayout)
  const fullLayout = createNodeLayout(provNodes, provEdges, options);
  const pages: DAGPage[] = [{
    pageNum: 0,
    nodes: fullLayout.nodes,
    edges: fullLayout.edges,
    width: fullLayout.width,
    height: fullLayout.height,
  }];

  // Group nodes by their node number (n1, n2, n3, etc.)
  const nodesByNumber = new Map<number, { node: ProvNode; rowNumber: number; moduleType: number }[]>();
  allNodes.forEach(item => {
    if (!nodesByNumber.has(item.rowNumber)) {
      nodesByNumber.set(item.rowNumber, []);
    }
    nodesByNumber.get(item.rowNumber)!.push(item);
  });

  // Get sorted node numbers
  const nodeNumbers = Array.from(nodesByNumber.keys()).sort((a, b) => {
    if (a === 999) return 1;
    if (b === 999) return -1;
    return a - b;
  });

  // Find the index of the last module for each node in allNodes
  const nodeEndIndices = new Map<number, number>();
  allNodes.forEach((item, index) => {
    nodeEndIndices.set(item.rowNumber, index);
  });

  // Detect split points between nodes (not modules)
  const splitPoints: number[] = [];
  for (let i = 0; i < nodeNumbers.length - 1; i++) {
    const currentNum = nodeNumbers[i];
    const nextNum = nodeNumbers[i + 1];

    // Get all module IDs for current and next nodes
    const currentNodeIds = new Set(nodesByNumber.get(currentNum)!.map(n => n.node.id));
    const nextNodeIds = new Set(nodesByNumber.get(nextNum)!.map(n => n.node.id));

    // Check if there's any connection between current node and next node
    let hasConnection = false;
    for (const currentId of currentNodeIds) {
      const connections = connectedTo.get(currentId) || new Set();
      for (const nextId of nextNodeIds) {
        if (connections.has(nextId)) {
          hasConnection = true;
          break;
        }
      }
      if (hasConnection) break;
    }

    // If no connection between these two nodes, split after current node
    if (!hasConnection) {
      const endIndex = nodeEndIndices.get(currentNum);
      if (endIndex !== undefined) {
        splitPoints.push(endIndex + 1); // Split after the last module of current node
      }
    }
  }

  // If no split points, just return the full overview
  if (splitPoints.length === 0) {
    return pages;
  }

  // Calculate split ranges: each split has a start and end index
  const splitRanges: { start: number; end: number }[] = [];
  let prevIndex = 0;
  splitPoints.forEach(point => {
    splitRanges.push({ start: prevIndex, end: point });
    prevIndex = point;
  });
  // Add the last split
  splitRanges.push({ start: prevIndex, end: allNodes.length });

  // For each split, find which previous nodes need to be copied
  // A node needs to be copied if it has an edge to a node in the current split
  // but is not in the current split itself
  const nodesToCopyForSplit: Set<string>[] = [];

  splitRanges.forEach((range, _splitIndex) => {
    const nodesInCurrentSplit = new Set(
      allNodes.slice(range.start, range.end).map(n => n.node.id)
    );

    const nodesToCopy = new Set<string>();

    // Check all edges to see if any source node is outside current split
    // but target is inside current split
    filteredEdges.forEach(edge => {
      if (nodesInCurrentSplit.has(edge.to) && !nodesInCurrentSplit.has(edge.from)) {
        // This edge comes from outside the split, need to copy source
        nodesToCopy.add(edge.from);
      }
    });

    nodesToCopyForSplit.push(nodesToCopy);
  });

  // Create split pages
  splitRanges.forEach((range, splitIndex) => {
    const pageNum = splitIndex + 1;
    const splitNodes = allNodes.slice(range.start, range.end);
    const nodesToCopy = nodesToCopyForSplit[splitIndex];

    // Collect node IDs in this split
    const nodeIdsInSplit = new Set(splitNodes.map(n => n.node.id));

    // Add copied nodes
    nodesToCopy.forEach(nodeId => {
      nodeIdsInSplit.add(nodeId);
    });

    // Find edges that involve nodes in this split (including copied nodes)
    const pageEdges = filteredEdges.filter(edge =>
      nodeIdsInSplit.has(edge.from) && nodeIdsInSplit.has(edge.to)
    );

    // Collect all node IDs needed for this page
    const allNodeIdsForPage = new Set(nodeIdsInSplit);
    pageEdges.forEach(edge => {
      allNodeIdsForPage.add(edge.from);
      allNodeIdsForPage.add(edge.to);
    });

    // Get the actual node objects
    const nodesForPage: ProvNode[] = [];
    const nodeIdToIndex = new Map<string, number>();

    allNodes.forEach((item, _index) => {
      if (allNodeIdsForPage.has(item.node.id)) {
        nodesForPage.push(item.node);
        nodeIdToIndex.set(item.node.id, nodesForPage.length - 1);
      }
    });

    // Create FlowNode for this page
    const centerX = 400;
    const flowNodes: FlowNode[] = [];

    nodesForPage.forEach((node, nodeIndex) => {
      const y = nodeIndex * (rowHeight + rowGap) + 50;
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

    // Build node index map for edge handles
    const nodeIndexMap = new Map<string, number>();
    nodesForPage.forEach((node, index) => {
      nodeIndexMap.set(node.id, index);
    });

    // Helper to get edge handles
    function getEdgeHandles(sourceId: string, targetId: string) {
      const sourceNode = provNodes.find(n => n.id === sourceId);
      const targetNode = provNodes.find(n => n.id === targetId);
      if (!sourceNode || !targetNode) {
        return { sourceHandle: 'right', targetHandle: 'left', isSequential: false, sourceRow: 0, targetRow: 0 };
      }

      const sourceRow = getNodeNumber(sourceNode);
      const targetRow = getNodeNumber(targetNode);
      const sourceIndex = nodeIndexMap.get(sourceId) ?? 0;
      const targetIndex = nodeIndexMap.get(targetId) ?? 0;
      const indexDiff = targetIndex - sourceIndex;

      if (indexDiff === 1) {
        return { sourceHandle: 'bottom', targetHandle: 'top', isSequential: true, sourceRow, targetRow };
      }

      const useLeft = sourceRow % 2 === 1;
      return {
        sourceHandle: useLeft ? 'left' : 'right',
        targetHandle: useLeft ? 'left' : 'right',
        isSequential: false,
        sourceRow,
        targetRow
      };
    }

    // Create FlowEdge for this page
    const flowEdges: FlowEdge[] = [];
    const edgeIdSet = new Set<string>();

    pageEdges.forEach((provEdge) => {
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
    });

    // Generate source info
    let sourceInfo: string | undefined;
    if (nodesToCopy.size > 0) {
      const sourceNames: string[] = [];
      nodesToCopy.forEach(id => {
        const node = provNodes.find(n => n.id === id);
        if (node) {
          const name = formatNodeLabel(node);
          sourceNames.push(name);
        }
      });
      if (sourceNames.length > 0) {
        sourceInfo = `Continued from: ${sourceNames.slice(0, 2).join(', ')}${sourceNames.length > 2 ? '...' : ''}`;
      }
    }

    // Add page
    pages.push({
      pageNum,
      nodes: flowNodes,
      edges: flowEdges,
      width: nodeWidth + 100,
      height: nodesForPage.length * (rowHeight + rowGap) + 100,
      sourceInfo,
    });
  });

  return pages;
}
