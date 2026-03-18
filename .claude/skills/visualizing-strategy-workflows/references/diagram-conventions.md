# Diagram Conventions

## Naming

- Architecture source: `docs/plantuml/code/<workflow-slug>-architecture.puml`
- Data-flow source: `docs/plantuml/code/<workflow-slug>-data-flow.puml`
- Sequence source: `docs/plantuml/code/<workflow-slug>-sequence.puml`
- Optional state source: `docs/plantuml/code/<workflow-slug>-state.puml`

## Architecture Diagram

- Show the workflow as the center of the diagram.
- Include only the collaborators that materially affect orchestration.
- Group collaborators by role when it improves readability: gateways, aggregates, services, persistence, observability.
- Use short edge labels such as `loads config`, `updates aggregate`, `records snapshot`.

## Data-Flow Diagram

- Show the main business payloads moving through the workflow.
- Prefer business nouns over implementation trivia.
- Label transformations and decision points.

## Sequence Diagram

- Show the real call order for the primary workflow path.
- Pick one representative happy-path sequence per workflow.
- Add `alt` / `opt` blocks only for meaningful branches.

## PlantUML Style

- Use readable titles.
- Prefer consistent aliases for the workflow and key collaborators.
- Keep diagrams compact enough to embed cleanly in markdown.
- Replace scaffold placeholders instead of expanding diagrams into exhaustive call graphs.
