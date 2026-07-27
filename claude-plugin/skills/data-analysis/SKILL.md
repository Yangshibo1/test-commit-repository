---
description: Record a real Claude Code data-analysis workflow with OpenTrace
---

# OpenTrace data-analysis recording

Claude Code performs the complete data analysis. OpenTrace only records and
validates the workflow; it does not load data, write analysis code, select
algorithms, interpret results, or decide the next analysis action.

For the task "$ARGUMENTS":

OpenTrace is recorded with the built-in Bash tool, not MCP. Run one recording
command at a time. Pass a single-line JSON object in a single-quoted `--payload`
argument. Do not append or pipe another shell command to a recording command.

1. Before inspecting data, record a semantic plan:

   ```bash
   python -m opentrace.agent_cli set-plan --payload '{"nodes":[{"node_id":"n1","objective":"Inspect data structure and quality","step_type":"inspect","depends_on":[]}],"reason":"initial plan"}'
   ```

   Use the input files declared by the OpenTrace Run; do not search for substitute
   datasets.
2. Before Read, Bash, Write, Edit, or NotebookEdit performs material analysis,
   record one active step:

   ```bash
   python -m opentrace.agent_cli start-step --payload '{"node_id":"n1","objective":"Inspect data structure and quality","input_files":["C:/absolute/input.csv"],"completion_condition":"Schema, quality issues, and relevant observations are established","expected_output_roles":["step_output"],"target_data":"declared input data"}'
   ```

   Copy the returned `step_id`; it is required when completing the step.
3. A Step is one independently explainable data-analysis objective. A Python
   script, command, function, retry, or file creation is not automatically a
   Step.
4. Keep implementation details inside the current Step unless you must inspect
   an intermediate result before deciding what analysis comes next, or the
   output becomes the input to another semantic task.
5. After observing the real result, record its truthful semantic result:

   ```bash
   python -m opentrace.agent_cli complete-step --payload '{"step_id":"step_...","operation_summary":"Inspected schema and calculated missing-value and distribution summaries","operation_types":["inspect","aggregate"],"parameters":{},"algorithms":[],"programs":[],"output_files":[],"processing_result":{"rows":100,"columns":8},"analysis_conclusion":{"summary":"Two columns contain substantial missing values"}}'
   ```

   Include inputs, operations, algorithms when relevant, program paths, output
   roles, processing result, and analysis conclusion when relevant.
6. Classify every input event identified by the UserPromptSubmit hook before
   further material analysis using
   `python -m opentrace.agent_cli classify-user-input`. For
   guidance, planning, or challenge input, use
   `python -m opentrace.agent_cli apply-user-input` after recording its real
   effect. Human input is not itself a Step.
7. Revise the plan with `python -m opentrace.agent_cli set-plan`. Never rewrite a
   completed Step to make the workflow look cleaner.
8. Run `python -m opentrace.agent_cli finish-run` only after all real Steps are
   complete. Use `python -m opentrace.agent_cli state` whenever the current
   recorder state is unclear.

Output roles:

- `step_output`: consumed by another Step or independently reviewable.
- `internal_intermediate`: implementation artifact used only inside this Step.
- `temporary`: cache or debug artifact; excluded from formal lineage.

Never invent commands, outputs, observations, decisions, or semantic boundaries
that did not occur.
