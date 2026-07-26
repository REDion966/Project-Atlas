# Project Atlas

Atlas is a personal AI operating system designed to orchestrate multiple AI models, automate workflows, manage long-term memory, and assist with creative, technical, and business tasks.

## Vision

Atlas is not just another chatbot.

It is an AI ecosystem that can:

- Route tasks to the best AI model
- Remember long-term knowledge
- Work with local and cloud models
- Automate repetitive workflows
- Assist in content creation, software development, cinematography, and business operations

## Current Status

**Phase 7.5 — Unified Cognitive Runtime (Complete)**

Atlas has evolved through 7 major phases covering:

| Capability | Status |
|---|---|
| AI provider abstraction | ✅ Active |
| Conversation management | ✅ Active |
| Memory system (search, rank, store) | ✅ Active |
| Knowledge management | ✅ Active |
| Cognition engine (decision-making) | ✅ Active |
| Reasoning pipeline (plan, analyze, route, dispatch) | ✅ Active |
| Outcome recording & reflection | ✅ Active |
| Planning engine (goal decomposition) | ✅ Active |
| Tool intelligence (select, execute) | ✅ Active |
| Learning feedback loop | ✅ Active |
| Integrated cognitive pipeline | ✅ Active |
| Learning engine (strategy analysis, insights) | ✅ Active |
| World model (causal graph, predictions) | ✅ Active |
| Unified cognitive runtime (14-stage pipeline) | ✅ Active |

**Test suite:** 850 passing tests

**Architecture:** Modular, AI-independent, event-driven. Pure logic layers are isolated from infrastructure. All major subsystems are optional and backward-compatible.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run Atlas
python main.py
```

## Project Structure

```
atlas/
├── kernel/          Service container and root application
├── cognition/       API, context, engine, decisions, pipeline
├── reasoning/       Controller, capabilities, execution, planning, reflection
├── tools/           Tool registry, selector, executor, engine
├── services/        High-level orchestration
├── ai/              Provider abstraction, registry, router
├── memory/          Models, ranking, search, repository, service
├── knowledge/       Knowledge management
├── learning/        Learning manager, knowledge feedback
├── learning_engine/ Strategy analysis, insight consolidation, learning memory
├── understanding/   Concept extraction, pattern analysis, understanding engine
├── evolution/       Self-observation, improvement planning, proposal generation
├── conversation/    Conversation service, history, prompt builder
├── events/          Event bus
├── config/          Configuration system
├── state/           State management
├── task/            Task management
├── workspace/       Workspace, project, resource management
├── cli/             Command-line interface
└── ...              Additional modules (agents, skills, etc.)
```

## Documentation

- `docs/ATLAS_CORE.md` — Permanent architectural principles and rules
- `docs/ATLAS_STATE.md` — Current operational state and resume point
- `docs/DEVELOPMENT_WORKFLOW.md` — Development workflow and verification gates

## Author

AB AL Mamun