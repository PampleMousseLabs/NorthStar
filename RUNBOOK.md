# NorthStar Runbook

Chromebook/Linux commands for resuming development and SEC/XBRL research.
Copy commands only—not terminal prompts or their output.

## Resume development

```bash
cd ~/PampleMousseLabs/NorthStar
source .venv/bin/activate
```

The environment already exists. Do not recreate it whenever you return.

## SEC identification

Before running a tool that contacts the SEC:

```bash
source ~/.config/northstar/sec.env
```

That local file supplies SEC_USER_AGENT. Keep the contact email outside Git.

## Run the current offline tests

```bash
python -m tests.test_sources &&
python -m tests.test_transforms &&
python -m tests.test_models &&
python -m tests.test_financial_statements &&
python -m tests.test_sec_xbrl_key &&
python -m tests.test_sec_xbrl &&
python -m unittest tests.test_parent_net_income
```

Each command runs only if the preceding command succeeds.

## Run the 100-ticker income-statement research check

Run from the NorthStar repository root:

```bash
source ~/.config/northstar/sec.env
PYTHONPATH=. python Dev_tools/xbrl/scale_is_waterfall.py --limit 100
```

Outputs:

- Dev_tools/xbrl/runlogs/scaled_is_summary.csv
- Dev_tools/xbrl/runlogs/scaled_tag_selection.csv

## Diagnose the existing results

These commands read cached research data and write a local diagnostic report:

```bash
PYTHONPATH=. python Dev_tools/xbrl/diagnose_scaled_is.py --issue NCI_MISMATCH
PYTHONPATH=. python Dev_tools/xbrl/diagnose_scaled_is.py --issue STEP1_MISSING_INPUT
PYTHONPATH=. python Dev_tools/xbrl/diagnose_scaled_is.py --issue STEP1_RESIDUAL
```

## Local research outputs

Dev_tools/xbrl/runlogs/ is Git-ignored.

Keep downloaded JSON, generated CSVs, and research backups there.
Do not force-add that directory to Git.

## Inspect Git before committing

```bash
git status --short
git diff --cached --stat
```

Stage intended code/docs/test files explicitly. Review the staged changes
before committing.

## Current scope

SEC/XBRL remains research, not an approved replacement for Canneberge sources.

A passing unit test verifies software behavior—not accounting correctness.
Derived and fallback values require explicit provenance and review.
Income statement, balance sheet, and cash-flow validation precede integration.

## Filing-level XBRL fact harvest (raw 10-K, includes company extensions)

    source ~/.config/northstar/sec.env
    PYTHONPATH=. python Dev_tools/xbrl/harvest_filing_facts.py MO --terms cost expense

## Top-half IS archetype validation (100-company sample)

    source ~/.config/northstar/sec.env
    PYTHONPATH=. python Dev_tools/xbrl/validate_top_half_archetypes.py
