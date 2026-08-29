"""
test_chaos_immunity.py - Unit and Integration Tests for K-CLI Chaos Immunity Engine
"""

import os
from pathlib import Path
import pytest
from k_cli.tools.chaos_immunity import ASTChaosProber, ChaosImmunityEngine, BrittlePattern, ImmunityReport


def test_ast_chaos_prober_detects_brittle_patterns(tmp_path):
    sample_code = '''
def process_user_data(payload):
    # Fragile KeyError risk
    user_id = payload["user_id"]
    # Fragile naked except
    try:
        import urllib.request
        # Fragile network call without timeout
        res = urllib.request.urlopen("https://api.example.com/data")
    except:
        pass
    return user_id
'''
    py_file = tmp_path / "sample_service.py"
    py_file.write_text(sample_code, encoding="utf-8")

    engine = ChaosImmunityEngine(repo_path=tmp_path)
    patterns = engine.probe_file(py_file)

    assert len(patterns) >= 2
    types = [p.pattern_type for p in patterns]
    assert "UNCHECKED_DICT_SUBSCRIPT" in types
    assert "BROAD_EXCEPTION_TRAP" in types or "MISSING_NETWORK_TIMEOUT" in types


def test_chaos_immunity_engine_inoculation_pipeline(tmp_path):
    sample_code = '''
def calculate_metrics(data):
    val = data["metric"]
    return val * 2
'''
    py_file = tmp_path / "metrics_service.py"
    py_file.write_text(sample_code, encoding="utf-8")

    engine = ChaosImmunityEngine(repo_path=tmp_path)
    report: ImmunityReport = engine.inoculate_file(py_file, auto_apply_patches=True)

    assert isinstance(report, ImmunityReport)
    assert report.generated_tests_count >= 2
    assert report.generated_test_suite_path is not None
    assert Path(report.generated_test_suite_path).exists()
    assert report.verification_passed is True

    md = report.render_markdown()
    assert "Chaos Immunity Report" in md
    assert "Detected Brittle Code Patterns" in md


def test_scan_and_inoculate_repo(tmp_path):
    py_file1 = tmp_path / "module_a.py"
    py_file1.write_text("def a(d):\n    return d['key']\n", encoding="utf-8")

    py_file2 = tmp_path / "module_b.py"
    py_file2.write_text("def b():\n    return 42\n", encoding="utf-8")

    engine = ChaosImmunityEngine(repo_path=tmp_path)
    reports = engine.scan_and_inoculate_repo(max_files=5)

    assert len(reports) == 2
    assert any(r.target_file == "module_a.py" for r in reports)
