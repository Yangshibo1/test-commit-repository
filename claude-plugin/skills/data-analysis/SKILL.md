---
description: Record a real Claude Code data-analysis workflow with AgentVAST
---

# AgentVAST data-analysis recording

Claude Code performs the complete data analysis. AgentVAST only records and
validates the workflow; it does not load data, write analysis code, select
algorithms, interpret results, or decide the next analysis action.

The Plugin may be loaded in an ordinary Claude session while no Run is active.
In that state AgentVAST is dormant: do not run recorder commands and do not
invent a Run. Recording begins only after an explicit `[AGENTVAST_ACTIVATE ...]`
control prompt or an AgentVAST Run already bound to this Claude session. Prompts
starting with `[AGENTVAST_CONTROL ...]` are structured Web control messages and
must not be classified as new human analysis input.

For the task "$ARGUMENTS":

AgentVAST is recorded with the built-in Bash tool, not MCP. Run one recording
command at a time. Pass a single-line JSON object in a single-quoted `--payload`
argument. Do not append or pipe another shell command to a recording command.

1. If the Run has no initial files, use `Glob`, `Grep`, and `Read` only as needed
   to understand the task before creating the Plan. Initial or previously declared
   files are context, not a whitelist. After a semantic Node starts, use any relevant
   file that Claude Code can normally access. At `complete-node`, list every file
   actually used; AgentVAST observes its current version and automatically registers
   a previously unknown external file. `declare-inputs` remains an optional early
   hint, not a prerequisite:

   ```bash
   python -m agentvast.agent_cli declare-inputs --payload '{"input_files":["C:/absolute/input.csv"]}'
   ```

   Additional external inputs may also be registered between or during Nodes.
   Never register files under the current Run result directory as Run inputs.
2. Before inspecting data materially, record a semantic plan. Every Node
   `objective` must be written in Chinese:

   ```bash
   python -m agentvast.agent_cli set-plan --payload '{"nodes":[{"node_id":"profile","objective":"检查数据结构与完整性","depends_on":[],"required_artifacts":["code","data"]},{"node_id":"visualize","objective":"可视化主要特征与异常","depends_on":["profile"],"required_artifacts":["visualization"]}]}'
   ```

   Prefer task-relevant files and do not silently substitute an unrelated dataset.
   Treat submitted node IDs as aliases. Read the `set-plan` result and use only
   the returned stable IDs such as `node-001` for subsequent commands. Every
   Claude selects the appropriate non-empty `required_artifacts` subset for each
   Node. The Plan is not required to cover predefined artifact categories.
   In `plan` and `node` checkpoint modes, every successful `set-plan` call
   automatically opens a checkpoint for the newly created Plan Revision. Print
   the task and complete returned Plan in the
   terminal. Stable Node IDs, Chinese objectives, dependencies, and required
   artifact types must exactly match the structured Plan shown in AgentVAST Web;
   do not translate, paraphrase, omit, or add Nodes. End with
   `Plan 已生成，请在右侧查看、编辑或确认。`, then end the turn before analysis.
3. Before Read, Bash, Write, Edit, or NotebookEdit performs material analysis,
   record one active Node:

   ```bash
   python -m agentvast.agent_cli start-node --payload '{"node_id":"node-001"}'
   ```

   Starting establishes the Plan boundary and freezes versions already known from
   the Run and completed upstream Nodes. It does not restrict later file discovery
   or record which inputs were actually used. Use the same `node_id` when completing
   the Node.
4. A Node is one independently explainable data-analysis objective. A Python
   script, command, function, retry, or file creation is not automatically a
   Node. Never create a separate Plan node merely to save, write, export, or
   confirm a file; record that file as the output of the semantic node that
   produced it.
5. Keep implementation details inside the current Node unless you must inspect
   an intermediate result before deciding what analysis comes next, or the
   output becomes the input to another semantic task.
6. Save all analysis artifacts in the current Run's injected result directory,
   using its `code`, `data`, `report`, and `visualization` subdirectories. These
   four category directories already exist; do not create an alternate result
   directory. Every newly created filename must start with its stable ID plus
   underscore, such as `node-001_profile.py`. A later Node may read, reuse, and
   edit an artifact produced by a completed Node without renaming it. When it
   edits that artifact, include the path in `input_files`; AgentVAST records the
   pre-edit version as input and the edited version as the later Node's output.
   Put substantive Python in `.py` or `.ipynb` files and execute the file; do not
   use `python -c` for the analysis.
   Save report artifacts as valid JSON objects in the `report` directory.
7. After observing the real result, record its truthful semantic result:

   ```bash
   python -m agentvast.agent_cli complete-node --payload '{"node_id":"node-001","input_files":["C:/absolute/input.csv"],"operation_summary":"Inspected schema and calculated missing-value and distribution summaries","result_summary":"The file contains 100 rows and 8 columns; two columns have substantial missing values.","analysis_conclusion":"The two high-missingness columns require validation before modeling.","analysis_outcome":"partial"}'
   ```

   `input_files` is required at completion and contains all external files and
   completed-Node outputs actually used during this Node. For known files AgentVAST
   uses the version frozen at Node start; a newly discovered external file is
   observed and registered at completion. AgentVAST discovers changed
   artifacts from the Node-start directory snapshot
   and derives commands and program paths from real Hook events. `output_files`
   is optional cross-checking only. Do not calculate or submit algorithms,
   parameters, output roles, or structured processing results solely for
   recording. Set `analysis_outcome` to `answered`, `partial`,
   `insufficient_data`, `blocked`, `failed`, or `not_assessed` according to the
   real analytical result; execution completion alone does not mean answered.
8. Classify every input event identified by the UserPromptSubmit hook before
   further material analysis using
   `python -m agentvast.agent_cli classify-user-input INPUT_ID INPUT_TYPE`. For
   an explicit checkpoint approval or instruction to continue, use
   `checkpoint_continue`; it resolves immediately and is not a public human
   contribution. For
   guidance, planning, or challenge input, use
   `python -m agentvast.agent_cli apply-user-input INPUT_ID
   "REAL_WORKFLOW_EFFECT"` after making and recording its real effect. Human
   input is not itself a Node.
9. Every executed Node must correspond to a node in the current Plan Revision.
   If an objective, dependency, or required artifact changes, revise the plan first with
   `trigger: "agent_replan"` or `"human_intervention"` and a truthful
   `change_reason`. You may add, remove, or change only future pending Nodes.
   Active/completed Nodes must remain present with the same objective,
   dependencies, and required artifact categories.
10. Follow the Run's injected checkpoint mode:

   - `plan`: every newly created Plan Revision must be presented and explicitly
     approved as `checkpoint_continue`. After approval, execute automatically
     until the Plan changes; then present and await approval for the new Revision.
   - `node`: approve every Plan Revision, and also run `pause-for-user` after every
     completed Node and end the turn.
   - `none`: no human checkpoint is required.

11. Completing the current Plan does not complete the Run. End the Claude turn
    and keep the trace active. A later user request continues the same Run: keep
    completed Node definitions, create a new Chinese Plan Revision with additional
    pending Nodes, present it, and stop for Web editing or approval before executing
    those Nodes. Reuse existing artifacts. Do not call `finish-run`
    automatically. The AgentVAST Web `New Task Trace` action seals and exports the
    current Run before creating a new Run. Use `python -m agentvast.agent_cli state`
    whenever the current recorder state is unclear.

Never invent commands, outputs, observations, decisions, or semantic boundaries
that did not occur.
