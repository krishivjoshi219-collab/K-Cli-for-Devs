"""
test_patcher.py - Unit and Integration Tests for Surgical Patch Engine (Patcher)
"""

import ast
from pathlib import Path
import pytest

from k_cli.git.patcher import Patcher


class TestSearchReplaceParsing:
    """Tests for SEARCH/REPLACE block parsing."""

    def test_parse_single_block(self):
        patch = (
            "<<<<<<< SEARCH\n"
            "def old_fn():\n"
            "    return 1\n"
            "=======\n"
            "def new_fn():\n"
            "    return 2\n"
            ">>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 1
        assert "def old_fn():" in blocks[0][0]
        assert "def new_fn():" in blocks[0][1]

    def test_parse_multiple_blocks(self):
        patch = (
            "Leading text\n"
            "<<<<<<< SEARCH\n"
            "a = 1\n"
            "=======\n"
            "a = 10\n"
            ">>>>>>>\n"
            "Middle notes\n"
            "<<<<<<< SEARCH\n"
            "b = 2\n"
            "=======\n"
            "b = 20\n"
            ">>>>>>>\n"
            "Trailing notes"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 2
        assert blocks[0][0].strip() == "a = 1"
        assert blocks[0][1].strip() == "a = 10"
        assert blocks[1][0].strip() == "b = 2"
        assert blocks[1][1].strip() == "b = 20"

    def test_parse_empty_string(self):
        assert Patcher.parse_search_replace_blocks("") == []
        assert Patcher.parse_search_replace_blocks("Just regular conversational text without blocks") == []

    def test_parse_malformed_missing_divider(self):
        patch = "<<<<<<< SEARCH\ndef fn(): pass\n>>>>>>>"
        assert Patcher.parse_search_replace_blocks(patch) == []

    def test_parse_malformed_missing_end_marker(self):
        patch = "<<<<<<< SEARCH\ndef fn(): pass\n=======\ndef fn(): return 1\n"
        assert Patcher.parse_search_replace_blocks(patch) == []

    def test_parse_blocks_with_trailing_spaces_on_markers(self):
        patch = (
            "<<<<<<< SEARCH   \t\n"
            "x = 1\n"
            "=======   \n"
            "x = 2\n"
            ">>>>>>>  \t"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 1
        assert blocks[0][0].strip() == "x = 1"
        assert blocks[0][1].strip() == "x = 2"


class TestApplyPatchExact:
    """Tests for exact match patch application."""

    def test_exact_match_single_line(self):
        orig = "x = 1\ny = 2\n"
        success, patched, err = Patcher.apply_patch(orig, "x = 1", "x = 10", fuzzy=False)
        assert success is True
        assert patched == "x = 10\ny = 2\n"
        assert err == ""

    def test_exact_match_multiline(self):
        orig = "def add(a, b):\n    return a - b\n"
        search = "def add(a, b):\n    return a - b"
        replace = "def add(a, b):\n    return a + b"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=False)
        assert success is True
        assert "return a + b" in patched

    def test_exact_match_replaces_first_occurrence(self):
        orig = "val = 1\nval = 1\nval = 1\n"
        success, patched, err = Patcher.apply_patch(orig, "val = 1", "val = 99", fuzzy=False)
        assert success is True
        assert patched == "val = 99\nval = 1\nval = 1\n"

    def test_exact_mode_fails_on_mismatch(self):
        orig = "def greet():\n    return 'hi'\n"
        search = "def greet():\n    return 'hello'"
        replace = "def greet():\n    return 'hey'"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=False)
        assert success is False
        assert patched == orig
        assert "not found" in err.lower()


class TestApplyPatchFuzzy:
    """Tests for fuzzy matching patch application."""

    def test_fuzzy_trailing_whitespace(self):
        orig = "def add(a, b):   \n    return a + b  \n"
        search = "def add(a, b):\n    return a + b"
        replace = "def add(a, b):\n    return a + b + 1"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "return a + b + 1" in patched

    def test_fuzzy_crlf_vs_lf(self):
        orig = "def fn():\r\n    return 42\r\n"
        search = "def fn():\n    return 42"
        replace = "def fn():\n    return 100"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "100" in patched
        assert "\r\n" in patched

    def test_fuzzy_indentation_shift_positive(self):
        orig = "    def method(self):\n        return self.val\n"
        search = "def method(self):\n    return self.val"
        replace = "def method(self):\n    return self.val * 2"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "        return self.val * 2" in patched

    def test_fuzzy_indentation_shift_negative(self):
        orig = "def method(self):\n    return self.val\n"
        search = "    def method(self):\n        return self.val"
        replace = "    def method(self):\n        return self.val * 2"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "    return self.val * 2" in patched

    def test_fuzzy_interspersed_blank_lines(self):
        orig = "def step1():\n    pass\n\n\ndef step2():\n    pass\n"
        search = "def step1():\n    pass\ndef step2():\n    pass"
        replace = "def step1():\n    pass\ndef step2():\n    return True"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "return True" in patched

    def test_fuzzy_unicode_emojis(self):
        orig = 'EMOJI = "🚀"\nSTATUS = "active"\n'
        search = 'STATUS = "active"'
        replace = 'STATUS = "completed ✅"'
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "completed ✅" in patched

    def test_fuzzy_empty_search_block_rejected(self):
        orig = "def foo(): pass\n"
        success, patched, err = Patcher.apply_patch(orig, "", "def bar(): pass", fuzzy=True)
        assert success is False
        assert "empty" in err.lower()

    def test_fuzzy_unmatched_block_returns_error(self):
        orig = "def foo():\n    return 1\n"
        search = "def nonexistent():\n    return 99"
        replace = "def replacement():\n    return 0"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is False
        assert patched == orig
        assert "not found" in err.lower()


class TestApplyFilePatches:
    """Tests for applying patches to files with AST validation."""

    def test_apply_file_patches_success(self, tmp_path: Path):
        test_file = tmp_path / "module.py"
        test_file.write_text("def run():\n    return False\n", encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "def run():\n"
            "    return False\n"
            "=======\n"
            "def run():\n"
            "    return True\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch, validate_ast=True)
        assert success is True
        assert err == ""
        assert "return True" in test_file.read_text(encoding="utf-8")

    def test_apply_file_patches_multiple_blocks(self, tmp_path: Path):
        test_file = tmp_path / "multi.py"
        test_file.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "a = 1\n"
            "=======\n"
            "a = 10\n"
            ">>>>>>>\n"
            "<<<<<<< SEARCH\n"
            "c = 3\n"
            "=======\n"
            "c = 30\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch, validate_ast=True)
        assert success is True
        content = test_file.read_text(encoding="utf-8")
        assert "a = 10" in content
        assert "b = 2" in content
        assert "c = 30" in content

    def test_apply_file_patches_missing_file_error(self, tmp_path: Path):
        missing = tmp_path / "missing.py"
        patch = "<<<<<<< SEARCH\na\n=======\nb\n>>>>>>>"
        success, err = Patcher.apply_file_patches(str(missing), patch, validate_ast=True)
        assert success is False
        assert "not found" in err.lower()

    def test_apply_file_patches_syntax_error_ast_rejection(self, tmp_path: Path):
        test_file = tmp_path / "syntax.py"
        original = "def calculate():\n    return 42\n"
        test_file.write_text(original, encoding="utf-8")

        # Invalid Python syntax replacement
        patch = (
            "<<<<<<< SEARCH\n"
            "def calculate():\n"
            "    return 42\n"
            "=======\n"
            "def calculate(\n"
            "    return 42\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        # Original file must remain untouched
        assert test_file.read_text(encoding="utf-8") == original

    def test_apply_file_patches_atomic_failure_on_second_block(self, tmp_path: Path):
        test_file = tmp_path / "atomic.py"
        original = "x = 1\ny = 2\n"
        test_file.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "x = 1\n"
            "=======\n"
            "x = 10\n"
            ">>>>>>>\n"
            "<<<<<<< SEARCH\n"
            "NONEXISTENT = 999\n"
            "=======\n"
            "y = 20\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch, validate_ast=True)
        assert success is False
        # File must not have x = 10 written
        assert test_file.read_text(encoding="utf-8") == original

    def test_apply_file_patches_non_python_file(self, tmp_path: Path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Hello World\n", encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "Hello World\n"
            "=======\n"
            "Hello Universe\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(txt_file), patch, validate_ast=True)
        assert success is True
        assert txt_file.read_text(encoding="utf-8") == "Hello Universe\n"


class TestStandardReplaceMarkerAndMultiFileParsing:
    """Tests for standard `>>>>>>> REPLACE` marker and multi-file patch parsing."""

    def test_parse_standard_replace_marker(self):
        patch = (
            "<<<<<<< SEARCH\n"
            "def foo(): return 1\n"
            "=======\n"
            "def foo(): return 2\n"
            ">>>>>>> REPLACE"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 1
        assert "def foo(): return 1" in blocks[0][0]
        assert "def foo(): return 2" in blocks[0][1]

    def test_parse_inline_filepath_in_marker(self):
        patch = (
            "<<<<<<< SEARCH: src/math_utils.py\n"
            "def add(a, b): return a - b\n"
            "=======\n"
            "def add(a, b): return a + b\n"
            ">>>>>>> REPLACE: src/math_utils.py"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 1
        assert "return a - b" in blocks[0][0]

        mf_blocks = Patcher.parse_multi_file_patches(patch)
        assert len(mf_blocks) == 1
        assert mf_blocks[0][0] == "src/math_utils.py"
        assert "return a - b" in mf_blocks[0][1]
        assert "return a + b" in mf_blocks[0][2]

    def test_parse_multi_file_markdown_headers(self):
        patch = (
            "### `calculator.py`\n"
            "<<<<<<< SEARCH\n"
            "x = 1\n"
            "=======\n"
            "x = 10\n"
            ">>>>>>> REPLACE\n\n"
            "File: formatter.py\n"
            "<<<<<<< SEARCH\n"
            "y = 2\n"
            "=======\n"
            "y = 20\n"
            ">>>>>>>"
        )
        mf_blocks = Patcher.parse_multi_file_patches(patch)
        assert len(mf_blocks) == 2
        assert mf_blocks[0][0] == "calculator.py"
        assert mf_blocks[0][1].strip() == "x = 1"
        assert mf_blocks[0][2].strip() == "x = 10"
        assert mf_blocks[1][0] == "formatter.py"
        assert mf_blocks[1][1].strip() == "y = 2"
        assert mf_blocks[1][2].strip() == "y = 20"


class TestASTAndAdvancedFuzzyMatching:
    """Tests for AST-based structural multi-line matching and advanced fuzzy tolerance."""

    def test_ast_structural_function_matching(self):
        orig = (
            "class Service:\n"
            "    def handle_request(self, req_id: int) -> bool:\n"
            "        # internal processing\n"
            "        status = True\n"
            "        return status\n"
        )
        # Search block without class wrapper and different internal whitespace
        search = (
            "def handle_request(self, req_id: int) -> bool:\n"
            "    status = True\n"
            "    return status"
        )
        replace = (
            "def handle_request(self, req_id: int) -> bool:\n"
            "    return True"
        )
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "        return True" in patched
        assert "class Service:" in patched

    def test_ast_inner_statement_matching(self):
        orig = (
            "def calculate_tax(income: float) -> float:\n"
            "    rate = 0.2\n"
            "    deduction = 1000\n"
            "    taxable = income - deduction\n"
            "    return taxable * rate\n"
        )
        search = (
            "deduction = 1000\n"
            "taxable = income - deduction\n"
            "return taxable * rate"
        )
        replace = (
            "deduction = 1500\n"
            "return max(0.0, (income - deduction) * rate)"
        )
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "deduction = 1500" in patched
        assert "rate = 0.2" in patched

    def test_whitespace_and_quote_normalization(self):
        orig = 'message = "Hello, world!"\ncount = 10\n'
        # Search with single quotes and extra space around '='
        search = "message  =  'Hello, world!'\ncount  =  10"
        replace = "message = 'Hello, Universe!'\ncount = 20"
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "Hello, Universe!" in patched
        assert "count = 20" in patched

    def test_fuzzy_similarity_fallback(self):
        orig = (
            "def authenticate(user_token, secret_key):\n"
            "    validated = check_token_signature(user_token, secret_key)\n"
            "    return validated\n"
        )
        # Minor typo/difference in search line
        search = (
            "def authenticate(user_token, secret_key):\n"
            "    validated = check_token_signature(user_token, secret_key)\n"
            "    return validated"
        )
        replace = (
            "def authenticate(user_token, secret_key):\n"
            "    return check_token_signature(user_token, secret_key)"
        )
        success, patched, err = Patcher.apply_patch(orig, search, replace, fuzzy=True)
        assert success is True
        assert "return check_token_signature" in patched


class TestMultiFilePatchBatchingAndTransactionalRollback:
    """Tests for multi-file patch batching with transactional all-or-nothing rollback."""

    def test_multi_file_batch_success_via_dict(self, tmp_path: Path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("val_a = 1\n", encoding="utf-8")
        f2.write_text("val_b = 2\n", encoding="utf-8")

        patches = {
            "a.py": "<<<<<<< SEARCH\nval_a = 1\n=======\nval_a = 10\n>>>>>>>",
            "b.py": "<<<<<<< SEARCH\nval_b = 2\n=======\nval_b = 20\n>>>>>>> REPLACE",
        }
        success, modified, err = Patcher.apply_multi_file_patches(patches, base_dir=tmp_path, validate_ast=True)
        assert success is True
        assert err == ""
        assert len(modified) == 2
        assert f1.read_text(encoding="utf-8") == "val_a = 10\n"
        assert f2.read_text(encoding="utf-8") == "val_b = 20\n"

    def test_multi_file_batch_success_via_text_header(self, tmp_path: Path):
        f1 = tmp_path / "mod1.py"
        f2 = tmp_path / "mod2.py"
        f1.write_text("def fn1(): return 1\n", encoding="utf-8")
        f2.write_text("def fn2(): return 2\n", encoding="utf-8")

        patch_text = (
            "### `mod1.py`\n"
            "<<<<<<< SEARCH\n"
            "def fn1(): return 1\n"
            "=======\n"
            "def fn1(): return 100\n"
            ">>>>>>> REPLACE\n\n"
            "### `mod2.py`\n"
            "<<<<<<< SEARCH\n"
            "def fn2(): return 2\n"
            "=======\n"
            "def fn2(): return 200\n"
            ">>>>>>> REPLACE\n"
        )
        success, modified, err = Patcher.apply_multi_file_patches(patch_text, base_dir=tmp_path, validate_ast=True)
        assert success is True
        assert f1.read_text(encoding="utf-8") == "def fn1(): return 100\n"
        assert f2.read_text(encoding="utf-8") == "def fn2(): return 200\n"

    def test_multi_file_rollback_when_second_file_search_fails(self, tmp_path: Path):
        f1 = tmp_path / "first.py"
        f2 = tmp_path / "second.py"
        orig1 = "x = 10\n"
        orig2 = "y = 20\n"
        f1.write_text(orig1, encoding="utf-8")
        f2.write_text(orig2, encoding="utf-8")

        patches = {
            "first.py": "<<<<<<< SEARCH\nx = 10\n=======\nx = 999\n>>>>>>>",
            "second.py": "<<<<<<< SEARCH\nNONEXISTENT = 0\n=======\ny = 888\n>>>>>>>",
        }
        success, modified, err = Patcher.apply_multi_file_patches(patches, base_dir=tmp_path, validate_ast=True)
        assert success is False
        assert "failed" in err.lower()
        # Both files must remain completely untouched
        assert f1.read_text(encoding="utf-8") == orig1
        assert f2.read_text(encoding="utf-8") == orig2

    def test_multi_file_rollback_when_second_file_ast_fails(self, tmp_path: Path):
        f1 = tmp_path / "file1.py"
        f2 = tmp_path / "file2.py"
        orig1 = "def valid(): return True\n"
        orig2 = "def valid2(): return True\n"
        f1.write_text(orig1, encoding="utf-8")
        f2.write_text(orig2, encoding="utf-8")

        patches = {
            "file1.py": "<<<<<<< SEARCH\ndef valid(): return True\n=======\ndef valid(): return False\n>>>>>>>",
            "file2.py": "<<<<<<< SEARCH\ndef valid2(): return True\n=======\ndef valid2(\n>>>>>>>",
        }
        success, modified, err = Patcher.apply_multi_file_patches(patches, base_dir=tmp_path, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        # File 1 must NOT be modified
        assert f1.read_text(encoding="utf-8") == orig1
        assert f2.read_text(encoding="utf-8") == orig2

    def test_multi_file_missing_target_file_aborts(self, tmp_path: Path):
        f1 = tmp_path / "exists.py"
        orig1 = "data = [1, 2, 3]\n"
        f1.write_text(orig1, encoding="utf-8")

        patches = {
            "exists.py": "<<<<<<< SEARCH\ndata = [1, 2, 3]\n=======\ndata = [4, 5, 6]\n>>>>>>>",
            "nonexistent.py": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>>",
        }
        success, modified, err = Patcher.apply_multi_file_patches(patches, base_dir=tmp_path, validate_ast=True)
        assert success is False
        assert "not found" in err.lower()
        assert f1.read_text(encoding="utf-8") == orig1

    def test_multi_file_patch_rejects_path_traversal(self, tmp_path: Path):
        outside = tmp_path.parent / "outside.py"
        outside.write_text("value = 1\n", encoding="utf-8")
        patches = {
            "../outside.py": "<<<<<<< SEARCH\nvalue = 1\n=======\nvalue = 2\n>>>>>>>"
        }

        success, modified, err = Patcher.apply_multi_file_patches(patches, base_dir=tmp_path)

        assert success is False
        assert modified == []
        assert "escapes base directory" in err
        assert outside.read_text(encoding="utf-8") == "value = 1\n"


class TestDiffPreviewRendering:
    """Tests for clean CLI diff preview rendering."""

    def test_generate_diff_structure(self):
        orig = "def add(a, b):\n    return a - b\n"
        patched = "def add(a, b):\n    return a + b\n"
        diff = Patcher.generate_diff(orig, patched, file_path="calc.py")
        assert "--- a/calc.py" in diff
        assert "+++ b/calc.py" in diff
        assert "-    return a - b" in diff
        assert "+    return a + b" in diff

    def test_get_diff_stats(self):
        orig = "line1\nline2\nline3\n"
        patched = "line1\nline2_mod\nline3\nline4\n"
        diff = Patcher.generate_diff(orig, patched, file_path="sample.txt")
        adds, dels = Patcher.get_diff_stats(diff)
        assert adds == 2  # line2_mod and line4
        assert dels == 1  # line2

    def test_render_diff_plain_and_colorized(self):
        orig = "a = 1\n"
        patched = "a = 2\n"
        diff = Patcher.generate_diff(orig, patched, file_path="test.py")

        plain = Patcher.render_diff(diff, colorize=False)
        assert "\033[" not in plain
        assert "-a = 1" in plain
        assert "+a = 2" in plain

        colored = Patcher.render_diff(diff, colorize=True)
        assert "\033[" in colored
        assert "a = 2" in colored

    def test_render_diff_preview_no_changes(self):
        code = "def stable(): pass\n"
        preview = Patcher.render_diff_preview(code, code, file_path="stable.py")
        assert preview == "[No changes]"

    def test_render_batch_diff_preview(self):
        diffs = {
            "calc.py": ("def add(a, b): return a - b\n", "def add(a, b): return a + b\n"),
            "sub.py": ("def sub(a, b): return a + b\n", "def sub(a, b): return a - b\n"),
        }
        rendered = Patcher.render_batch_diff_preview(diffs, colorize=False)
        assert "Diff Preview" in rendered
        assert "2 file(s) changed" in rendered
        assert "calc.py" in rendered
        assert "sub.py" in rendered
