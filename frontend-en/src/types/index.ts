// AgentVAST PROV Types
export interface ArtifactMatchResult {
  artifact: LlmArtifact | null;
  matchedKey: string | null;
  candidates: string[];
  matchType: 'exact' | 'fuzzy' | 'none';
  similarityScore?: number;
}

export interface ProvNode {
  id: string;
  type: 'entity' | 'activity' | 'agent';
  entity_type?: string;
  activity_type?: string;
  agent_type?: string;
  location?: string;
  name?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  timestamp?: string;
  merged?: boolean;
  original_ids?: string[];
}

export interface ProvEdge {
  from: string;
  to: string;
  relation: string;
}

export interface ProvDAG {
  nodes: Record<string, ProvNode>;
  edges: ProvEdge[];
  session_id?: string;
  created_at?: string;
}

export interface StepDetail {
  step_id: string;
  step_name: string;
  name: string;
  description: string;
  timestamp: string;
  input_files: string[];
  output_files: string[];
  code_files: string[];
  code_generated?: string[];
  commands_run?: string[];
  parameters?: Record<string, unknown>;
  index?: number;
  operation?: string;
}

export interface StepDetails {
  session_id: string;
  created_at: string;
  steps: StepDetail[];
  total_steps?: number;
}

export interface LlmArtifact {
  algorithm_purpose?: string;
  algorithm_logic?: string[] | string;
  data_flow?: string;
  description?: string;
  sample_data?: unknown;
  echarts_chart?: object;
  // 可视化内容：可以是图片URL、base64图片或HTML字符串
  visualization?: string;
  visualization_type?: 'image' | 'html' | 'echarts';
  key_findings?: unknown;
  answers?: unknown;
}

export interface MetaData {
  session_id?: string;
  created_at?: string;
  total_steps?: number;
}

// Session Files
export interface SessionFiles {
  'step_details.json'?: StepDetails;
  'prov_nodes.json'?: { nodes: Record<string, ProvNode> };
  'prov_edges.json'?: { edges: ProvEdge[] };
  'prov_dag.json'?: ProvDAG;
  'meta.json'?: MetaData;
  [key: string]: unknown;
}

// Parsed Trace Data
export interface TraceData {
  sessionId: string;
  createdAt: string;
  steps: StepDetail[];
  prov: {
    nodes: Record<string, ProvNode>;
    edges: ProvEdge[];
  };
  llmArtifacts: Record<string, LlmArtifact>;
  counts: {
    entities: number;
    activities: number;
    agents: number;
    edges: number;
    artifacts: number;
  };
  consistency: {
    ok: boolean;
    warnings: string[];
  };
}

// React Flow Types
export interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    nodeType: string;
    description?: string;
    location?: string;
    provNode?: ProvNode;
    step?: StepDetail;
    artifact?: LlmArtifact;
  };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type?: string;
  animated?: boolean;
  style?: React.CSSProperties;
  sourceHandle?: string;
  targetHandle?: string;
  data?: {
    relation: string;
    isSequential?: boolean;
    sourceRow?: number;
    targetRow?: number;
  };
}
