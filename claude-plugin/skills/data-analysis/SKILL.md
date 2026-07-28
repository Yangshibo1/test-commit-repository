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
   python -m opentrace.agent_cli set-plan --payload '{"nodes":[{"node_id":"n1","objective":"Inspect data structure and quality","depends_on":[]}]}'
   ```

   Use the input files declared by the OpenTrace Run; do not search for substitute
   datasets.
2. Before Read, Bash, Write, Edit, or NotebookEdit performs material analysis,
   record one active step:

   ```bash
   python -m opentrace.agent_cli start-step --payload '{"node_id":"n1","input_files":["C:/absolute/input.csv"]}'
   ```

   Copy the returned `step_id`; it is required when completing the step.
3. A Step is one independently explainable data-analysis objective. A Python
   script, command, function, retry, or file creation is not automatically a
   Step. Never create a separate Plan node merely to save, write, export, or
   confirm a file; record that file as the output of the semantic node that
   produced it.
4. Keep implementation details inside the current Step unless you must inspect
   an intermediate result before deciding what analysis comes next, or the
   output becomes the input to another semantic task.
5. After observing the real result, record its truthful semantic result:

   ```bash
   python -m opentrace.agent_cli complete-step --payload '{"step_id":"step_...","operation_summary":"Inspected schema and calculated missing-value and distribution summaries","output_files":[],"result_summary":"The file contains 100 rows and 8 columns; two columns have substantial missing values.","analysis_conclusion":"The two high-missingness columns require validation before modeling."}'
   ```

   OpenTrace derives commands and program paths from real Hook events. Do not
   calculate or submit algorithms, parameters, output roles, or structured
   statistics only for recording.
6. Classify every input event identified by the UserPromptSubmit hook before
   further material analysis using
   `python -m opentrace.agent_cli classify-user-input`. For
   guidance, planning, or challenge input, use
   `python -m opentrace.agent_cli apply-user-input` after recording its real
   effect. Human input is not itself a Step.
7. Every actual Step must correspond to a node in the current Plan Revision.
   If an objective or dependency changes, revise the plan first with
   `trigger: "agent_replan"` or `"human_intervention"` and a truthful
   `change_reason`. Never rewrite a completed Step to make the workflow look
   cleaner.
8. Run `python -m opentrace.agent_cli finish-run` only after all real Steps are
   complete. Use `python -m opentrace.agent_cli state` whenever the current
   recorder state is unclear.

Never invent commands, outputs, observations, decisions, or semantic boundaries
that did not occur.
