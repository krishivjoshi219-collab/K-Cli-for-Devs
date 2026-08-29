"""
dedup_engine.py - Intelligent Repository & Request Deduplication Engine for K-CLI

Features:
1. Multi-tier semantic and lexical similarity analysis (BM25, Jaccard, token overlap, string distance, stemming, prefix matching).
2. Deep AST symbol extraction and indexing powered by RepoMap.
3. Git commit history scanning (commit messages, diff stats, issue/PR references).
4. Code snippet and symbol duplicate detection with precise line ranges.
5. Structured DedupMatch results with confidence scores and explainability.
"""

from __future__ import annotations

import difflib
import math
import os
import re
import subprocess
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from k_cli.git.repo_map import RepoMap
except ModuleNotFoundError:
    try:
        from repo_map import RepoMap
    except ModuleNotFoundError:
        RepoMap = None  # type: ignore


@dataclass
class DedupMatch:
    """Structured result of a deduplication query check."""
    is_duplicate: bool
    confidence: float  # Score from 0.0 to 1.0
    existing_commit: Optional[str] = None  # Commit hash if matched in git history
    file_path: Optional[str] = None  # File path if matched in codebase
    line_range: Optional[Tuple[int, int]] = None  # (start_line, end_line) in file
    explanation: str = ""  # Human-readable rationale
    match_type: str = "none"  # "commit", "symbol", "issue_pr", "snippet", "none"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes DedupMatch to dictionary."""
        return {
            "is_duplicate": self.is_duplicate,
            "confidence": round(self.confidence, 4),
            "existing_commit": self.existing_commit,
            "file_path": self.file_path,
            "line_range": list(self.line_range) if self.line_range else None,
            "explanation": self.explanation,
            "match_type": self.match_type,
            "metadata": self.metadata,
        }


@dataclass
class CommitRecord:
    """Structured git commit record."""
    commit_hash: str
    short_hash: str
    author: str
    date: str
    subject: str
    body: str
    files: List[str] = field(default_factory=list)
    diff_stat: str = ""
    issue_refs: List[str] = field(default_factory=list)


@dataclass
class SymbolRecord:
    """Structured AST symbol record."""
    name: str
    type: str  # "class", "function", "method", "struct", "interface", etc.
    file_path: str
    rel_path: str
    line_number: int
    end_lineno: int
    signature: str
    docstring: Optional[str] = None


