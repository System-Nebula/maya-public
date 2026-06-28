# Public Boundary

This repository is limited to generic contracts, small helper packages, and
demo-safe application scaffolding.

Do not add:

- private source mappings
- collector watch configuration
- credentials or local service URLs
- generated media or datasets
- internal operations notes

## Research agent

The research bounded context is public upstream. Extension points
(`OperatorHistoryReader`, `ResearchProgressPublisher`) ship with null implementations
here; Discord UX and Firefox history wiring live in internal `~/Workspace`.

Handoff instructions: [research-internal-handoff.md](research-internal-handoff.md)

