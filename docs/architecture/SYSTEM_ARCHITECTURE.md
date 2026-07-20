============================================================
PROJECT ATLAS - SYSTEM CONTEXT & DEVELOPMENT GUIDELINES
============================================================

Purpose:
This file provides persistent context for future Atlas development
sessions. Before making any architectural decision, review this file
to maintain project continuity and prevent accidental architectural
damage.

============================================================
PROJECT IDENTITY
============================================================

Project Name:
Atlas

Assistant Project Role:
Selena

Atlas is not a normal chatbot.

Atlas is designed as a modular AI operating framework capable of:

- independent reasoning
- problem solving
- research assistance
- knowledge acquisition
- self-improvement through controlled development
- interaction with multiple AI models
- future AI technology adaptation

The final goal is to create an AI system that can:

- understand tasks
- research solutions
- analyze problems
- propose improvements
- modify or extend its own capabilities only with user permission
- maintain long-term memory and context
- operate as an intelligent development partner


============================================================
CURRENT PRIMARY OBJECTIVE
============================================================

Current development phase:

Complete Atlas Core Model.

The immediate goal is NOT to make Atlas fully autonomous yet.

The current priority is building a strong foundation so Atlas can
eventually develop itself safely and intelligently.

Quality must always be prioritized over speed.

Never sacrifice:

- architecture quality
- maintainability
- scalability
- security
- testing
- documentation

Avoid shortcuts that create future technical debt.


============================================================
CURRENT DEVELOPMENT STRATEGY
============================================================

Development order:

Phase 1:
Core Foundation

Includes:

- Kernel
- Service Container
- Lifecycle Management
- State System
- Event System


Phase 2:
AI Architecture

Includes:

- AI Provider system
- Multiple AI model support
- AI routing
- Model abstraction
- Future model compatibility


Phase 3:
Conversation System

Includes:

- conversation handling
- context integration
- user interaction layer


Phase 4:
Memory Evolution

Includes:

- memory storage
- memory retrieval
- ranking system
- search system
- context generation
- long-term memory architecture


Phase 5:
Knowledge System

Includes:

- information management
- research capability
- knowledge expansion


Phase 6:
Workspace System

Includes:

- project management
- resources
- permissions
- controlled file operations


Phase 7:
Task System

Includes:

- task planning
- execution
- scheduling


Phase 8:
Self Improvement Layer

Future capability:

Atlas can:

- research
- suggest improvements
- analyze its own architecture
- request permission before modifications
- safely evolve


============================================================
CURRENT STABLE ARCHITECTURE
============================================================


Atlas

|
├── Kernel
|
├── AI Layer
|
├── Conversation Layer
|
├── Memory Layer
|
├── Knowledge Layer
|
├── Workspace Layer
|
├── Task Layer
|
├── Event System
|
└── State System



============================================================
KERNEL
============================================================

Responsible for:

- startup
- lifecycle
- system coordination
- connecting major subsystems


============================================================
SERVICE CONTAINER
============================================================

Responsible for:

- dependency registration
- dependency management
- service lifecycle


All major services should be connected through controlled
dependency management.

Avoid unnecessary direct coupling.


============================================================
AI LAYER
============================================================

Responsible for:

- AI provider abstraction
- model communication
- multiple model support
- future AI compatibility


Atlas should not depend on a single AI model.


============================================================
CONVERSATION LAYER
============================================================

Responsible for:

- user interaction
- conversation flow
- context usage


Conversation should use memory and knowledge systems.


============================================================
MEMORY LAYER
============================================================

Responsible for:

- storing information
- retrieving information
- ranking memories
- searching memories
- providing context


Current memory architecture:

Memory

|
├── Models
|
├── Repository
|
├── Storage
|
├── Search Engine
|
├── Ranking Engine
|
├── Context Engine
|
└── Memory Manager Service



Important:

Memory architecture should evolve carefully.

Do not randomly rename, remove, or duplicate memory components.


============================================================
WORKSPACE LAYER
============================================================

Responsible for:

- projects
- resources
- permissions
- controlled access


Workspace will eventually allow Atlas to work with files,
projects, and development environments safely.


============================================================
IMPORTANT ARCHITECTURAL RULES
============================================================

1. Never modify architecture without understanding existing design.

2. Before adding files:
   - check existing modules
   - check imports
   - check dependency flow

3. Before removing files:
   - verify no dependency exists

4. Avoid duplicate systems.

5. Maintain backward compatibility when possible.

6. Every major change requires:

   - tests
   - documentation
   - validation


============================================================
GIT WORKFLOW
============================================================

Git is the source of truth.

Before major changes:

Create branch:

feature-name


Example:

phase5-memory-evolution


Never directly experiment on stable branches.


Stable checkpoints:

Use tags.

Example:

v0.5.3-stable


Before risky migrations:

Create backup branch.


Example:

backup-memory-migration


Always run:

git status

pytest

before committing.


============================================================
CURRENT RECOVERY LESSON
============================================================

Previous memory migration issue happened because:

- architecture changed too aggressively
- old and new memory systems existed together
- responsibilities became unclear
- compatibility layer was incomplete


Future migrations must happen incrementally:

Step 1:
Understand current system.

Step 2:
Design migration plan.

Step 3:
Add new architecture beside old.

Step 4:
Move dependencies gradually.

Step 5:
Remove old code only after validation.


============================================================
SELENA DEVELOPMENT RULE
============================================================

When working on Atlas:

Do not rush.

Do not create unnecessary files.

Do not redesign existing architecture without reason.

Protect the original vision.

The objective is not just working code.

The objective is building the foundation of a future intelligent
AI operating framework.


============================================================
END OF ATLAS PROJECT CONTEXT
============================================================