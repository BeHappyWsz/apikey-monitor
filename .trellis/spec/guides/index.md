# Thinking Guides

> **Purpose**: Expand your thinking to catch things you might not have considered.
>
> **Project note (apikey-monitor)**: stack is Python stdlib + vanilla ESM. When examples in the thinking guides mention React/TypeScript components, map them to `static/js` modules, `services/*`, and `api/router.py` boundaries instead.

---

## Why Thinking Guides?

**Most bugs and tech debt come from "didn't think of that"**, not from lack of skill:

- Didn't think about layer boundaries ? cross-layer bugs
- Didn't think about repeated patterns ? duplication
- Didn't think about edge cases ? runtime errors
- Didn't think about other machines / existing `data.db` ? broken upgrades

These guides help you **ask the right questions before coding**.

---

## Available Guides

| Guide | Purpose | When to Use |
|-------|---------|-------------|
| [Local Development & Portability](./local-dev-and-portability.md) | Run the same project on multiple PCs safely | First clone, new machine, env/DB questions |
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | Reduce duplication | When you notice repeated logic |
| [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) | Data flow across layers | Features spanning API / service / DB / UI |

---

## Quick Reference: Thinking Triggers

### When to Think About Portability

- [ ] Developing on a second computer or OS
- [ ] Tests might touch `data.db`
- [ ] Changing listen host/port or restart behavior
- [ ] Adding env-specific paths

? Read [Local Development & Portability](./local-dev-and-portability.md)

### When to Think About Cross-Layer Issues

- [ ] Feature touches 3+ layers (API, Service, UI, Database)
- [ ] Data format changes between layers
- [ ] List vs secret field exposure
- [ ] Settings dual-write (SQLite + `config.json`)
- [ ] UI assumes a settings flag that services do not read yet

? Read [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) and backend [Services & Runtime](../backend/services-runtime.md)

### When to Think About Code Reuse

- [ ] Writing logic similar to `core/` / `state.js` / `utils.js`
- [ ] New export format, import parser, or probe path
- [ ] Copy-pasting mask/export/probe helpers

? Read [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md)

### Pre-Modification Rule (CRITICAL)

Before changing a field name, status string, or settings key:

1. Search the repo for the old symbol (`rg` / IDE).
2. Update backend validator + DB + UI + `docs/api.md` + tests together.
3. Prefer additive migrations over renames when user DBs exist.

---

## How to Use This Directory

Read the relevant guide **before** implementing, not only during review. Spec layer indexes (`backend/index.md`, `frontend/index.md`) list file-level coding rules; these guides cover judgment calls.

---

## Contributing

If you discover a recurring mistake on this project, add a short bullet here or to the matching layer spec with a real file path reference. Keep language English in `.trellis/spec/`.
