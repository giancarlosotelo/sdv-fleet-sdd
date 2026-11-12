Build the product described in docs/product-brief.md, from scratch, following the workflow in CLAUDE.md.

Start with requirements only:
1. Use the grilling skill to interview me about anything in the brief that is unclear or missing, one question at a time.
2. Then use spec-driven-development to write specs/fleet-monitor.md: every requirement gets an id (REQ-001, ...) and acceptance criteria, and the spec says which features ship in V1.
3. Stop and show me the spec. Don't plan or write code until I approve it.

When you stop, add a row to measurements/dev-log.csv for each step (date, feature, stage, skill, rough minutes, tokens from /cost, defects found, rework notes).
