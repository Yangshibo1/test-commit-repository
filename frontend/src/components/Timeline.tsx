import { StepDetail } from '../types';

interface TimelineProps {
  steps: StepDetail[];
  selectedStepId?: string;
  interventionNodeIds?: string[];
  onStepSelect: (step: StepDetail) => void;
}

export default function Timeline({ steps, selectedStepId, interventionNodeIds = [], onStepSelect }: TimelineProps) {
  const interventionNodes = new Set(interventionNodeIds);
  return (
    <div className="h-full overflow-auto p-3.5">
      {steps.length === 0 ? (
        <div className="h-full flex items-center justify-center text-muted text-sm">
          没有可显示的语义 Node
        </div>
      ) : (
        steps.map((step) => (
          <div
            key={step.step_id}
            onClick={() => onStepSelect(step)}
            className={`
              relative border rounded-2xl p-3.5 mb-3 cursor-pointer
              bg-gradient-to-br from-white to-[#fbf3e6]
              transition-all hover:shadow-lg
              ${step.step_id === selectedStepId
                ? 'border-[rgba(217,119,69,0.62)] shadow-[0_14px_34px_rgba(217,119,69,0.11)]'
                : 'border-[rgba(184,165,143,0.5)]'
              }
            `}
          >
            <div className="flex justify-between gap-2 text-muted ot-meta font-mono mb-2">
              <span>序号 {String((step.index || 0)).padStart(2, '0')} · Revision {step.plan_version ?? '—'}</span>
              <span>{interventionNodes.has(step.step_id) ? '人工介入 · ' : ''}{step.status || 'recorded'}</span>
            </div>
            <div className="font-mono ot-meta text-accent mb-1">{step.step_id}</div>
            <div className="font-semibold ot-body">{step.name}</div>
            <div className="text-muted ot-meta mt-1.5">
              {step.result_summary || step.description}
            </div>
            <div className="text-muted ot-meta font-mono mt-2.5 break-all">
              {step.input_files.length} 个输入 → {step.output_files.length} 个输出 · {step.commands_run?.length || 0} 条命令
            </div>
          </div>
        ))
      )}
    </div>
  );
}
