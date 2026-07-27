---
description: Record a real Claude Code data-analysis workflow with OpenTrace
---

# OpenTrace data-analysis recording

Claude Code performs the complete data analysis. OpenTrace only records and
validates the workflow; it does not load data, write analysis code, select
algorithms, interpret results, or decide the next analysis action.

For the task "$ARGUMENTS":

1. Inspect enough context to propose a semantic plan, then call
   `opentrace_set_plan`.
2. Before Read, Bash, Write, Edit, or NotebookEdit performs material analysis,
   call `opentrace_start_step`.
3. A Step is one independently explainable data-analysis objective. A Python
   script, command, function, retry, or file creation is not automatically a
   Step.
4. Keep implementation details inside the current Step unless you must inspect
   an intermediate result before deciding what analysis comes next, or the
   output becomes the input to another semantic task.
5. After observing the real result, call `opentrace_complete_step`. Record:
   inputs, operations, algorithms when relevant, program paths, output roles,
   processing result, and analysis conclusion when relevant.
6. Classify every input event identified by the UserPromptSubmit hook before
   further material analysis. For guidance, planning, or challenge input, call
   `opentrace_apply_user_input` after recording its real effect. Human input is
   not itself a Step.
7. Revise the plan by calling `opentrace_set_plan` again. Never rewrite a
   completed Step to make the workflow look cleaner.
8. Call `opentrace_finish_run` only after all real Steps are complete.

Output roles:

- `step_output`: consumed by another Step or independently reviewable.
- `internal_intermediate`: implementation artifact used only inside this Step.
- `temporary`: cache or debug artifact; excluded from formal lineage.

Never invent commands, outputs, observations, decisions, or semantic boundaries
that did not occur.
