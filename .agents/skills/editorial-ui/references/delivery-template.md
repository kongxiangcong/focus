# Delivery record template

Use for a substantial implementation; embed in the existing project process where possible.

```markdown
# UI delivery

## Scope
Primary task:
Mode: Integrate / Standalone / Review
Visual policy: preserve / redesign (Integrate)
Selected specification and execution overrides:
Reference snapshot (Git root/HEAD/status or file hashes):
Product-owned token/motion source:
Required-first / required-final / optional / out-of-scope:
Per-page implementation and verification status:
Files delivered:
Existing contracts retained:
Assumptions and data provenance:

## Implemented behavior
Action → state transition → visible result:
Cancellation/recovery:
Keyboard and focus:
Narrow-screen behavior:

## Validation
| Check | Status | Evidence |
|---|---|---|
| Main interaction | PASS / FAIL / NOT_RUN | command / observation |
| Wide/narrow layout | | viewport + screenshot |
| Keyboard/focus | | sequence |
| IME | | synthetic vs native |
| Error/cancel | | reproduction |
| Motion/theme/contrast | | scope |
| Offline file:// | | request attempts + behavior |

## Remaining limitations
Browser coverage:
Known issues:
Checks not run:
```

Do not turn a small cosmetic patch into a large required documentation project. Do not invent a test report when no browser was available.
