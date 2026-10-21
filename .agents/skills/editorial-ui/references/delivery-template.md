# Delivery record

Use for Substantial implementation tasks, embedded in the existing tracker. Link the [implementation brief](brief-schema.md) instead of repeating its schema. Tiny and Small tasks may use a concise result plus relevant evidence.

```markdown
# UI delivery

Brief: <existing spec/issue path>
Changes since brief: <approved scope/decision changes, or none>
Files/routes delivered:

## Implemented behavior
Action → state transition → visible result:
Recovery and retained state:

## Validation
| Scenario | Status | Evidence basis | Evidence / environment / reason |
|---|---|---|---|
| <acceptance scenario from brief> | | | |

## Remaining work
Required gaps, known issues, next action:
```

Use the vocabulary and evidence limits in [quality gates](quality-gates.md#evidence-levels). Include only scenarios applicable to the task; keep implementation completion separate from verification status.
