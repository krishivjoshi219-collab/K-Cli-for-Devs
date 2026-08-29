"""
test_repo_map.py - Comprehensive Unit & Integration Tests for AST Codebase Repository Map.

Tests symbol extraction, hierarchy rendering, token budget enforcement, focus file
prioritization, cross-file reference ranking, ignore pattern filtering, cache efficiency,
and error resilience under adversarial conditions.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from k_cli.git.repo_map import RepoMap


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def temp_repo_workspace(tmp_path: Path) -> Path:
    """Creates a realistic multi-module workspace with diverse Python constructs."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    # 1. core/models.py
    core_dir = ws / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "__init__.py").write_text('"""Core package."""\n', encoding="utf-8")
    (core_dir / "models.py").write_text(
        '"""Data models for system."""\n\n'
        'class BaseEntity:\n'
        '    """Abstract base entity."""\n'
        '    def __init__(self, entity_id: str):\n'
        '        self.entity_id = entity_id\n\n'
        '    def get_id(self) -> str:\n'
        '        return self.entity_id\n\n'
        'class User(BaseEntity):\n'
        '    """User domain model."""\n'
        '    def __init__(self, user_id: str, username: str, email: str = "user@example.com"):\n'
        '        super().__init__(user_id)\n'
        '        self.username = username\n'
        '        self.email = email\n\n'
        '    @property\n'
        '    def display_name(self) -> str:\n'
        '        return f"{self.username} <{self.email}>"\n\n'
        '    async def save_async(self, db: Any) -> bool:\n'
        '        return True\n',
        encoding="utf-8",
    )

    # 2. core/utils.py
    (core_dir / "utils.py").write_text(
        'import math\n\n'
        'def sanitize_input(text: str, max_length: int = 100) -> str:\n'
        '    """Sanitizes user input string."""\n'
        '    return text.strip()[:max_length]\n\n'
        'async def compute_hash(data: bytes, salt: str = "default") -> str:\n'
        '    """Asynchronously hashes bytes data."""\n'
        '    return "hash_value"\n',
        encoding="utf-8",
    )

    # 3. service.py
    (ws / "service.py").write_text(
        'from core.models import User\n'
        'from core.utils import sanitize_input\n\n'
        'class UserService:\n'
        '    """Service layer for user operations."""\n'
        '    def __init__(self):\n'
        '        self.users = {}\n\n'
        '    def create_user(self, username: str, email: str) -> User:\n'
        '        clean_name = sanitize_input(username)\n'
        '        user = User(user_id="u-1", username=clean_name, email=email)\n'
        '        self.users[user.entity_id] = user\n'
        '        return user\n\n'
        '    def find_user(self, user_id: str) -> User | None:\n'
        '        return self.users.get(user_id)\n',
        encoding="utf-8",
    )

    # 4. main.py
    (ws / "main.py").write_text(
        'from service import UserService\n\n'
        'def main() -> int:\n'
        '    svc = UserService()\n'
        '    user = svc.create_user("alice", "alice@example.com")\n'
        '    print(user.display_name)\n'
        '    return 0\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n',
        encoding="utf-8",
    )

    return ws


# ==============================================================================
# Unit Tests: Symbol Extraction
# ==============================================================================

