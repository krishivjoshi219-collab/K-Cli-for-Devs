# Contributing to K-CLI 🚀

Yo! First off — **thank you so much for wanting to contribute!** Seriously, whether you're fixing a 1-character typo in the docs, adding a sick new terminal color scheme, hooking up a local model, or inventing a brand new agentic superpower — you are what makes open-source awesome.

We don't believe in corporate red tape or 20-page contribution guidelines. Here's everything you need to get hacking in 2 minutes:

---

## ⚡ Quick Dev Setup (Get Hacking in 2 Minutes)

```bash
# 1. Fork and clone the repo
git clone https://github.com/krishivjoshi219-collab/K-Cli.git
cd K-Cli

# 2. Spin up a quick virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install in editable dev mode
pip install -e .

# 4. Run tests to make sure everything's green
pytest
```

---

## 💡 Zero Red Tape / No Stress Rules

- **Don't worry about being 100% perfect**: If you wrote something cool but a test is failing or you're not sure how to structure something, just open a **Draft PR** and drop a comment like *"Hey, got this working but need a hand with XYZ!"*. We'll happily jump in, collaborate, and help you get it merged.
- **Any contribution counts**: Code, docs, fixing typos, adding themes, reporting bugs, suggesting crazy ideas — it's all valued.
- **Keep it focused**: Try to keep PRs focused on one idea or feature so we can review and merge it fast!

---

## 🎨 Fun Ideas You Can Build Right Now!

Looking for inspiration? Here are some awesome starter ideas:

- 🌈 **Terminal Themes**: Add your favorite color themes to the TUI (e.g. *Catppuccin Mocha*, *Tokyo Night*, *Dracula*, *Gruvbox*, *Cyberpunk 2077*).
- 🦙 **New Local SLMs & Cloud Providers**: Hook up new model endpoints (e.g. vLLM, ExLlamaV2, OpenRouter models, Cerebras, Together AI).
- 🛠️ **Language Syntax Support**: Add new compiler/syntax checks in `k_cli/git/verifier.py` (e.g. Zig, Swift, Kotlin, Elixir, Haskell).
- 🔌 **Cool MCP Servers**: Add default presets for popular Model Context Protocol servers (Postgres, Brave Search, Slack, SQLite, Filesystem).
- ⚡ **Your Own Wild Agent Feature**: Built a cool script that does something magical with code? Let's turn it into a `k-cli <command>`!

---

## 🧪 Testing Your Changes

Before you push, just run:

```bash
pytest tests/ -v
```

If it passes, you're golden. Push your branch, open the PR, and we'll celebrate and merge it! 🎉

Thanks again for building with us! ❤️
