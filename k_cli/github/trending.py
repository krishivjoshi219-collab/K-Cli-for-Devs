"""
trending.py - GitHub Trending Discovery Engine for K-CLI

Allows developers to discover trending GitHub repositories, AI agent frameworks,
slm projects, and high-growth developer toolchains offline or online.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TrendingRepo:
    """Represents a trending GitHub repository."""
    owner: str
    name: str
    stars: int
    forks: int
    language: str
    description: str
    stars_today: int
    url: str
    topics: List[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner": self.owner,
            "name": self.name,
            "full_name": self.full_name,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "description": self.description,
            "stars_today": self.stars_today,
            "url": self.url,
            "topics": self.topics,
        }


CURATED_TRENDING_REPOS: List[TrendingRepo] = [
    TrendingRepo(
        owner="krishivjoshi219-collab",
        name="K-Cli",
        stars=14200,
        forks=1180,
        language="Python",
        description="The AI coding workstation that lives in your terminal. Self-heals crashes & adversarial swarms.",
        stars_today=420,
        url="https://github.com/krishivjoshi219-collab/K-Cli",
        topics=["ai-agent", "terminal-workstation", "python", "ollama", "cli"],
    ),
    TrendingRepo(
        owner="ollama",
        name="ollama",
        stars=105000,
        forks=9400,
        language="Go",
        description="Get up and running with Llama 3.3, DeepSeek-R1, Qwen2.5-Coder and other large language models.",
        stars_today=1250,
        url="https://github.com/ollama/ollama",
        topics=["llm", "local-ai", "go", "llama3", "ollama"],
    ),
    TrendingRepo(
        owner="astral-sh",
        name="uv",
        stars=48000,
        forks=1600,
        language="Rust",
        description="An extremely fast Python package and project manager, written in Rust.",
        stars_today=890,
        url="https://github.com/astral-sh/uv",
        topics=["python", "rust", "package-manager", "pip", "uv"],
    ),
    TrendingRepo(
        owner="textualize",
        name="textual",
        stars=27500,
        forks=1120,
        language="Python",
        description="The TUI framework for Python with async rendering and CSS layouts.",
        stars_today=340,
        url="https://github.com/textualize/textual",
        topics=["python", "tui", "terminal", "asyncio", "ui"],
    ),
    TrendingRepo(
        owner="vllm-project",
        name="vllm",
        stars=36000,
        forks=4800,
        language="Python",
        description="A high-throughput and memory-efficient LLM serving engine.",
        stars_today=670,
        url="https://github.com/vllm-project/vllm",
        topics=["llm-serving", "paged-attention", "python", "cuda"],
    ),
    TrendingRepo(
        owner="deepseek-ai",
        name="DeepSeek-V3",
        stars=62000,
        forks=7300,
        language="Python",
        description="DeepSeek-V3 and DeepSeek-R1 open weights reasoning model architecture.",
        stars_today=2100,
        url="https://github.com/deepseek-ai/DeepSeek-V3",
        topics=["ai", "deepseek", "moe", "reasoning"],
    ),
    TrendingRepo(
        owner="openclaw",
        name="openclaw",
        stars=387000,
        forks=4000,
        language="TypeScript",
        description="Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞",
        stars_today=3872,
        url="https://github.com/openclaw/openclaw",
        topics=["ai-agent", "typescript", "assistant"],
    ),
]


class TrendingEngine:
    """Discovers trending GitHub repositories via online API search with fallback to curated catalog."""

    def __init__(self, offline_only: bool = False):
        self.offline_only = offline_only

    def get_trending(
        self,
        language: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[TrendingRepo]:
        """Fetches trending repositories based on language or search query."""
        if not self.offline_only:
            try:
                results = self._fetch_github_api(language=language, query=query, limit=limit)
                if results:
                    return results
            except Exception:
                pass

        # Fallback to curated list with local filtering
        repos = list(CURATED_TRENDING_REPOS)
        if language:
            repos = [r for r in repos if r.language.lower() == language.lower()]
        if query:
            q = query.lower()
            repos = [
                r for r in repos
                if q in r.name.lower() or q in r.description.lower() or any(q in t for t in r.topics)
            ]
        return repos[:limit]

    def _fetch_github_api(
        self,
        language: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[TrendingRepo]:
        """Queries GitHub REST API v3 search endpoint."""
        q_parts = ["stars:>100"]
        if language:
            q_parts.append(f"language:{language}")
        if query:
            q_parts.append(query)

        q_str = " ".join(q_parts)
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q_str)}&sort=stars&order=desc&per_page={limit}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "K-CLI-TrendingEngine/1.0.0",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("items", [])
            repos: List[TrendingRepo] = []
            for item in items:
                desc = "".join(ch for ch in (item.get("description") or "") if ord(ch) >= 32 or ch == ' ')
                repos.append(
                    TrendingRepo(
                        owner=item.get("owner", {}).get("login", "unknown"),
                        name=item.get("name", ""),
                        stars=item.get("stargazers_count", 0),
                        forks=item.get("forks_count", 0),
                        language=item.get("language") or "Python",
                        description=desc,
                        stars_today=item.get("stargazers_count", 0) // 100,
                        url=item.get("html_url", ""),
                        topics=item.get("topics", []),
                    )
                )
            return repos
