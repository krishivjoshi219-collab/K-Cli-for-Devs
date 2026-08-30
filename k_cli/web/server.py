"""
server.py - FastAPI Web UI Server & Async REST / WebSocket API for K-CLI Engine
"""

from __future__ import annotations

import asyncio
import json
import os
import psutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from k_cli.agents.orchestrator import Orchestrator, Persona
from k_cli.core.llm_driver import LLMDriver
from k_cli.core.model_manager import MODEL_CATALOG
from k_cli.core.models_hub import ModelHub, ModelProvider
from k_cli.core.session import SessionManager
from k_cli.git.conflict_resolver import ConflictResolver
from k_cli.git.smart_git import SmartGitEngine
from k_cli.git.verifier import Verifier
from k_cli.tools.chaos_immunity import ChaosImmunityEngine
from k_cli.tools.doc_retriever import DocRetriever
from k_cli.tools.security_healer import SecurityHealer

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    prompt: str
    language: str = "python"
    model: str = "qwen2.5-coder:1.5b"
    max_retries: int = 3
    persona: Optional[str] = None
    mock: bool = False


class CrashTriageRequest(BaseModel):
    log_text: str
    repo_path: str = "."


class ConflictResolveRequest(BaseModel):
    file_path: Optional[str] = None
    repo_path: str = "."
    model: Optional[str] = None
    auto_stage: bool = True
    mock: bool = False


class SecurityHealRequest(BaseModel):
    vuln_id: Optional[str] = None
    heal_all: bool = False
    repo_path: str = "."


class ChaosInoculateRequest(BaseModel):
    target_file: Optional[str] = None
    repo_path: str = "."
    auto_apply: bool = True


class DevDocsSearchRequest(BaseModel):
    query: str
    limit: int = 5
    max_tokens: int = 250


