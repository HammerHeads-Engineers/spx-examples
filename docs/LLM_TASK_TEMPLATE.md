# LLM Task Template

Use this template for new-device-model generation tasks.

## Goal
- What is the change and why?
- What are the explicit acceptance criteria?

## Inputs
- Target domain / pack:
- Target protocol:
- Required source constraints (if vendor/protocol-specific):
- Branch policy: PR base is `develop` only.

## Base example
- Closest existing model/profile/test used as a starting point:

## Plan (implementation)
1. 
2. 
3. 

## Files touched
- 

## Runtime smoke test plan (required for new model YAML)
- Model path:
- Smoke test path:
- Bootstrap method (`spx_python` + instance start):
- Protocol probe(s):
- Expected running/healthy criteria:

## Validation
```bash
poetry run python tools/validate_models.py
poetry run pytest
```

## CI remediation loop
- Attempt 1/3:
- Attempt 2/3:
- Attempt 3/3:
- Stop after 3 failed CI attempts and create issue.

## PR summary (target `develop`)
- Source links (first-party):
- Register/attribute rationale:
- `k__` / `cmd__` decisions:
- Validation/test evidence:

## Failure issue summary (if CI failed 3 times)
- Workflow/job links:
- Last error signature:
- Attempted fixes:
- Blocker and recommended manual action:

## Risks or follow-ups
- 
