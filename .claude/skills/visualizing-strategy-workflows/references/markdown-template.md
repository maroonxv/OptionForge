# Markdown Template

Use this structure for each workflow doc:

```md
# <Workflow Title>

- Source: `<relative/path/to/workflow_file.py>`
- Primary entrypoint: `<ClassName.method>`

## Responsibility

<2-4 short sentences>

## Architecture

![<workflow title> architecture](../plantuml/chart/<workflow-slug>-architecture.svg)

## Data Flow

![<workflow title> data flow](../plantuml/chart/<workflow-slug>-data-flow.svg)

## Sequence

![<workflow title> sequence](../plantuml/chart/<workflow-slug>-sequence.svg)

## State

Include only when a real state or mode transition exists:

![<workflow title> state](../plantuml/chart/<workflow-slug>-state.svg)

## Notes

- Key collaborators: ...
- Inputs: ...
- Outputs: ...
```

Prefer flat bullets and short paragraphs. Avoid long narrative explanations.
