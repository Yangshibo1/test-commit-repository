import { StepDetail } from '../types';

interface TimelineProps {
  steps: StepDetail[];
  selectedStepId?: string;
  onStepSelect: (step: StepDetail) => void;
}

export default function Timeline({ steps, selectedStepId, onStepSelect }: TimelineProps) {
  return (
    <div className="h-full overflow-auto p-3.5">
      {steps.length === 0 ? (
        <div className="h-full flex items-center justify-center text-muted text-sm">
          No steps available
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
            <div className="flex justify-between text-muted text-xs font-mono mb-2">
              <span>{String((step.index || 0)).padStart(2, '0')} · {step.operation}</span>
              <span>{step.step_id}</span>
            </div>
            <div className="font-bold text-sm">{step.name}</div>
            <div className="text-muted text-xs mt-1.5 leading-relaxed">
              {step.description}
            </div>
            <div className="text-muted text-[11px] font-mono mt-2.5 break-all">
              {step.input_files.length} inputs → {step.output_files.length} outputs · {step.code_files.length} code files
            </div>
          </div>
        ))
      )}
    </div>
  );
}
