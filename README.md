# SDV Fleet Monitor (SDD rebuild)

SDV fleet monitor built from scratch with spec-driven development. Start from `docs/product-brief.md`.

- `CLAUDE.md`: the workflow every feature follows.
- `.claude/skills/`: vendored SDD skills (V1), customized in V2.
- `skills-vendor/VENDOR.md`: where each skill came from and why it was chosen.

Run Claude Code with a clean profile so only this repo's skills load:

    CLAUDE_CONFIG_DIR=~/.claude-sdd claude
