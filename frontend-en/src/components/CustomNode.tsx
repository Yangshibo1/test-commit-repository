import { memo, useCallback } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { ProvNode } from '../types';

interface CustomNodeData {
  label: string;
  nodeType: string;
  description?: string;
  location?: string;
  provNode: ProvNode;
  onNodeClick?: (node: ProvNode) => void;
}

const CustomNode = ({ data, selected }: NodeProps<CustomNodeData>) => {
  const nodeData = data as CustomNodeData;
  const provNode = nodeData.provNode as ProvNode;
  const nodeType = provNode?.type || 'default';

  // 获取更细粒度的节点分类用于颜色区分
  const getNodeCategory = (): string => {
    // 检查是否为 Code 节点（Python 脚本 - Agent 节点）
    if (nodeType === 'agent') {
      return 'code';
    }

    // 检查是否为 Report 节点（报告或可视化）
    const location = provNode?.location || '';
    if (nodeType === 'entity') {
      // 扩展 report 匹配模式，包含更多 report 相关关键词
      if (location.match(/(final_report|visualization|validation_result|analysis_report|investigation_report|\.txt$|report\.json)/i)) {
        return 'report';
      }
    }

    // 其他 Entity 都是 Dataset
    if (nodeType === 'entity') {
      return 'dataset';
    }

    return 'other';
  };

  const getBorderColor = () => {
    const category = getNodeCategory();

    // Code: 蓝紫色边框
    if (category === 'code') return 'border-l-4 border-[#8b5cf6] border-2 border-[#8b5cf6]';

    // Dataset: 绿色边框
    if (category === 'dataset') return 'border-l-4 border-[#10b981] border-2 border-[#10b981]';

    // Report: 橙红色边框
    if (category === 'report') return 'border-l-4 border-[#f97316] border-2 border-[#f97316]';

    // Other: 灰色边框
    return 'border-l-4 border-gray-400 border-2 border-gray-400';
  };

  const getSubtype = () => {
    if (nodeType === 'entity') return provNode?.entity_type || 'artifact';
    if (nodeType === 'activity') return provNode?.activity_type || 'activity';
    if (nodeType === 'agent') return provNode?.agent_type || 'agent';
    return 'node';
  };

  const getDescription = () => {
    if (nodeType === 'agent') {
      return (provNode?.name || provNode?.agent_type || 'processing agent').replace(/_/g, ' ').slice(0, 72);
    }
    if (nodeType === 'activity') {
      return (provNode?.description || provNode?.activity_type || 'activity').slice(0, 72);
    }
    if (provNode?.location) {
      return `${provNode?.entity_type || 'artifact'} · click for details`;
    }
    return (provNode?.description || provNode?.name || 'PROV node').slice(0, 72);
  };

  const handleClick = useCallback((event: React.MouseEvent) => {
    event.stopPropagation();
    if (nodeData.onNodeClick && provNode) {
      nodeData.onNodeClick(provNode);
    }
  }, [nodeData.onNodeClick, provNode]);

  return (
    <div
      onClick={handleClick}
      className={`
        px-3 py-2 rounded-xl border border-[rgba(184,165,143,0.58)]
        bg-[rgba(255,255,255,0.92)] shadow-lg
        hover:shadow-xl transition-shadow cursor-pointer
        ${getBorderColor()}
        ${selected ? 'border-accent' : ''}
      `}
      style={{ width: 220, minHeight: 96 }}
    >
      <div className="text-[9px] text-muted font-mono uppercase tracking-wider mb-1">
        {getSubtype()}
      </div>
      <div className="font-bold text-sm leading-tight overflow-hidden line-clamp-2">
        {nodeData.label}
      </div>
      <div className="text-[11px] text-[#6b5b4f] mt-1 leading-tight overflow-hidden line-clamp-2">
        {getDescription()}
      </div>

      {/* Handles for connections */}
      {/* Top handle - for receiving from node above (sequential edges) */}
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
      {/* Bottom handle - for sending to node below (sequential edges) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
      {/* Left handle - for cross-node relationships */}
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
      <Handle
        type="source"
        position={Position.Left}
        id="left"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
      {/* Right handle - for cross-node relationships */}
      <Handle
        type="target"
        position={Position.Right}
        id="right"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!w-2 !h-2 !bg-accent !border-transparent"
      />
    </div>
  );
};

export default memo(CustomNode);
