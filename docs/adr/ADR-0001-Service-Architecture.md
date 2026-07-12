# ADR-0001: Service-Oriented Architecture

**Status:** Accepted  
**Date:** 2026-07-12  
**Decision Makers:** Atlas Core Team

---

# Context

Atlas is designed as a long-term AI platform that will continue growing in both size and capability.

The project will eventually include:

- Memory
- Knowledge Base
- AI Router
- Planner
- Automation
- Voice
- Skills
- Plugins
- Networking

Without clear separation between these components, the project would become difficult to maintain.

---

# Decision

Atlas will use a Service-Oriented Architecture.

Every major subsystem should be implemented as an independent service whenever practical.

Examples include:

- MemoryService
- KnowledgeService
- AIService
- AutomationService
- VoiceService
- PluginService

Services are registered through the Service Registry during the boot process.

---

# Consequences

Benefits include:

- Modular development
- Easier testing
- Independent maintenance
- Cleaner architecture
- Simplified debugging
- Future plugin support

Potential drawbacks include:

- Slightly more boilerplate code
- More planning before implementation

These trade-offs are acceptable for a long-term project.

---

# Alternatives Considered

## Monolithic Architecture

Rejected because the project is expected to grow significantly over time.

## Direct Module Coupling

Rejected because tightly coupled systems become difficult to maintain.

---

# Outcome

Atlas will continue expanding through independent services coordinated by the Service Registry.

This decision establishes the architectural foundation for future development.