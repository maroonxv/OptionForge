---
name: option-schema-designer
description: Use when Claude Code needs to design or refine normalized persistence models, Chen-notation E-R diagrams, schema docs, or Peewee mappings for option-strategy repositories, especially when the user wants discovery-first schema work before code changes.
argument-hint: "[strategy-slug] [docs-root]"
---

# Option Schema Designer

Design persistence before implementation. Use this skill to discover the right schema for an option-strategy workflow, document it in Chinese, and only then map the approved design to Peewee models.

## Load Order

1. Inspect existing docs, models, and naming in the repository.
2. Read [discovery-checklist.md](references/discovery-checklist.md) first.
3. Read [schema-design-rules.md](references/schema-design-rules.md) before locking entities, keys, or redundancy.
4. Read [schema-doc-template.md](references/schema-doc-template.md) only when you are ready to write the markdown doc.
5. Read [peewee-mapping.md](references/peewee-mapping.md) only after the user explicitly approves the schema doc and asks to continue.
6. Read [example-prompts.md](references/example-prompts.md) only if you need invocation examples.

## Workflow

1. Clarify one domain at a time: contracts, market data, pricing and greeks, execution, risk, restart, or audit.
2. After each domain, summarize confirmed entities, relationships, candidate keys, allowed redundancy, and open questions.
3. If the user wants planning first, or the design is still ambiguous, stop at a structured design summary and do not write files yet.
4. After approval, write:
   - `docs/design/schema/<strategy-slug>.md`
   - `docs/plantuml/code/E-R/<strategy-slug>-er.puml`
5. Render the diagram and insert it into the markdown doc:

```bash
python .claude/skills/option-schema-designer/scripts/render_er_diagram.py --input docs/plantuml/code/E-R/<strategy-slug>-er.puml --output-dir docs/plantuml/charts --jar-path <optional-plantuml-jar>
python .claude/skills/option-schema-designer/scripts/update_schema_doc.py --doc docs/design/schema/<strategy-slug>.md --image docs/plantuml/charts/<strategy-slug>-er.svg --title "<strategy-name> primary E-R diagram"
```

6. Stop again for user review. Only if the user explicitly asks to continue, map the approved schema to Peewee models. Never generate DDL or deployment steps.

## Output Rules

- Keep docs and reference prose in Chinese unless the repository clearly uses another language.
- Keep model, table, field, class, and script identifiers in English.
- Keep core trading facts normalized first. Allow snapshot or projection redundancy only when the doc explains why.
- Reuse existing repository terminology before inventing new names.

## Stop When

- High-impact domain ambiguity remains.
- The user has not approved the design summary.
- The schema doc and E-R diagram are done, but Peewee continuation was not requested.
- The user asks for DDL or deployment instead of design and modeling work.
