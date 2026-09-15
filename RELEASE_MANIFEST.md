# AgentVAST latest snapshot manifest

Snapshot branch: `agentvast-9-15-latest`

Snapshot date: 2026-09-15 (Asia/Shanghai)

## Included system code

- `agentvast/`: AgentVAST Python package, including constrained workflow recording,
  Passive Observer, transcript reconstruction, semantic workflow generation, Reviewer,
  Web backend, artifact tracking, and file lineage.
- `frontend/`: current Chinese Web frontend, including the Claude terminal, workflow
  visualization, Passive Observer, semantic workflow, raw Event evidence, readable tool
  requests, and grouped task-planning evidence.
- `claude-plugin/`: constrained workflow Claude Code plugin.
- `claude-observer-plugin/`: passive Claude Code observer plugin.
- `tests/`: current automated tests.
- `examples/`: small reproducible examples.
- Repository-root launch and utility scripts, including `启动AgentVAST.bat`.

## Included documentation

- `README.md` and `CLAUDE.md`.
- `docs/`: current system design, Passive Observer, Semantic Workflow, and archived
  implementation history.
- `.env.example`: configuration names and safe placeholder values only.

## Included version-controlled data and analysis outputs

- `VAST_Challenge_2026_MC2/src/`: version-controlled analysis scripts and derived
  intermediate JSON/TXT results used by the existing MC2 case study.
- `VAST_Challenge_2026_MC2/meeting_datasets/`: small derived CSV datasets.
- `VAST_Challenge_2026_MC2/report_question_visualizations/` and
  `VAST_Challenge_2026_MC2/visualizations/`: version-controlled case-study visualizations.
- `VAST_Challenge_2026_MC2/artifacts_llm/` and `context/`: existing case-study review and
  context artifacts.
- `result/`: existing version-controlled reproducibility outputs used by the repository.

The largest tracked file in this snapshot is the derived
`VAST_Challenge_2026_MC2/src/node_01_loaded.json` (about 63.9 MB), which remains below
GitHub's 100 MB per-file limit.

## Deliberately excluded

- `.env` and all real API credentials.
- `.agentvast/`, `.opentrace/`, `.claude/` local sessions, transcripts, observations,
  SQLite databases, and private runtime state.
- `frontend/node_modules/`, build output, Python caches, pytest caches, scratch files,
  temporary worktrees, and local backups.
- The original VAST Challenge input file
  `VAST_Challenge_2026_MC2/MC2 data.json` (about 70.2 MB). It is intentionally ignored
  and is not part of this GitHub snapshot. Users must obtain authorized source data
  separately and place it at that path when reproducing the MC2 case study.
- Other untracked or ignored raw VAST datasets.

## Reproduction notes

1. Copy `.env.example` to `.env` and provide local credentials. Never commit `.env`.
2. Install the required extras described in `README.md`.
3. For the MC2 case study, separately obtain the original dataset and place it at
   `VAST_Challenge_2026_MC2/MC2 data.json`.
4. On Windows, run `启动AgentVAST.bat --diagnose` before starting the services.