class ModelTestRequest(BaseModel):
    model_name: str
    prompt: str = "Write a python fibonacci function."


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="K-CLI World-Class Web UI",
        description="Autonomous Self-Healing DevOps & Engineering Workstation Web Dashboard",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # REST Endpoints

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return index_file.read_text(encoding="utf-8")
        return HTMLResponse("<html><body><h1>K-CLI Web UI</h1><p>Static index.html not found.</p></body></html>")

    @app.get("/api/status")
    async def get_status():
        session = SessionManager()
        driver = LLMDriver()
        process = psutil.Process()
        ram_mb = process.memory_info().rss / (1024 * 1024)

        return {
            "status": "online",
            "active_model": driver.model_name,
            "git_branch": session.get_git_branch(),
            "active_persona": session.active_persona,
            "ram_usage_mb": round(ram_mb, 2),
            "ram_budget_mb": 1024.0,
            "python_version": sys.version.split()[0],
            "ollama_available": driver.is_ollama_available(),
            "mock_mode": driver.mock_mode,
        }

    @app.post("/api/run")
    async def run_agent(req: AgentRunRequest):
        driver = LLMDriver(model_name=req.model, mock_mode=req.mock)
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=req.max_retries, persona=req.persona)

        result = orchestrator.execute_pipeline(
            user_prompt=req.prompt,
            language=req.language,
            persona=req.persona,
        )

        return {
            "success": result.success,
            "final_code": result.final_code,
            "architecture_plan": result.architecture_plan,
            "attempts": result.attempts,
            "ram_usage_mb": round(result.ram_usage_mb, 2),
            "history": result.history,
            "verification": result.verification.to_dict() if result.verification else None,
        }

    @app.post("/api/triage")
    async def triage_crash(req: CrashTriageRequest):
        from k_cli.agents.strands_agent import triage_and_heal_incident
        try:
            report_raw = triage_and_heal_incident(req.log_text, repo_path=req.repo_path)
            report = json.loads(report_raw)
            return {"success": True, "report": report}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/conflicts")
    async def list_conflicts(repo_path: str = "."):
        resolver = ConflictResolver()
        conflicts = resolver.find_conflicts(repo_path=repo_path)
        return {
            "total_conflicts": len(conflicts),
            "conflicts": [c.to_dict() for c in conflicts],
        }

    @app.post("/api/conflicts/resolve")
    async def resolve_conflicts(req: ConflictResolveRequest):
        resolver = ConflictResolver(default_model=req.model)
        driver = LLMDriver(model_name=req.model or "qwen2.5-coder:1.5b", mock_mode=req.mock)
        verifier = Verifier()

        if req.file_path:
            res = resolver.resolve_file(
                file_path=req.file_path,
                llm_driver=driver,
                verifier=verifier,
                auto_stage=req.auto_stage,
            )
            return {"success": res.success, "result": res.to_dict()}
        else:
            summary = resolver.resolve_all_conflicts(
                repo_path=req.repo_path,
                llm_driver=driver,
                verifier=verifier,
                auto_stage=req.auto_stage,
            )
            return {"success": summary.success, "summary": summary.to_dict()}

    @app.get("/api/security/scan")
    async def security_scan(repo_path: str = "."):
        healer = SecurityHealer(repo_path=repo_path)
        report = healer.scan_repository()
        return report.to_dict()

    @app.post("/api/security/heal")
    async def security_heal(req: SecurityHealRequest):
        healer = SecurityHealer(repo_path=req.repo_path)
        if req.vuln_id:
            res = healer.auto_heal_vulnerability(vuln_id=req.vuln_id)
            return {"success": res.success, "results": [res.to_dict()]}
        elif req.heal_all:
            results = healer.heal_all_vulnerabilities()
            return {"success": True, "results": [r.to_dict() for r in results]}
        else:
            raise HTTPException(status_code=400, detail="Must specify vuln_id or heal_all=True")

    @app.get("/api/chaos/scan")
    async def chaos_scan(repo_path: str = "."):
        engine = ChaosImmunityEngine(repo_path=repo_path)
        reports = engine.scan_and_inoculate_repo(max_files=10)
        return {
            "total_modules": len(reports),
            "reports": [
                {
                    "target_file": r.target_file,
                    "patterns_detected": len(r.patterns_detected),
                    "generated_tests_count": r.generated_tests_count,
                    "patches_applied_count": r.patches_applied_count,
                    "verification_passed": r.verification_passed,
                    "summary": r.summary,
                }
                for r in reports
            ],
        }

    @app.post("/api/chaos/inoculate")
    async def chaos_inoculate(req: ChaosInoculateRequest):
        engine = ChaosImmunityEngine(repo_path=req.repo_path)
        if req.target_file:
            report = engine.inoculate_file(req.target_file, auto_apply_patches=req.auto_apply)
            return {
                "success": report.verification_passed,
                "target_file": report.target_file,
                "patterns_detected": len(report.patterns_detected),
                "summary": report.summary,
            }
        else:
            reports = engine.scan_and_inoculate_repo(max_files=10)
            return {"success": True, "count": len(reports)}

    @app.post("/api/devdocs/search")
    async def devdocs_search(req: DevDocsSearchRequest):
        retriever = DocRetriever()
        results = retriever.search(req.query, limit=req.limit, max_tokens=req.max_tokens)
        return {"query": req.query, "results": results}

    @app.get("/api/models")
    async def list_models():
        hub = ModelHub()
        models = hub.list_models()
        return {"models": [m.to_dict() for m in models]}

    @app.post("/api/models/test")
    async def test_model(req: ModelTestRequest):
        hub = ModelHub()
        res = hub.benchmark_model(model_name=req.model_name, prompt=req.prompt)
        return res.to_dict()

    # WebSocket for real-time agent token streaming
    @app.websocket("/ws/agent")
    async def websocket_agent(websocket: WebSocket):
        await websocket.accept()
        try:
            data_raw = await websocket.receive_text()
            data = json.loads(data_raw)
            prompt = data.get("prompt", "")
            language = data.get("language", "python")
            model = data.get("model", "qwen2.5-coder:1.5b")
            mock = data.get("mock", False)
            persona = data.get("persona")

            await websocket.send_json({"type": "start", "prompt": prompt, "model": model})

            loop = asyncio.get_running_loop()

            def sync_stream_callback(current_persona, token: str):
                p_str = current_persona.value if hasattr(current_persona, "value") else str(current_persona)
                msg = {"type": "token", "persona": p_str, "token": token}
                asyncio.run_coroutine_threadsafe(websocket.send_json(msg), loop)

            driver = LLMDriver(model_name=model, mock_mode=mock)
            verifier = Verifier()
            orchestrator = Orchestrator(driver=driver, verifier=verifier, persona=persona)

            result = await loop.run_in_executor(
                None,
                lambda: orchestrator.execute_pipeline(
                    user_prompt=prompt,
                    language=language,
                    token_stream_callback=sync_stream_callback,
                    persona=persona,
                ),
            )

            await websocket.send_json({
                "type": "complete",
                "success": result.success,
                "final_code": result.final_code,
                "attempts": result.attempts,
                "ram_usage_mb": round(result.ram_usage_mb, 2),
            })
        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

    return app


def start_web_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = False):
    import uvicorn

    app = create_app()

    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_web_server(port=8000)
