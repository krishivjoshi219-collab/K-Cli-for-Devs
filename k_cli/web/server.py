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
from k_cli.core.credentials import CredentialsManager, DevPreferencesManager, detect_key_type
from k_cli.core.llm_driver import LLMDriver
from k_cli.core.model_manager import MODEL_CATALOG
from k_cli.core.models_hub import ModelHub, ModelProvider, ModelSpec
from k_cli.core.session import SessionManager
from k_cli.core.smart_router import AdaptiveIntentRouter
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


class SaveKeyRequest(BaseModel):
    key_value: str
    key_name: Optional[str] = None


class TestKeyRequest(BaseModel):
    key_name: str


class CustomModelRequest(BaseModel):
    model_id: str
    provider: Optional[str] = "custom"
    description: Optional[str] = "Custom developer model"
    base_url: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Real-Time Agent Activity Broadcast Manager
# ─────────────────────────────────────────────────────────────────────────────

class ActivityMonitorManager:
    """Broadcaster for real-time dual-window agent execution tracking."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

monitor_manager = ActivityMonitorManager()


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

    @app.get("/favicon.ico")
    async def get_favicon():
        from fastapi import Response
        return Response(status_code=204)

    @app.get("/v1/models")
    async def get_v1_models():
        hub = ModelHub()
        models = hub.list_models()
        return {
            "object": "list",
            "data": [
                {"id": m.id, "object": "model", "created": int(time.time()), "owned_by": m.provider.value if hasattr(m.provider, "value") else str(m.provider)}
                for m in models
            ]
        }

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return index_file.read_text(encoding="utf-8")
        return HTMLResponse("<html><body><h1>K-CLI Web UI</h1><p>Static index.html not found.</p></body></html>")

    @app.get("/monitor", response_class=HTMLResponse)
    async def get_monitor():
        monitor_file = STATIC_DIR / "monitor.html"
        if monitor_file.exists():
            return monitor_file.read_text(encoding="utf-8")
        return HTMLResponse("<html><body><h1>K-CLI Live Monitor</h1><p>Static monitor.html not found.</p></body></html>")

    @app.websocket("/ws/monitor")
    async def websocket_monitor(websocket: WebSocket):
        await monitor_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            monitor_manager.disconnect(websocket)
        except Exception:
            monitor_manager.disconnect(websocket)

    @app.get("/api/status")
    async def get_status():
        ram_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
        git_engine = SmartGitEngine(".")
        branch = git_engine.get_current_branch()
        active_model = DevPreferencesManager.get_default_model()

        return {
            "status": "online",
            "active_model": active_model,
            "git_branch": branch,
            "ram_usage_mb": ram_mb,
            "timestamp": time.time(),
        }

    @app.post("/api/run")
    async def run_agent_task(req: AgentRunRequest):
        model, route_reason = AdaptiveIntentRouter.resolve_model_for_prompt(req.prompt, req.model)

        driver = LLMDriver(model_name=model, mock_mode=req.mock)
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=req.max_retries, persona=req.persona)

        result = orchestrator.execute_pipeline(
            user_prompt=req.prompt,
            language=req.language,
            persona=req.persona,
        )

        errors = [result.verification.error_trace] if (result.verification and result.verification.error_trace) else []

        return {
            "success": result.success,
            "final_code": result.final_code,
            "attempts": result.attempts,
            "ram_usage_mb": round(result.ram_usage_mb, 2),
            "route_reason": route_reason,
            "model_used": model,
            "errors": errors,
        }

    @app.post("/api/triage")
    async def triage_crash_log(req: CrashTriageRequest):
        from k_cli.agents.strands_agent import triage_and_heal_incident
        report_str = triage_and_heal_incident(req.log_text, repo_path=req.repo_path)
        try:
            report = json.loads(report_str)
        except Exception:
            report = {"summary": report_str}

        return {"success": True, "report": report}

    @app.get("/api/conflicts")
    async def list_conflicts(repo_path: str = "."):
        resolver = ConflictResolver()
        conflicts = resolver.find_conflicts(repo_path=repo_path)
        return {
            "total_conflicts": len(conflicts),
            "conflicts": [c.to_dict() for c in conflicts],
        }

    @app.post("/api/conflicts/resolve")
    async def resolve_conflict(req: ConflictResolveRequest):
        resolver = ConflictResolver(default_model=req.model)
        if req.file_path:
            result = resolver.resolve_file(req.file_path, model_name=req.model, auto_stage=req.auto_stage, mock=req.mock)
            return result.to_dict()
        else:
            result = resolver.resolve_all_conflicts(repo_path=req.repo_path, model_name=req.model, auto_stage=req.auto_stage, mock=req.mock)
            return result.to_dict()

    @app.get("/api/security/scan")
    async def security_scan(repo_path: str = "."):
        healer = SecurityHealer(repo_path=repo_path)
        report = healer.scan_repository()
        return {
            "total_findings": len(report.findings),
            "findings": [f.to_dict() for f in report.findings],
        }

    @app.post("/api/security/heal")
    async def security_heal(req: SecurityHealRequest):
        healer = SecurityHealer(repo_path=req.repo_path)
        if req.heal_all:
            results = healer.heal_all()
            return {"success": True, "healed_count": len(results)}
        elif req.vuln_id:
            res = healer.heal_vulnerability(req.vuln_id)
            return {"success": res.success, "diff": res.diff, "error": res.error}
        else:
            raise HTTPException(status_code=400, detail="Must provide vuln_id or heal_all=True")

    @app.get("/api/chaos/scan")
    async def chaos_scan(repo_path: str = "."):
        engine = ChaosImmunityEngine(repo_path=repo_path)
        root = Path(repo_path).resolve()
        py_files = [str(p.relative_to(root)) for p in root.rglob("*.py") if not any(part.startswith((".", "venv", "__pycache__", "build", "dist")) for part in p.parts)][:20]
        return {"total_modules": len(py_files), "modules": py_files}

    @app.post("/api/chaos/inoculate")
    async def chaos_inoculate(req: ChaosInoculateRequest):
        engine = ChaosImmunityEngine(repo_dir=req.repo_path)
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

    @app.get("/api/credentials")
    async def get_credentials():
        return {"statuses": CredentialsManager.get_key_statuses()}

    @app.post("/api/credentials")
    async def save_credentials(req: SaveKeyRequest):
        key_name, provider_name = CredentialsManager.save_any_key(req.key_value, explicit_key_name=req.key_name)
        return {"success": True, "key_name": key_name, "provider_name": provider_name}

    @app.post("/api/credentials/test")
    async def test_credential(req: TestKeyRequest):
        ok, msg = CredentialsManager.test_key_connectivity(req.key_name)
        return {"success": ok, "message": msg, "key_name": req.key_name}

    @app.get("/api/models")
    async def list_models(all_catalog: bool = False):
        hub = ModelHub()
        loop = asyncio.get_running_loop()
        active_models = await loop.run_in_executor(None, hub.get_verified_active_models)
        all_specs = await loop.run_in_executor(None, hub.list_models)

        active_ids = {m.id for m in active_models}
        out_list = []
        for m in (all_specs if all_catalog else (active_models or all_specs)):
            d = m.to_dict()
            d["is_online"] = m.id in active_ids
            out_list.append(d)

        return {
            "models": out_list,
            "default_model": DevPreferencesManager.get_default_model(),
            "active_count": len(active_models),
            "total_count": len(all_specs),
        }

    @app.post("/api/models/custom")
    async def register_custom_model(req: CustomModelRequest):
        hub = ModelHub()
        spec = ModelSpec(
            id=req.model_id.strip(),
            name=f"Custom: {req.model_id.strip()}",
            provider=ModelProvider.OPENAI_COMPATIBLE if req.base_url else ModelProvider.OLLAMA,
            base_url=req.base_url,
            is_local=not bool(req.base_url),
            description=req.description or "User custom registered model",
        )
        hub.register_model(spec)
        DevPreferencesManager.set_default_model(spec.id)
        return {"success": True, "model": spec.to_dict()}

    @app.post("/api/models/test")
    async def test_model(req: ModelTestRequest):
        hub = ModelHub()
        res = hub.benchmark_model(model_name=req.model_name, prompt=req.prompt)
        return res.to_dict()

    @app.get("/api/models/default")
    async def get_default_model():
        return {"default_model": DevPreferencesManager.get_default_model()}

    @app.post("/api/models/default")
    async def set_default_model(req: ModelTestRequest):
        DevPreferencesManager.set_default_model(req.model_name)
        return {"success": True, "default_model": req.model_name}

    # WebSocket for real-time agent token streaming
    @app.websocket("/ws/agent")
    async def websocket_agent(websocket: WebSocket):
        await websocket.accept()
        try:
            data_raw = await websocket.receive_text()
            data = json.loads(data_raw)
            prompt = data.get("prompt", "")
            language = data.get("language", "python")
            raw_model = data.get("model", "auto")
            mock = data.get("mock", False)
            persona = data.get("persona")

            model, route_reason = AdaptiveIntentRouter.resolve_model_for_prompt(prompt, raw_model)

            start_payload = {"type": "start", "prompt": prompt, "model": model, "route_reason": route_reason, "timestamp": time.time()}
            await websocket.send_json(start_payload)
            await monitor_manager.broadcast(start_payload)

            loop = asyncio.get_running_loop()

            def sync_stream_callback(current_persona, token: str):
                p_str = current_persona.value if hasattr(current_persona, "value") else str(current_persona)
                msg = {"type": "token", "persona": p_str, "token": token, "timestamp": time.time()}
                asyncio.run_coroutine_threadsafe(websocket.send_json(msg), loop)
                asyncio.run_coroutine_threadsafe(monitor_manager.broadcast(msg), loop)

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

            if result.final_code:
                await websocket.send_json({
                    "type": "token",
                    "persona": persona or "CODER",
                    "token": f"\n\n```\n{result.final_code}\n```\n" if "\n" in result.final_code and "```" not in result.final_code else "",
                })

            comp_payload = {
                "type": "done",
                "success": result.success,
                "final_code": result.final_code,
                "attempts": result.attempts,
                "ram_usage_mb": round(result.ram_usage_mb, 2),
                "timestamp": time.time(),
            }
            await websocket.send_json(comp_payload)
            await monitor_manager.broadcast(comp_payload)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                err_payload = {"type": "error", "message": str(e), "timestamp": time.time()}
                await websocket.send_json(err_payload)
                await monitor_manager.broadcast(err_payload)
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
