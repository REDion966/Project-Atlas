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

**Phase 6.9 — Tool Intelligence Foundation (Complete)**

Atlas has evolved through 6 major phases covering:

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

**Test suite:** 584 passing tests

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
├── cognition/       API, context, engine, decisions
├── reasoning/       Controller, capabilities, execution, planning, reflection
├── tools/           Tool registry, selector, executor, engine
├── services/        High-level orchestration
├── ai/              Provider abstraction, registry, router
├── memory/          Models, ranking, search, repository, service
├── knowledge/       Knowledge management
├── learning/        Learning manager, knowledge feedback
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