class TestSymbolExtraction:
    """Tests for RepoMap.extract_symbols."""

    def test_extract_classes_and_methods(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        models_file = str(temp_repo_workspace / "core" / "models.py")
        symbols = repo_map.extract_symbols(models_file)

        assert isinstance(symbols, list)
        names = [s["name"] for s in symbols]
        assert "BaseEntity" in names
        assert "User" in names
        assert "__init__" in names
        assert "get_id" in names
        assert "display_name" in names
        assert "save_async" in names

        # Validate class symbol structure
        user_sym = next(s for s in symbols if s["name"] == "User" and s["type"] == "class")
        assert user_sym["bases"] == ["BaseEntity"]
        assert "User domain model." in (user_sym["docstring"] or "")
        assert user_sym["lineno"] > 0
        assert len(user_sym["methods"]) >= 3

        # Validate async method
        async_method = next(s for s in symbols if s["name"] == "save_async")
        assert async_method["type"] == "async_method"
        assert async_method["is_async"] is True
        assert async_method["parent"] == "User"

    def test_extract_top_level_functions_and_async(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        utils_file = str(temp_repo_workspace / "core" / "utils.py")
        symbols = repo_map.extract_symbols(utils_file)

        names = [s["name"] for s in symbols]
        assert "sanitize_input" in names
        assert "compute_hash" in names

        sync_fn = next(s for s in symbols if s["name"] == "sanitize_input")
        assert sync_fn["type"] == "function"
        assert sync_fn["is_async"] is False
        assert "text" in sync_fn["args"]
        assert "max_length" in sync_fn["args"]
        assert sync_fn["return_type"] == "str"
        assert "def sanitize_input" in sync_fn["signature"]

        async_fn = next(s for s in symbols if s["name"] == "compute_hash")
        assert async_fn["type"] == "async_function"
        assert async_fn["is_async"] is True
        assert "async def compute_hash" in async_fn["signature"]

    def test_extract_symbols_relative_path(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        symbols = repo_map.extract_symbols("service.py")
        names = [s["name"] for s in symbols]
        assert "UserService" in names
        assert "create_user" in names

    def test_extract_symbols_empty_file(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("", encoding="utf-8")
        symbols = repo_map.extract_symbols(str(empty_file))
        assert symbols == []

    def test_extract_symbols_missing_file(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(tmp_path / "non_existent.py"))
        assert symbols == []

    def test_extract_symbols_syntax_error_resilience(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        corrupt_file = tmp_path / "corrupt.py"
        corrupt_file.write_text("class Broken(\n    def ???\n", encoding="utf-8")
        symbols = repo_map.extract_symbols(str(corrupt_file))
        assert symbols == []

    def test_extract_symbols_binary_file_resilience(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        bin_file = tmp_path / "data.bin.py"
        bin_file.write_bytes(b"\x00\x01\x02\xfe\xff")
        symbols = repo_map.extract_symbols(str(bin_file))
        assert symbols == []

    def test_extract_symbols_utf8_bom_encoding(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        bom_file = tmp_path / "bom.py"
        bom_file.write_text("\ufeffdef bom_func(): pass\n", encoding="utf-8-sig")
        symbols = repo_map.extract_symbols(str(bom_file))
        names = [s["name"] for s in symbols]
        assert "bom_func" in names

    def test_cache_invalidation_on_file_edit(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        target_file = tmp_path / "module.py"
        target_file.write_text("def initial_version(): pass\n", encoding="utf-8")

        symbols_v1 = repo_map.extract_symbols(str(target_file))
        assert [s["name"] for s in symbols_v1] == ["initial_version"]

        # Modify file and change mtime
        time.sleep(0.01)
        target_file.write_text("def updated_version(): pass\n", encoding="utf-8")

        symbols_v2 = repo_map.extract_symbols(str(target_file))
        assert [s["name"] for s in symbols_v2] == ["updated_version"]


# ==============================================================================
# Unit Tests: Workspace Scanning & Filtering
# ==============================================================================

class TestWorkspaceScanning:
    """Tests for workspace file scanning and ignore rules."""

    def test_scan_finds_all_valid_py_files(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        files = repo_map.scan_workspace_files()
        rel_files = [os.path.relpath(f, str(temp_repo_workspace)).replace("\\", "/") for f in files]

        assert "core/__init__.py" in rel_files
        assert "core/models.py" in rel_files
        assert "core/utils.py" in rel_files
        assert "service.py" in rel_files
        assert "main.py" in rel_files

    def test_skips_hidden_dirs_and_files(self, tmp_path: Path):
        ws = tmp_path / "hidden_ws"
        ws.mkdir()
        (ws / "valid.py").write_text("def valid(): pass\n", encoding="utf-8")
        (ws / ".hidden.py").write_text("def hidden(): pass\n", encoding="utf-8")

        secret_dir = ws / ".secret"
        secret_dir.mkdir()
        (secret_dir / "secret.py").write_text("def secret(): pass\n", encoding="utf-8")

        git_dir = ws / ".git"
        git_dir.mkdir()
        (git_dir / "hook.py").write_text("def hook(): pass\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        files = repo_map.scan_workspace_files()
        basenames = [os.path.basename(f) for f in files]

        assert "valid.py" in basenames
        assert ".hidden.py" not in basenames
        assert "secret.py" not in basenames
        assert "hook.py" not in basenames

    def test_skips_virtualenv_directories(self, tmp_path: Path):
        ws = tmp_path / "venv_ws"
        ws.mkdir()
        (ws / "app.py").write_text("def app(): pass\n", encoding="utf-8")

        # Fake venv dir with pyvenv.cfg
        venv_dir = ws / "my_custom_env"
        venv_dir.mkdir()
        (venv_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (venv_dir / "lib.py").write_text("def lib(): pass\n", encoding="utf-8")

        # Standard venv names
        std_venv = ws / ".venv"
        std_venv.mkdir()
        (std_venv / "internal.py").write_text("def internal(): pass\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        files = repo_map.scan_workspace_files()
        basenames = [os.path.basename(f) for f in files]

        assert "app.py" in basenames
        assert "lib.py" not in basenames
        assert "internal.py" not in basenames

    def test_skips_non_py_files(self, tmp_path: Path):
        ws = tmp_path / "non_py_ws"
        ws.mkdir()
        (ws / "code.py").write_text("def code(): pass\n", encoding="utf-8")
        (ws / "config.json").write_text("{}", encoding="utf-8")
        (ws / "notes.txt").write_text("hello", encoding="utf-8")
        (ws / "data.bin").write_bytes(b"\x00\x01\x02")

        repo_map = RepoMap(root_dir=str(ws))
        files = repo_map.scan_workspace_files()
        assert len(files) == 1
        assert os.path.basename(files[0]) == "code.py"


# ==============================================================================
# Unit Tests: Tree Generation & Token Budgeting
# ==============================================================================

class TestRepoMapTreeGeneration:
    """Tests for RepoMap.get_repo_map output format, ranking, and budget enforcement."""

    def test_get_repo_map_contains_hierarchy(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        tree = repo_map.get_repo_map(max_tokens=400)

        assert isinstance(tree, str)
        assert "core/models.py:" in tree or "models.py:" in tree
        assert "class User" in tree
        assert "class BaseEntity" in tree
        assert "class UserService" in tree
        assert "def sanitize_input" in tree

    def test_token_budget_strict_enforcement(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))

        for max_tok in [10, 25, 50, 100, 200, 400]:
            tree = repo_map.get_repo_map(max_tokens=max_tok)
            word_count = len(tree.split())
            assert word_count <= max_tok, f"Tree exceeded budget {max_tok}: got {word_count} words"

    def test_zero_or_negative_token_budget(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        assert repo_map.get_repo_map(max_tokens=0) == ""
        assert repo_map.get_repo_map(max_tokens=-5) == ""

    def test_focus_files_prioritization(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        # With tight budget, focus file must take priority over others
        tree = repo_map.get_repo_map(max_tokens=25, focus_files=["service.py"])
        assert "service.py:" in tree
        assert "UserService" in tree

    def test_multiple_focus_files(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        tree = repo_map.get_repo_map(max_tokens=60, focus_files=["models.py", "utils.py"])
        assert "models.py:" in tree or "utils.py:" in tree

    def test_cross_file_reference_ranking(self, temp_repo_workspace: Path):
        """Files referenced by other files (models.py, utils.py) should be ranked highly."""
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert "models.py" in tree
        assert "User" in tree

    def test_huge_workspace_pruning(self, tmp_path: Path):
        """Generates a workspace with 150 functions across 5 modules and checks strict pruning."""
        ws = tmp_path / "huge_workspace"
        ws.mkdir()

        for mod_idx in range(5):
            funcs = [
                f"def module_{mod_idx}_func_{fn_idx}(arg: int) -> int:\n    return arg * {fn_idx}\n"
                for fn_idx in range(30)
            ]
            (ws / f"mod_{mod_idx}.py").write_text("\n".join(funcs), encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        tree = repo_map.get_repo_map(max_tokens=400)

        assert isinstance(tree, str)
        assert len(tree.split()) <= 400
        assert len(tree.split()) > 0


# ==============================================================================
# Unit Tests: Performance Benchmarks & Edge Cases
# ==============================================================================

class TestPerformanceAndRobustness:
    """Latency benchmarks and boundary conditions."""

    def test_latency_under_250ms_on_multi_module_workspace(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))

        # Warm-up pass
        repo_map.get_repo_map(max_tokens=400)

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            tree = repo_map.get_repo_map(max_tokens=400)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)
            assert len(tree) > 0

        mean_latency = sum(latencies) / len(latencies)
        assert mean_latency < 250.0, f"Mean latency exceeded 250ms: {mean_latency:.3f} ms"
        # Cached latency should be sub-millisecond
        assert latencies[-1] < 10.0, f"Cached query exceeded 10ms: {latencies[-1]:.3f} ms"

    def test_empty_workspace_returns_empty_string(self, tmp_path: Path):
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        repo_map = RepoMap(root_dir=str(empty_dir))
        assert repo_map.get_repo_map(max_tokens=400) == ""

    def test_non_existent_workspace_dir(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path / "does_not_exist"))
        assert repo_map.scan_workspace_files() == []
        assert repo_map.get_repo_map(max_tokens=400) == ""

    def test_workspace_with_only_corrupt_files(self, tmp_path: Path):
        ws = tmp_path / "broken_ws"
        ws.mkdir()
        (ws / "bad1.py").write_text("def broken(\n", encoding="utf-8")
        (ws / "bad2.py").write_text("class ((\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert tree == ""


# ==============================================================================
# Unit Tests: Multi-Language Symbol Extraction (TS/JS, Rust, Go, C++)
# ==============================================================================

class TestMultiLanguageSymbolExtraction:
    """Tests for symbol extraction across JS/TS, Rust, Go, and C++."""

    def test_typescript_symbol_extraction(self, tmp_path: Path):
        ts_file = tmp_path / "service.ts"
        ts_file.write_text(
            'import { BaseEntity } from "./models";\n'
            'import * as http from "http";\n\n'
            'export interface UserConfig {\n'
            '    timeout: number;\n'
            '}\n\n'
            'export enum Role {\n'
            '    Admin = "ADMIN",\n'
            '    User = "USER",\n'
            '}\n\n'
            'export type UserID = string | number;\n\n'
            'export class AuthService extends BaseEntity {\n'
            '    private token: string;\n'
            '    constructor(token: string) {\n'
            '        super();\n'
            '        this.token = token;\n'
            '    }\n'
            '    public async authenticate(username: string): Promise<boolean> {\n'
            '        return true;\n'
            '    }\n'
            '}\n\n'
            'export async function validateToken(t: string): Promise<boolean> {\n'
            '    return true;\n'
            '}\n\n'
            'export const hashPassword = async (p: string): Promise<string> => {\n'
            '    return "hashed";\n'
            '};\n',
            encoding="utf-8",
        )

        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(ts_file))
        names = [s["name"] for s in symbols]

        assert "UserConfig" in names
        assert "Role" in names
        assert "UserID" in names
        assert "AuthService" in names
        assert "authenticate" in names
        assert "validateToken" in names
        assert "hashPassword" in names

        # Check interface symbol
        iface_sym = next(s for s in symbols if s["name"] == "UserConfig")
        assert iface_sym["type"] == "interface"

        # Check enum symbol
        enum_sym = next(s for s in symbols if s["name"] == "Role")
        assert enum_sym["type"] == "enum"

        # Check class symbol
        cls_sym = next(s for s in symbols if s["name"] == "AuthService")
        assert cls_sym["type"] == "class"
        assert "BaseEntity" in cls_sym["bases"]

        # Check async method
        auth_meth = next(s for s in symbols if s["name"] == "authenticate")
        assert auth_meth["is_async"] is True
        assert auth_meth["parent"] == "AuthService"

        # Check async top-level function
        val_fn = next(s for s in symbols if s["name"] == "validateToken")
        assert val_fn["type"] == "async_function"
        assert val_fn["is_async"] is True

    def test_rust_symbol_extraction(self, tmp_path: Path):
        rs_file = tmp_path / "engine.rs"
        rs_file.write_text(
            'use std::collections::HashMap;\n'
            'use crate::core::models::Entity;\n\n'
            'pub struct EngineConfig {\n'
            '    pub workers: usize,\n'
            '}\n\n'
            'pub enum State {\n'
            '    Idle,\n'
            '    Running,\n'
            '}\n\n'
            'pub trait Runnable {\n'
            '    fn run(&self);\n'
            '}\n\n'
            'pub struct Engine {\n'
            '    config: EngineConfig,\n'
            '}\n\n'
            'impl Engine {\n'
            '    pub fn new(config: EngineConfig) -> Self {\n'
            '        Self { config }\n'
            '    }\n'
            '    pub async fn execute_task(&self, task_id: &str) -> Result<(), String> {\n'
            '        Ok(())\n'
            '    }\n'
            '}\n\n'
            'pub async fn bootstrap_engine() -> Result<Engine, String> {\n'
            '    Ok(Engine::new(EngineConfig { workers: 4 }))\n'
            '}\n',
            encoding="utf-8",
        )

        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(rs_file))
        names = [s["name"] for s in symbols]

        assert "EngineConfig" in names
        assert "State" in names
        assert "Runnable" in names
        assert "Engine" in names
        assert "new" in names
        assert "execute_task" in names
        assert "bootstrap_engine" in names

        # Struct symbol
        cfg_sym = next(s for s in symbols if s["name"] == "EngineConfig")
        assert cfg_sym["type"] == "struct"

        # Trait symbol
        trait_sym = next(s for s in symbols if s["name"] == "Runnable")
        assert trait_sym["type"] == "trait"

        # Attached method inside impl
        exec_sym = next(s for s in symbols if s["name"] == "execute_task")
        assert exec_sym["parent"] == "Engine"
        assert exec_sym["is_async"] is True

    def test_go_symbol_extraction(self, tmp_path: Path):
        go_file = tmp_path / "server.go"
        go_file.write_text(
            'package server\n\n'
            'import (\n'
            '    "fmt"\n'
            '    "net/http"\n'
            ')\n\n'
            'type ServerConfig struct {\n'
            '    Port int\n'
            '}\n\n'
            'type Handler interface {\n'
            '    Handle(req *http.Request) error\n'
            '}\n\n'
            'type APIServer struct {\n'
            '    config ServerConfig\n'
            '}\n\n'
            'func (s *APIServer) Start() error {\n'
            '    return nil\n'
            '}\n\n'
            'func (s *APIServer) Stop() error {\n'
            '    return nil\n'
            '}\n\n'
            'func NewServer(cfg ServerConfig) *APIServer {\n'
            '    return &APIServer{config: cfg}\n'
            '}\n',
            encoding="utf-8",
        )

        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(go_file))
        names = [s["name"] for s in symbols]

        assert "ServerConfig" in names
        assert "Handler" in names
        assert "APIServer" in names
        assert "Start" in names
        assert "Stop" in names
        assert "NewServer" in names

        # Struct & Interface
        struct_sym = next(s for s in symbols if s["name"] == "APIServer")
        assert struct_sym["type"] == "struct"
        assert len(struct_sym["methods"]) == 2

        iface_sym = next(s for s in symbols if s["name"] == "Handler")
        assert iface_sym["type"] == "interface"

        # Method with receiver
        start_sym = next(s for s in symbols if s["name"] == "Start")
        assert start_sym["type"] == "method"
        assert start_sym["parent"] == "APIServer"

    def test_cpp_symbol_extraction(self, tmp_path: Path):
        cpp_file = tmp_path / "pipeline.cpp"
        cpp_file.write_text(
            '#include "models.hpp"\n'
            '#include <vector>\n\n'
            'enum class Status {\n'
            '    Active,\n'
            '    Inactive\n'
            '};\n\n'
            'class Pipeline : public BasePipeline {\n'
            'public:\n'
            '    void initialize(int threads);\n'
            '    int run_step(double delta);\n'
            '};\n\n'
            'int compute_stats(const std::vector<int>& data);\n',
            encoding="utf-8",
        )

        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(cpp_file))
        names = [s["name"] for s in symbols]

        assert "Status" in names
        assert "Pipeline" in names
        assert "initialize" in names
        assert "run_step" in names
        assert "compute_stats" in names

        cls_sym = next(s for s in symbols if s["name"] == "Pipeline")
        assert cls_sym["type"] == "class"
        assert "BasePipeline" in cls_sym["bases"]


# ==============================================================================
# Unit Tests: Dependency Graph, Caller-Callee, and Cyclic Import Detection
# ==============================================================================

class TestDependencyGraphAndCyclicImports:
    """Tests for forward/reverse dependency graph, caller-callee, and cycle detection."""

    def test_forward_and_reverse_dependency_graph(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        fwd_graph = repo_map.get_dependency_graph()
        rev_graph = repo_map.get_reverse_dependency_graph()

        # service.py imports core/models.py and core/utils.py
        assert "service.py" in fwd_graph
        deps_of_service = fwd_graph["service.py"]
        assert any("models.py" in d for d in deps_of_service)
        assert any("utils.py" in d for d in deps_of_service)

        # main.py imports service.py
        assert "main.py" in fwd_graph
        deps_of_main = fwd_graph["main.py"]
        assert any("service.py" in d for d in deps_of_main)

        # Reverse graph: service.py is depended on by main.py
        assert "service.py" in rev_graph
        assert any("main.py" in r for r in rev_graph["service.py"])

    def test_caller_callee_mapping(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        cc_map = repo_map.get_caller_callee_map()

        assert isinstance(cc_map, dict)
        # UserService.create_user calls sanitize_input and User
        assert "UserService.create_user" in cc_map
        callees = cc_map["UserService.create_user"]
        assert "sanitize_input" in callees
        assert "User" in callees

        # main calls UserService and create_user
        assert "main" in cc_map
        main_callees = cc_map["main"]
        assert "UserService" in main_callees or "create_user" in main_callees

    def test_detect_cyclic_imports(self, tmp_path: Path):
        ws = tmp_path / "cyclic_ws"
        ws.mkdir()

        # Circular loop: mod_a -> mod_b -> mod_c -> mod_a
        (ws / "mod_a.py").write_text("import mod_b\ndef fn_a(): pass\n", encoding="utf-8")
        (ws / "mod_b.py").write_text("import mod_c\ndef fn_b(): pass\n", encoding="utf-8")
        (ws / "mod_c.py").write_text("import mod_a\ndef fn_c(): pass\n", encoding="utf-8")

        # Independent module: mod_d (no cycle)
        (ws / "mod_d.py").write_text("import mod_a\ndef fn_d(): pass\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        cycles = repo_map.detect_cyclic_imports()

        assert len(cycles) >= 1
        cycle = cycles[0]
        # Cycle contains mod_a.py, mod_b.py, mod_c.py
        cycle_basenames = [os.path.basename(f) for f in cycle]
        assert "mod_a.py" in cycle_basenames
        assert "mod_b.py" in cycle_basenames
        assert "mod_c.py" in cycle_basenames

    def test_acyclic_workspace_returns_empty_cycles(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        cycles = repo_map.detect_cyclic_imports()
        assert cycles == []

    def test_get_symbol_references(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        refs = repo_map.get_symbol_references("User")
        # User is referenced in models.py, service.py, main.py
        assert any("service.py" in r for r in refs)


# ==============================================================================
# Unit Tests: Compact Topological Summary
# ==============================================================================

class TestTopologicalSummary:
    """Tests for RepoMap.get_topological_summary."""

    def test_topological_summary_layers(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        summary = repo_map.get_topological_summary(max_tokens=400)

        assert "[Topological Architecture Map]" in summary
        assert "core/models.py" in summary or "models.py" in summary
        assert "service.py" in summary
        assert "main.py" in summary

    def test_topological_summary_token_budget(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))

        for budget in [15, 30, 60, 150, 400]:
            summary = repo_map.get_topological_summary(max_tokens=budget)
            word_count = len(summary.split())
            assert word_count <= budget, f"Topological summary exceeded budget {budget}: got {word_count}"

    def test_topological_summary_focus_files(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))
        summary = repo_map.get_topological_summary(max_tokens=50, focus_files=["service.py"])
        assert "service.py" in summary


# ==============================================================================
# Unit Tests: Incremental Hashing Cache Efficiency
# ==============================================================================

class TestIncrementalHashingCache:
    """Tests for mtime + hash cache performance and invalidation."""

    def test_cache_hit_without_reparse(self, temp_repo_workspace: Path):
        repo_map = RepoMap(root_dir=str(temp_repo_workspace))

        # Initial parse -> cache miss
        models_file = str(temp_repo_workspace / "core" / "models.py")
        s1 = repo_map.extract_symbols(models_file)
        stats1 = repo_map.get_cache_stats()
        assert stats1["misses"] >= 1

        # Second query -> instant stat hit
        s2 = repo_map.extract_symbols(models_file)
        assert s1 == s2
        stats2 = repo_map.get_cache_stats()
        assert stats2["hits"] >= 1

    def test_hash_cache_hit_on_mtime_touch_same_content(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        f = tmp_path / "calc.py"
        f.write_text("def calculate(x: int) -> int:\n    return x * 2\n", encoding="utf-8")

        s1 = repo_map.extract_symbols(str(f))
        assert len(s1) == 1
        stats1 = repo_map.get_cache_stats()
        misses_before = stats1["misses"]
        hits_before = stats1["hits"]

        # Modify mtime without changing content
        time.sleep(0.01)
        f.write_text("def calculate(x: int) -> int:\n    return x * 2\n", encoding="utf-8")

        s2 = repo_map.extract_symbols(str(f))
        assert s1 == s2
        stats2 = repo_map.get_cache_stats()
        # Hash match treated as hit!
        assert stats2["hits"] > hits_before
        assert stats2["misses"] == misses_before

    def test_cache_invalidation_and_clear(self, tmp_path: Path):
        repo_map = RepoMap(root_dir=str(tmp_path))
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("def a(): pass\n", encoding="utf-8")
        f2.write_text("def b(): pass\n", encoding="utf-8")

        repo_map.extract_symbols(str(f1))
        repo_map.extract_symbols(str(f2))
        assert repo_map.get_cache_stats()["cached_files"] == 2

        # Invalidate single file
        repo_map.invalidate_cache(str(f1))
        assert repo_map.get_cache_stats()["cached_files"] == 1

        # Clear entire cache
        repo_map.clear_cache()
        assert repo_map.get_cache_stats()["cached_files"] == 0
