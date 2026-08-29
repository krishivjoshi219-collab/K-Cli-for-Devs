# Contributing to K-CLI

Thanks for wanting to contribute — you're literally helping build "lazy dev autopilot."

## The fastest way to contribute

```bash
git clone https://github.com/krishivjoshi219-collab/K-Cli.git
cd K-Cli
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pytest tests/ -v  # make sure all 114 pass before you start
```

## What to work on

Check [open issues](https://github.com/krishivjoshi219-collab/K-Cli/issues) — anything tagged `good first issue` is a great start.

High-impact areas:
- **More model providers** — add Mistral AI, Together.ai, Cohere, Fireworks
- **Ollama model pull** — implement `k-cli models pull <model>` that streams download progress
- **More TUI modals** — new panels for test runner, log viewer, diagram viewer
- **Windows support** — the TUI mostly works; a few path issues to fix
- **Shell completions** — `k-cli --install-completion` bash/zsh/fish
- **Plugin system** — load custom slash commands from `~/.k-cli/plugins/`

## Rules (keep them short)

1. **Run `pytest tests/ -v` before submitting.** If tests break, fix them.
2. **Add a test for new features.** Even a simple one.
3. **Don't add new required dependencies without discussion.** We want `pip install -e .` to stay fast.
4. **Keep PRs focused.** One feature or fix per PR is easier to review.

## Project structure (quick map)

```
k_cli/cli.py              → Typer CLI (add new commands here)
k_cli/tui/tui_app.py      → Textual TUI (add new modals/widgets here)
k_cli/core/               → LLM driver, model hub, credentials, routing
k_cli/agents/             → Adversarial swarm, subagents
k_cli/git/                → Conflict resolver, verifier, patcher, bisect
k_cli/github/             → GitHub client, PR lifecycle, trending
k_cli/tools/              → Doc retriever, MCP client, security healer
tests/                    → pytest test suite (add your tests here)
```

## Commit message format

```
feat(scope): what you added
fix(scope): what you fixed
test(scope): tests added/updated
docs(scope): documentation updated
refactor(scope): code cleanup without behavior change
```

## PR checklist

- [ ] `pytest tests/ -v` passes (114 tests)
- [ ] New feature has at least one test
- [ ] Existing docstrings/comments preserved
- [ ] PR description explains _why_, not just _what_

That's it. PRs welcome.