class SimilarityScorer:
    """
    Computes lexical, statistical (BM25), and set-based similarity metrics
    between search queries, commit records, and source code tokens.
    """

    STOP_WORDS: Set[str] = {
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "can", "could", "should", "would", "will", "this",
        "that", "these", "those", "it", "its", "as", "if", "each", "all", "both",
        "into", "through", "during", "before", "after", "above", "below", "up", "down",
        "create", "implement", "add", "build", "write", "make", "new",
    }

    @classmethod
    def stem_token(cls, token: str) -> str:
        """Lightweight stemmer for common suffixes and domain prefixes in code."""
        t = token.lower()
        if t.startswith("auth"):
            return "auth"
        if t.startswith("calc"):
            return "calc"
        if t.startswith("valid"):
            return "valid"
        if t.startswith("config"):
            return "config"
        if t.startswith("init"):
            return "init"

        if len(t) > 5:
            for suffix in ("ation", "izing", "ising", "ator", "tion", "ment", "ness", "able", "ible"):
                if t.endswith(suffix):
                    return t[:-len(suffix)]
        if len(t) > 4:
            for suffix in ("ing", "ies", "ied", "ers", "est", "ant", "ent"):
                if t.endswith(suffix):
                    return t[:-len(suffix)]
        if len(t) > 3:
            for suffix in ("ed", "er", "es", "ly"):
                if t.endswith(suffix):
                    return t[:-len(suffix)]
            if t.endswith("s") and not t.endswith("ss"):
                return t[:-1]
        return t

    @classmethod
    def tokenize(cls, text: str, stem: bool = False) -> List[str]:
        """
        Code-aware tokenization:
        - Splits acronyms & camelCase (`JWTTokenHandler` -> `jwt`, `token`, `handler`)
        - Splits snake_case and kebab-case (`calculate_total_score` -> `calculate`, `total`, `score`)
        - Normalizes to lowercase and removes punctuation and stop words.
        """
        if not text:
            return []

        s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s1)
        raw_tokens = re.findall(r"[A-Za-z0-9]+", s2.lower())

        tokens: List[str] = []
        for t in raw_tokens:
            if len(t) > 1 and t not in cls.STOP_WORDS:
                tokens.append(cls.stem_token(t) if stem else t)
        return tokens

    @classmethod
    def _match_tokens(cls, t1: str, t2: str) -> bool:
        """Returns True if tokens match directly, via stemming, or via common code prefixes."""
        if t1 == t2:
            return True
        st1 = cls.stem_token(t1)
        st2 = cls.stem_token(t2)
        if st1 == st2:
            return True
        if len(t1) >= 4 and len(t2) >= 4:
            if t1.startswith(t2) or t2.startswith(t1):
                return True
        return False

    @classmethod
    def jaccard_similarity(cls, tokens1: List[str], tokens2: List[str]) -> float:
        """Calculates Jaccard set similarity between two token lists with stemming support."""
        s1 = {cls.stem_token(t) for t in tokens1}
        s2 = {cls.stem_token(t) for t in tokens2}
        if not s1 or not s2:
            return 0.0
        intersection = sum(1 for t1 in s1 if any(cls._match_tokens(t1, t2) for t2 in s2))
        union = len(s1 | s2)
        return intersection / union if union > 0 else 0.0

    @classmethod
    def token_overlap(cls, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Calculates query token containment / overlap ratio in document with stemming."""
        if not query_tokens:
            return 0.0
        q_set = {cls.stem_token(t) for t in query_tokens}
        d_set = {cls.stem_token(t) for t in doc_tokens}
        overlap = sum(1 for q in q_set if any(cls._match_tokens(q, d) for d in d_set))
        return overlap / len(q_set) if q_set else 0.0

    @classmethod
    def bm25_score(
        cls,
        query_tokens: List[str],
        doc_tokens: List[str],
        corpus_doc_freq: Dict[str, int],
        total_docs: int,
        avg_doc_len: float,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """
        Calculates normalized BM25 score in range [0.0, 1.0].
        """
        if not query_tokens or not doc_tokens:
            return 0.0

        q_stemmed = [cls.stem_token(t) for t in query_tokens]
        d_stemmed = [cls.stem_token(t) for t in doc_tokens]

        doc_len = len(d_stemmed)
        doc_counts = Counter(d_stemmed)
        score = 0.0

        matched_terms = 0
        total_q_terms = len(set(q_stemmed))

        for q in set(q_stemmed):
            df = corpus_doc_freq.get(q, 1)
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
            if idf < 0:
                idf = 0.1

            tf = sum(count for term, count in doc_counts.items() if cls._match_tokens(q, term))
            if tf > 0:
                matched_terms += 1
                numerator = tf * (k1 + 1.0)
                denominator = tf + k1 * (1.0 - b + b * (doc_len / (avg_doc_len or 1.0)))
                term_score = (numerator / denominator)
                score += idf * term_score

        coverage = matched_terms / total_q_terms if total_q_terms > 0 else 0.0
        saturation = (score / (total_q_terms * (k1 + 1.0))) if total_q_terms > 0 else 0.0
        normalized = 0.6 * coverage + 0.4 * min(1.0, saturation * 1.5)
        return min(1.0, max(0.0, normalized))

    @classmethod
    def string_similarity(cls, str1: str, str2: str) -> float:
        """Calculates SequenceMatcher string similarity ratio."""
        return difflib.SequenceMatcher(None, str1.lower().strip(), str2.lower().strip()).ratio()

    @classmethod
    def composite_similarity(
        cls,
        query: str,
        target_text: str,
        corpus_doc_freq: Optional[Dict[str, int]] = None,
        total_docs: int = 1,
        avg_doc_len: float = 20.0,
    ) -> float:
        """
        Calculates weighted composite similarity score combining BM25,
        Jaccard similarity, query token overlap, and string distance.
        """
        q_tokens = cls.tokenize(query)
        t_tokens = cls.tokenize(target_text)

        if not q_tokens or not t_tokens:
            return 0.0

        jaccard = cls.jaccard_similarity(q_tokens, t_tokens)
        overlap = cls.token_overlap(q_tokens, t_tokens)
        str_sim = cls.string_similarity(query, target_text)

        bm25 = 0.0
        if corpus_doc_freq and total_docs > 0:
            bm25 = cls.bm25_score(
                query_tokens=q_tokens,
                doc_tokens=t_tokens,
                corpus_doc_freq=corpus_doc_freq,
                total_docs=total_docs,
                avg_doc_len=avg_doc_len,
            )
        else:
            bm25 = overlap

        # Composite score
        composite = 0.40 * overlap + 0.30 * bm25 + 0.20 * jaccard + 0.10 * str_sim
        return min(1.0, max(0.0, composite))


class DedupEngine:
    """
    Repository and Request Deduplication Engine for K-CLI.
    
    Identifies duplicate tasks, redundant code additions, existing AST symbols,
    and past git commits to prevent duplicative work across large projects.
    """

    def __init__(
        self,
        repo_path: str = ".",
        duplicate_threshold: float = 0.65,
        git_depth: int = 50,
    ):
        """
        Initializes DedupEngine.
        
        Args:
            repo_path: Target repository path.
            duplicate_threshold: Confidence score threshold (0.0 to 1.0) to mark as duplicate.
            git_depth: Max commit history depth to scan by default.
        """
        self.repo_path = Path(repo_path).resolve()
        self.duplicate_threshold = duplicate_threshold
        self.git_depth = git_depth
        self._repo_map: Optional[Any] = None
        self._cached_symbols: Optional[List[SymbolRecord]] = None
        self._cached_commits: Optional[List[CommitRecord]] = None

    def get_repo_map(self) -> Any:
        """Lazy loads RepoMap instance."""
        if self._repo_map is None and RepoMap is not None:
            self._repo_map = RepoMap(root_dir=str(self.repo_path))
        return self._repo_map

    # =========================================================================
    # Git History Indexing & Extraction
    # =========================================================================

    def get_git_commits(self, depth: Optional[int] = None) -> List[CommitRecord]:
        """
        Extracts recent commit records, messages, diff stats, and issue references.
        
        Args:
            depth: Max number of commits to retrieve.
            
        Returns:
            List of CommitRecord objects.
        """
        if self._cached_commits is not None and (depth is None or len(self._cached_commits) >= depth):
            return self._cached_commits[:depth] if depth else self._cached_commits

        max_depth = depth or self.git_depth
        commits: List[CommitRecord] = []

        if not self.repo_path.exists() or not (self.repo_path / ".git").exists():
            return []

        sep_field = "%x1f"
        sep_record = "%x1e"
        format_str = f"COMMIT_START{sep_field}%H{sep_field}%h{sep_field}%an{sep_field}%ad{sep_field}%s{sep_field}%b{sep_record}"

        cmd = [
            "git",
            "log",
            f"-n{max_depth}",
            f"--pretty=format:{format_str}",
            "--stat",
        ]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                errors="ignore",
            )
            if res.returncode != 0 or not res.stdout.strip():
                return []

            raw_entries = res.stdout.split("COMMIT_START\x1f")
            issue_regex = re.compile(r"\b(?:closes?|closed|fixes?|fixed|resolves?|resolved|pr|issue|pull\s+request)\s*#?(\d+)\b", re.IGNORECASE)

            for entry in raw_entries:
                if not entry.strip():
                    continue

                parts = entry.split("\x1e", 1)
                meta_part = parts[0]
                stat_part = parts[1] if len(parts) > 1 else ""

                fields = meta_part.split("\x1f")
                if len(fields) < 5:
                    continue

                commit_hash = fields[0].strip()
                short_hash = fields[1].strip()
                author = fields[2].strip()
                date = fields[3].strip()
                subject = fields[4].strip()
                body = fields[5].strip() if len(fields) > 5 else ""

                # Extract modified files from stat
                files_changed: List[str] = []
                for line in stat_part.splitlines():
                    if "|" in line:
                        file_token = line.split("|")[0].strip()
                        if file_token:
                            files_changed.append(file_token)

                # Extract issue references
                full_msg = f"{subject}\n{body}"
                issue_refs: List[str] = []
                for match in issue_regex.finditer(full_msg):
                    issue_refs.append(f"#{match.group(1)}")

                record = CommitRecord(
                    commit_hash=commit_hash,
                    short_hash=short_hash,
                    author=author,
                    date=date,
                    subject=subject,
                    body=body,
                    files=files_changed,
                    diff_stat=stat_part.strip(),
                    issue_refs=sorted(set(issue_refs)),
                )
                commits.append(record)

        except Exception:
            return []

        self._cached_commits = commits
        return commits

    # =========================================================================
    # AST Symbol Table Extraction & Indexing
    # =========================================================================

    def get_ast_symbols(self) -> List[SymbolRecord]:
        """
        Extracts all AST symbol records across supported source files in the repository.
        
        Returns:
            List of SymbolRecord objects.
        """
        if self._cached_symbols is not None:
            return self._cached_symbols

        rm = self.get_repo_map()
        symbols: List[SymbolRecord] = []

        if rm is None:
            return []

        try:
            files = rm.scan_workspace_files()
            for fpath in files:
                try:
                    rel_p = rm._resolve_relative_path(fpath)
                    raw_symbols = rm.extract_symbols(fpath)
                    for sym in raw_symbols:
                        name = sym.get("name", "")
                        sym_type = sym.get("type", "symbol")
                        lineno = sym.get("lineno", sym.get("line_number", 1))
                        end_lineno = sym.get("end_lineno", lineno)
                        signature = sym.get("signature", name)
                        docstring = sym.get("docstring")

                        symbols.append(SymbolRecord(
                            name=name,
                            type=sym_type,
                            file_path=fpath,
                            rel_path=rel_p,
                            line_number=lineno,
                            end_lineno=end_lineno,
                            signature=signature,
                            docstring=docstring,
                        ))
                except Exception:
                    continue
        except Exception:
            return []

        self._cached_symbols = symbols
        return symbols

    # =========================================================================
    # Similarity Scans
    # =========================================================================

    def scan_git_history(
        self,
        query: str,
        repo_path: Optional[str] = None,
        git_depth: int = 50,
    ) -> List[Tuple[float, CommitRecord]]:
        """
        Scans git commit history for matching commits based on query.
        
        Returns:
            Sorted list of (similarity_score, CommitRecord) tuples in descending score order.
        """
        commits = self.get_git_commits(depth=git_depth)
        if not commits or not query.strip():
            return []

        doc_tokens_list = []
        corpus_df: Dict[str, int] = defaultdict(int)

        for c in commits:
            doc_text = f"{c.subject} {c.body} {' '.join(c.files)} {' '.join(c.issue_refs)}"
            toks = SimilarityScorer.tokenize(doc_text, stem=True)
            doc_tokens_list.append(toks)
            for t in set(toks):
                corpus_df[t] += 1

        total_docs = len(commits)
        avg_len = sum(len(t) for t in doc_tokens_list) / (total_docs or 1)

        results: List[Tuple[float, CommitRecord]] = []
        for i, c in enumerate(commits):
            doc_text = f"{c.subject} {c.body} {' '.join(c.files)} {' '.join(c.issue_refs)}"
            sim = SimilarityScorer.composite_similarity(
                query=query,
                target_text=doc_text,
                corpus_doc_freq=corpus_df,
                total_docs=total_docs,
                avg_doc_len=avg_len,
            )

            # Direct subject match boost
            subj_sim = SimilarityScorer.string_similarity(query, c.subject)
            q_tokens = set(SimilarityScorer.tokenize(query, stem=True))
            s_tokens = set(SimilarityScorer.tokenize(c.subject, stem=True))
            if q_tokens and s_tokens and len(q_tokens & s_tokens) / len(q_tokens) >= 0.7:
                sim = max(sim, 0.88)
            elif subj_sim > 0.6:
                sim = max(sim, subj_sim)

            if sim > 0.15:
                results.append((sim, c))

        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def scan_ast_symbols(
        self,
        query: str,
        repo_path: Optional[str] = None,
    ) -> List[Tuple[float, SymbolRecord]]:
        """
        Scans codebase AST symbols (classes, functions, methods, structs) for matches.
        
        Returns:
            Sorted list of (similarity_score, SymbolRecord) tuples in descending score order.
        """
        symbols = self.get_ast_symbols()
        if not symbols or not query.strip():
            return []

        doc_tokens_list = []
        corpus_df: Dict[str, int] = defaultdict(int)

        for sym in symbols:
            doc_text = f"{sym.name} {sym.type} {sym.signature} {sym.docstring or ''} {os.path.basename(sym.rel_path)}"
            toks = SimilarityScorer.tokenize(doc_text, stem=True)
            doc_tokens_list.append(toks)
            for t in set(toks):
                corpus_df[t] += 1

        total_docs = len(symbols)
        avg_len = sum(len(t) for t in doc_tokens_list) / (total_docs or 1)

        results: List[Tuple[float, SymbolRecord]] = []
        for i, sym in enumerate(symbols):
            doc_text = f"{sym.name} {sym.type} {sym.signature} {sym.docstring or ''} {os.path.basename(sym.rel_path)}"
            sim = SimilarityScorer.composite_similarity(
                query=query,
                target_text=doc_text,
                corpus_doc_freq=corpus_df,
                total_docs=total_docs,
                avg_doc_len=avg_len,
            )

            # Symbol name containment boost:
            name_tokens = set(SimilarityScorer.tokenize(sym.name, stem=True))
            query_tokens = set(SimilarityScorer.tokenize(query, stem=True))
            if query_tokens and name_tokens:
                name_overlap = sum(1 for n in name_tokens if any(SimilarityScorer._match_tokens(n, q) for q in query_tokens)) / len(name_tokens)
                if name_overlap >= 0.8:
                    sim = max(sim, 0.90)
                elif name_overlap >= 0.5:
                    sim = max(sim, 0.75)

            name_sim = SimilarityScorer.string_similarity(query, sym.name)
            if name_sim > 0.7:
                sim = max(sim, name_sim)

            if sim > 0.15:
                results.append((sim, sym))

        results.sort(key=lambda x: x[0], reverse=True)
        return results

    # =========================================================================
    # Primary Deduplication Interface
    # =========================================================================

    def scan_for_duplicate(
        self,
        query: str,
        repo_path: str = ".",
        git_depth: int = 50,
    ) -> Optional[DedupMatch]:
        """
        Scans repository commits and codebase AST symbol tables for duplicates.
        
        Args:
            query: User request, feature description, or code prompt.
            repo_path: Repository workspace path.
            git_depth: Commit depth to inspect.
            
        Returns:
            DedupMatch object with duplicate status, confidence score, and explanation.
        """
        clean_query = query.strip()
        if not clean_query:
            return DedupMatch(
                is_duplicate=False,
                confidence=0.0,
                explanation="Empty query provided.",
                match_type="none",
            )

        # 1. Scan Git commits
        commit_matches = self.scan_git_history(query=clean_query, repo_path=repo_path, git_depth=git_depth)
        top_commit: Optional[Tuple[float, CommitRecord]] = commit_matches[0] if commit_matches else None

        # 2. Scan AST symbols
        symbol_matches = self.scan_ast_symbols(query=clean_query, repo_path=repo_path)
        top_symbol: Optional[Tuple[float, SymbolRecord]] = symbol_matches[0] if symbol_matches else None

        commit_score = top_commit[0] if top_commit else 0.0
        symbol_score = top_symbol[0] if top_symbol else 0.0

        if symbol_score >= commit_score and top_symbol is not None:
            score, sym = top_symbol
            is_dup = score >= self.duplicate_threshold
            expl = (
                f"Matched existing {sym.type} `{sym.name}` in `{sym.rel_path}` (lines {sym.line_number}-{sym.end_lineno}) "
                f"with {score:.1%} confidence."
            )
            return DedupMatch(
                is_duplicate=is_dup,
                confidence=score,
                existing_commit=None,
                file_path=sym.file_path,
                line_range=(sym.line_number, sym.end_lineno),
                explanation=expl,
                match_type="symbol",
                metadata={
                    "symbol_name": sym.name,
                    "symbol_type": sym.type,
                    "signature": sym.signature,
                    "rel_path": sym.rel_path,
                },
            )

        elif top_commit is not None:
            score, c = top_commit
            is_dup = score >= self.duplicate_threshold
            first_file = c.files[0] if c.files else None
            issue_str = f" referencing {', '.join(c.issue_refs)}" if c.issue_refs else ""
            expl = (
                f"Matched existing commit {c.short_hash} ('{c.subject}'){issue_str} "
                f"with {score:.1%} confidence."
            )
            return DedupMatch(
                is_duplicate=is_dup,
                confidence=score,
                existing_commit=c.commit_hash,
                file_path=str(self.repo_path / first_file) if first_file else None,
                line_range=None,
                explanation=expl,
                match_type="commit",
                metadata={
                    "commit_hash": c.commit_hash,
                    "short_hash": c.short_hash,
                    "subject": c.subject,
                    "author": c.author,
                    "date": c.date,
                    "files": c.files,
                    "issue_refs": c.issue_refs,
                },
            )

        return DedupMatch(
            is_duplicate=False,
            confidence=0.0,
            explanation="No matching existing commits or AST symbols found in repository.",
            match_type="none",
        )

    # =========================================================================
    # Additional Duplicate Helpers
    # =========================================================================

    def find_duplicate_symbols(
        self,
        symbol_name: str,
        repo_path: str = ".",
    ) -> List[Dict[str, Any]]:
        """
        Finds existing AST symbols with identical or highly similar names.
        
        Args:
            symbol_name: Target symbol identifier name.
            repo_path: Workspace directory.
            
        Returns:
            List of matching symbol detail dictionaries.
        """
        matches = self.scan_ast_symbols(query=symbol_name, repo_path=repo_path)
        output: List[Dict[str, Any]] = []

        for score, sym in matches:
            if score >= 0.5:
                output.append({
                    "name": sym.name,
                    "type": sym.type,
                    "file_path": sym.file_path,
                    "rel_path": sym.rel_path,
                    "line_number": sym.line_number,
                    "end_lineno": sym.end_lineno,
                    "signature": sym.signature,
                    "confidence": round(score, 4),
                })
        return output

    def find_duplicate_code_snippets(
        self,
        code_snippet: str,
        repo_path: str = ".",
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Finds source files in repository containing duplicate or near-identical code blocks.
        
        Args:
            code_snippet: Target code snippet to search for.
            repo_path: Repository path.
            threshold: Minimum token similarity threshold.
            
        Returns:
            List of match dictionaries with file path and similarity score.
        """
        clean_snippet = code_snippet.strip()
        if not clean_snippet:
            return []

        rm = self.get_repo_map()
        if rm is None:
            return []

        snippet_tokens = SimilarityScorer.tokenize(clean_snippet)
        if not snippet_tokens:
            return []

        dedented_snippet = textwrap.dedent(clean_snippet)
        matches: List[Dict[str, Any]] = []
        files = rm.scan_workspace_files()

        for fpath in files:
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                file_tokens = SimilarityScorer.tokenize(content)
                if not file_tokens:
                    continue

                overlap = SimilarityScorer.token_overlap(snippet_tokens, file_tokens)
                jaccard = SimilarityScorer.jaccard_similarity(snippet_tokens, file_tokens)
                score = 0.6 * overlap + 0.4 * jaccard

                is_exact = (
                    clean_snippet in content
                    or dedented_snippet in textwrap.dedent(content)
                    or overlap == 1.0
                )

                if score >= threshold or is_exact:
                    confidence = 1.0 if is_exact else score
                    matches.append({
                        "file_path": fpath,
                        "rel_path": rm._resolve_relative_path(fpath),
                        "confidence": round(confidence, 4),
                        "exact_match": is_exact,
                    })
            except Exception:
                continue

        matches.sort(key=lambda x: x["confidence"], reverse=True)
        return matches

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Utility shortcut for calculating composite similarity between two text strings."""
        return SimilarityScorer.composite_similarity(text1, text2)
