# Atlas Development Rules

Version: 1.0

Purpose:
This document defines the development rules for Project Atlas to protect the architecture, maintain quality, and prevent uncontrolled changes.

---

# 1. Core Principle

Atlas is not a normal application.

Atlas is designed as a long-term autonomous AI operating framework.

Every change must preserve:

- modular architecture
- extensibility
- maintainability
- self-improvement capability
- future AI model compatibility

Quality must never be sacrificed for speed.

---

# 2. Development Workflow

Every major change follows this process:

1. Understand current architecture
2. Inspect existing implementation
3. Check dependencies
4. Create a development branch
5. Implement changes
6. Run full test suite
7. Review architecture impact
8. Commit changes
9. Merge only after validation


No direct modification of stable branches.

---

# 3. Branch Rules

Main:

Purpose:
Stable production-ready Atlas state.

Rules:

- Must always pass all tests
- No experimental changes
- No unfinished architecture


Feature branches:

Format:

feature-name


Examples:

phase5-memory-evolution

feature-learning-engine

feature-agent-planning


All experimental development happens here.

---

# 4. Before Modifying Existing Architecture

Before changing any existing file:

Check:

- Who imports this file?
- What services depend on it?
- Does the kernel use it?
- Does the service container register it?
- Are tests covering it?
- Does it affect future autonomy?


Never replace a component without understanding its role.

---

# 5. Architecture Rules

Atlas follows layered architecture:

Atlas Kernel

Responsible for:

- startup
- lifecycle
- coordination


AI Layer

Responsible for:

- AI providers
- model communication
- routing


Conversation Layer

Responsible for:

- user interaction
- context handling


Memory Layer

Responsible for:

- storing memories
- retrieval
- ranking
- context generation


Knowledge Layer

Responsible for:

- information management
- learning systems


Workspace Layer

Responsible for:

- projects
- resources
- permissions


Task Layer

Responsible for:

- scheduling
- execution


Event System

Responsible for:

- communication between systems


State System

Responsible for:

- runtime state tracking

---

# 6. Dependency Rules

Components should depend on abstractions, not implementations.

Avoid:

Direct imports between unrelated systems.

Prefer:

Service interfaces
Repositories
Dependency injection


---

# 7. Testing Requirement

Before committing:

Run:

pytest


A change is incomplete if tests fail.

New architecture requires:

- unit tests
- integration tests
- regression checks

---

# 8. Documentation Requirement

Every major architectural change requires documentation.

Required:

- architecture explanation
- reason for change
- future purpose
- migration notes


---

# 9. Memory System Rules

Memory is a core Atlas intelligence subsystem.

Changes must preserve:

- storage reliability
- retrieval accuracy
- ranking quality
- context generation
- future learning capability


Never simplify memory architecture only to fix a test.

---

# 10. AI Evolution Principle

Atlas should remain compatible with:

- current AI models
- future AI models
- local models
- cloud models
- multi-model systems


Do not hardcode Atlas to one provider.

---

# 11. Autonomous Development Principle

Future Atlas should be able to:

- research
- analyze code
- suggest improvements
- modify approved systems
- test changes
- request permission before dangerous actions


Current development must prepare for this capability.

---

# 12. Emergency Recovery Procedure

If architecture becomes unstable:

1. Stop modifying files
2. Check git history
3. Restore last stable tag
4. Create recovery branch
5. Analyze failure
6. Restart development carefully


Never continue random fixes on broken architecture.

---

# 13. Golden Rule

Do not ask:

"How can we make this work quickly?"

Ask:

"How does this improve Atlas as a long-term intelligent system?"

Every decision must serve the future Atlas architecture.