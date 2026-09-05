"""
model_manager.py - Model Bootstrapper & Auto-Sync Engine for K-CLI (Project Bankai)

Manages automated model lifecycle:
1. Pulls quantized Bankai GGUF models (e.g. krishivjoshi/bankai-7b, krishivjoshi/bankai-10b)
   from Hugging Face Hub directly into Ollama or local GGUF cache (~/.kcli/models, ~/models).
2. Verifies SHA256 cryptographic integrity of downloaded GGUF binaries.
3. Checks local Ollama instance health and auto-creates Ollama models via Modelfiles.
4. Seamlessly integrates with K-CLI LLM Driver and Typer CLI interface.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("k_cli.model_manager")

# ------------------------------------------------------------------------------
# Constants & Defaults
# ------------------------------------------------------------------------------
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_KCLI_DIR = Path.home() / ".kcli"
DEFAULT_MODELS_DIR = DEFAULT_KCLI_DIR / "models"
FALLBACK_MODELS_DIR = Path.home() / "models"

# Standard ChatML Prompt Template for Bankai Qwen-based models
DEFAULT_CHATML_TEMPLATE = """<|im_start|>system
{{ .System }}<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
{{ .Response }}<|im_end|>
"""

# Preset Model Catalog
MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "bankai-7b": {
        "repo_id": "krishivjoshi/bankai-7b",
        "default_filename": "bankai-7b.gguf",
        "candidate_filenames": [
            "bankai-7b.gguf",
            "bankai-7b-q4_k_m.gguf",
            "bankai-7b.Q4_K_M.gguf",
            "qwen2.5-coder-7b-instruct.Q4_K_M.gguf",
        ],
        "ollama_tag": "bankai:7b",
        "aliases": ["bankai-7b", "bankai:7b", "7b", "krishivjoshi/bankai-7b"],
        "system_prompt": (
            "You are Bankai-7B, an elite compiler-grounded AI coding model operating under strict "
            "1.0 GB RAM constraints. You specialize in complex AST code generation, surgical "
            "SEARCH/REPLACE patches, zero-fluff critique, and step-by-step technical reasoning inside <think>...</think> tags."
        ),
        "temperature": 0.2,
        "top_p": 0.95,
        "repeat_penalty": 1.1,
        "stop_tokens": ["<|im_start|>", "<|im_end|>"],
    },
    "bankai-10b": {
        "repo_id": "krishivjoshi/bankai-10b",
        "default_filename": "bankai-10b.gguf",
        "candidate_filenames": [
            "bankai-10b.gguf",
            "bankai-10b-q4_k_m.gguf",
            "bankai-10b.Q4_K_M.gguf",
            "qwen2.5-coder-10b-instruct.Q4_K_M.gguf",
        ],
        "ollama_tag": "bankai:10b",
        "aliases": ["bankai-10b", "bankai:10b", "10b", "krishivjoshi/bankai-10b"],
        "system_prompt": (
            "You are Bankai-10B, a high-capacity compiler-grounded AI coding model operating under strict "
            "RAM constraints. You specialize in multi-file architecture reasoning, surgical AST patches, "
            "and formal verification inside <think>...</think> tags."
        ),
        "temperature": 0.2,
        "top_p": 0.95,
        "repeat_penalty": 1.1,
        "stop_tokens": ["<|im_start|>", "<|im_end|>"],
    },
    "bankai-1.5b": {
        "repo_id": "krishivjoshi/bankai-1.5b",
        "default_filename": "bankai-1.5b.gguf",
        "candidate_filenames": [
            "bankai-1.5b.gguf",
            "bankai-1.5b-q4_k_m.gguf",
            "qwen2.5-coder-1.5b-instruct.Q4_K_M.gguf",
        ],
        "ollama_tag": "bankai:1.5b",
        "aliases": ["bankai-1.5b", "bankai:1.5b", "1.5b", "krishivjoshi/bankai-1.5b"],
        "system_prompt": (
            "You are Bankai-1.5B, a fast lightweight compiler-grounded AI coding model operating under strict "
            "1.0 GB RAM constraints. You specialize in AST code generation and surgical patches inside <think>...</think> tags."
        ),
        "temperature": 0.2,
        "top_p": 0.95,
        "repeat_penalty": 1.1,
        "stop_tokens": ["<|im_start|>", "<|im_end|>"],
    },
    "bankai-3b": {
        "repo_id": "krishivjoshi/bankai-3b",
        "default_filename": "bankai-3b.gguf",
        "candidate_filenames": [
            "bankai-3b.gguf",
            "bankai-3b-q4_k_m.gguf",
            "qwen2.5-coder-3b-instruct.Q4_K_M.gguf",
        ],
        "ollama_tag": "bankai:3b",
        "aliases": ["bankai-3b", "bankai:3b", "3b", "krishivjoshi/bankai-3b"],
        "system_prompt": (
            "You are Bankai-3B, an elite compiler-grounded AI coding model operating under strict "
            "1.0 GB RAM constraints. You specialize in unpadded code generation, surgical SEARCH/REPLACE patches, "
            "AST syntax validation, and step-by-step technical reasoning inside <think>...</think> tags."
        ),
        "temperature": 0.2,
        "top_p": 0.95,
        "repeat_penalty": 1.1,
        "stop_tokens": ["<|im_start|>", "<|im_end|>"],
    },
    "bankai-14b": {
        "repo_id": "krishivjoshi/bankai-14b",
        "default_filename": "bankai-14b.gguf",
        "candidate_filenames": [
            "bankai-14b.gguf",
            "bankai-14b-q4_k_m.gguf",
            "bankai-14b.Q4_K_M.gguf",
            "qwen2.5-coder-14b-instruct.Q4_K_M.gguf",
        ],
        "ollama_tag": "bankai:14b",
        "aliases": ["bankai-14b", "bankai:14b", "14b", "krishivjoshi/bankai-14b"],
        "system_prompt": (
            "You are Bankai-14B, an elite distilled reasoning coding model. You decouple pure reasoning from static memorization: "
            "all code syntax, API references, and library docs are dynamically supplied by the SQLite DevDocs indexer and codebase QA. "
            "You specialize in complex multi-file AST architecture, surgical patches, and formal verification inside <think>...</think> tags."
        ),
        "temperature": 0.2,
        "top_p": 0.95,
        "repeat_penalty": 1.1,
        "stop_tokens": ["<|im_start|>", "<|im_end|>"],
    },
}


@dataclass
class ModelPullResult:
    """Structured result from a model pull operation."""
    success: bool
    model_name: str
    ollama_tag: str
    gguf_path: Optional[Path] = None
    modelfile_path: Optional[Path] = None
    sha256: Optional[str] = None
    sha256_verified: bool = False
    ollama_created: bool = False
    ollama_healthy: bool = False
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "model_name": self.model_name,
            "ollama_tag": self.ollama_tag,
            "gguf_path": str(self.gguf_path) if self.gguf_path else None,
            "modelfile_path": str(self.modelfile_path) if self.modelfile_path else None,
            "sha256": self.sha256,
            "sha256_verified": self.sha256_verified,
            "ollama_created": self.ollama_created,
            "ollama_healthy": self.ollama_healthy,
            "message": self.message,
            "details": self.details,
        }


class ModelManager:
    """
    Automated Model Lifecycle, GGUF Cache, Integrity Verification, and Ollama Registration Engine.
    """

    def __init__(
        self,
        models_dir: Optional[Union[str, Path]] = None,
        ollama_url: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        if models_dir is not None:
            self.models_dir = Path(models_dir).resolve()
        else:
            self.models_dir = DEFAULT_MODELS_DIR

        # Ensure model cache directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)

        env_ollama = os.getenv("OLLAMA_HOST")
        self.ollama_url = (ollama_url or env_ollama or DEFAULT_OLLAMA_URL).rstrip("/")
        if not self.ollama_url.startswith("http"):
            self.ollama_url = f"http://{self.ollama_url}"

        if mock_mode is not None:
            self.mock_mode = bool(mock_mode)
        else:
            self.mock_mode = os.getenv("KCLI_MOCK_MODE", "").lower() in ("true", "1") or (
                "PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM")
            )

        # Internal mock state for testing
        self._mock_ollama_models: List[str] = ["qwen2.5-coder:1.5b", "bankai:1.5b"]

    # --------------------------------------------------------------------------
    # 1. Model Resolution & Spec Lookup
    # --------------------------------------------------------------------------

    @staticmethod
    def resolve_model_spec(model_identifier: str) -> Dict[str, Any]:
        """
        Resolves model metadata and parameters for a given name, alias, or HF repo.
        """
        clean_id = model_identifier.strip().lower()

        # Exact key or alias match
        for key, spec in MODEL_CATALOG.items():
            if clean_id == key or clean_id in spec.get("aliases", []):
                return dict(spec)

        # Partial matching (e.g. '7b' -> 'bankai-7b')
        for key, spec in MODEL_CATALOG.items():
            if clean_id in key or any(clean_id == a.lower() for a in spec.get("aliases", [])):
                return dict(spec)

        # Fallback for custom Hugging Face repository or custom model tag
        repo_id = model_identifier if "/" in model_identifier else f"krishivjoshi/{model_identifier}"
        clean_name = model_identifier.split("/")[-1].replace(":", "-")
        tag_name = model_identifier.split("/")[-1].replace("-", ":")
        return {
            "repo_id": repo_id,
            "default_filename": f"{clean_name}.gguf",
            "candidate_filenames": [f"{clean_name}.gguf", f"{clean_name}-q4_k_m.gguf", f"{clean_name}.Q4_K_M.gguf"],
            "ollama_tag": tag_name,
            "aliases": [model_identifier, clean_name, tag_name],
            "system_prompt": (
                f"You are {clean_name.upper()}, an elite compiler-grounded AI coding model operating under "
                "strict RAM constraints. You specialize in AST code generation and surgical patches inside <think>...</think> tags."
            ),
            "temperature": 0.2,
            "top_p": 0.95,
            "repeat_penalty": 1.1,
            "stop_tokens": ["<|im_start|>", "<|im_end|>"],
        }

    # --------------------------------------------------------------------------
    # 2. Ollama Health & Model Registration
    # --------------------------------------------------------------------------

    def check_ollama_health(self) -> Dict[str, Any]:
        """
        Checks local Ollama service availability, version, and loaded models.
        """
        if self.mock_mode:
            return {
                "healthy": True,
                "version": "0.1.0-mock",
                "models": list(self._mock_ollama_models),
                "url": self.ollama_url,
                "error": None,
            }

        health_data: Dict[str, Any] = {
            "healthy": False,
            "version": "unknown",
            "models": [],
            "url": self.ollama_url,
            "error": None,
        }

        # 1. Check /api/tags
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
                    health_data["healthy"] = True
                    health_data["models"] = [m for m in models if m]
        except Exception as e:
            health_data["error"] = str(e)
            return health_data

        # 2. Check /api/version if available
        try:
            req_ver = urllib.request.Request(f"{self.ollama_url}/api/version", method="GET")
            with urllib.request.urlopen(req_ver, timeout=2.0) as resp:
                if resp.status == 200:
                    v_data = json.loads(resp.read().decode("utf-8"))
                    health_data["version"] = v_data.get("version", "unknown")
        except Exception:
            pass

        return health_data

    def is_ollama_available(self) -> bool:
        """Returns True if local Ollama daemon is active and responsive."""
        return self.check_ollama_health().get("healthy", False)

    def list_ollama_models(self) -> List[str]:
        """Returns list of all model tags available in Ollama."""
        return self.check_ollama_health().get("models", [])

    def has_ollama_model(self, model_tag: str) -> bool:
        """Checks whether a specific model tag exists in Ollama."""
        models = self.list_ollama_models()
        target = model_tag.strip().lower()
        for m in models:
            m_low = m.lower()
            if target == m_low or m_low.startswith(target) or target.startswith(m_low.split(":")[0]):
                return True
            # Also check without tag suffix (e.g. bankai-7b vs bankai:7b)
            norm_target = target.replace("-", ":")
            norm_m = m_low.replace("-", ":")
            if norm_target == norm_m or norm_target.split(":")[0] == norm_m.split(":")[0]:
                if ":" in target and ":" in m_low and target.split(":")[-1] == m_low.split(":")[-1]:
                    return True
        return False

    # --------------------------------------------------------------------------
    # 3. Cryptographic SHA256 Integrity Verification
    # --------------------------------------------------------------------------

    @staticmethod
    def compute_sha256(
        file_path: Union[str, Path],
        chunk_size: int = 1024 * 1024 * 4, # 4MB chunks
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Computes SHA256 hash of a local binary file.
        """
        fp = Path(file_path)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError(f"Cannot compute SHA256: file '{fp}' not found.")

        total_size = fp.stat().st_size
        bytes_read = 0
        sha256_hasher = hashlib.sha256()

        with open(fp, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256_hasher.update(chunk)
                bytes_read += len(chunk)
                if progress_callback:
                    progress_callback(bytes_read, total_size)

        return sha256_hasher.hexdigest().lower()

    @classmethod
    def verify_sha256(
        cls,
        file_path: Union[str, Path],
        expected_sha256: str,
        chunk_size: int = 1024 * 1024 * 4,
    ) -> bool:
        """
        Validates whether file matches expected SHA256 digest.
        """
        if not expected_sha256 or not expected_sha256.strip():
            return False
        calculated = cls.compute_sha256(file_path, chunk_size=chunk_size)
        return calculated.lower() == expected_sha256.strip().lower()

    def fetch_hf_metadata(
        self,
        repo_id: str,
        filename: Optional[str] = None,
        hf_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries Hugging Face API to extract remote file list and LFS SHA256 metadata.
        """
        if self.mock_mode:
            return {
                "repo_id": repo_id,
                "files": [filename or "model.gguf"],
                "lfs_sha256": {"bankai-7b.gguf": "mock_sha256_bankai_7b", "bankai-10b.gguf": "mock_sha256_bankai_10b"},
                "size_map": {filename or "model.gguf": 4000000000},
            }

        token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        meta_url = f"https://huggingface.co/api/models/{repo_id}"
        headers = {"User-Agent": "K-CLI/0.2.0 ModelManager"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            req = urllib.request.Request(meta_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    siblings = data.get("siblings", [])
                    file_names = [s.get("rfilename", "") for s in siblings if isinstance(s, dict)]
                    lfs_map: Dict[str, str] = {}
                    size_map: Dict[str, int] = {}

                    # Inspect siblings or tags for LFS hashes
                    for s in siblings:
                        fn = s.get("rfilename", "")
                        lfs = s.get("lfs", {})
                        if isinstance(lfs, dict) and "sha256" in lfs:
                            lfs_map[fn] = lfs["sha256"]
                        if isinstance(lfs, dict) and "size" in lfs:
                            size_map[fn] = lfs["size"]

                    return {
                        "repo_id": repo_id,
                        "files": file_names,
                        "lfs_sha256": lfs_map,
                        "size_map": size_map,
                    }
        except Exception as e:
            logger.debug(f"HF API metadata lookup notice for {repo_id}: {e}")

        return {"repo_id": repo_id, "files": [], "lfs_sha256": {}, "size_map": {}}

    # --------------------------------------------------------------------------
    # 4. GGUF Location & Hugging Face Hub Pull
    # --------------------------------------------------------------------------

    def find_local_gguf(self, model_identifier: str) -> Optional[Path]:
        """
        Searches local storage directories for existing GGUF binaries.
        """
        spec = self.resolve_model_spec(model_identifier)
        candidates = spec.get("candidate_filenames", [spec.get("default_filename", f"{model_identifier}.gguf")])

        search_dirs = [
            self.models_dir,
            FALLBACK_MODELS_DIR,
            DEFAULT_KCLI_DIR,
            Path("/content"), # Colab runtime root
            Path("/content/bankai_7b_model"),
            Path("/content/bankai_10b_model"),
            Path("/content/bankai_14b_model"),
            Path("/kaggle/working"), # Kaggle runtime root
            Path("/kaggle/working/models"),
            Path("/kaggle/input"),
        ]

        for s_dir in search_dirs:
            if not s_dir.exists():
                continue
            for cand in candidates:
                p = s_dir / cand
                if p.exists() and p.is_file() and p.stat().st_size > 1024:
                    return p

            # Also check direct glob matches
            clean_name = model_identifier.split("/")[-1].replace(":", "-").lower()
            for f in s_dir.glob("*.gguf"):
                if clean_name in f.name.lower():
                    return f

        return None

    def download_from_hf(
        self,
        repo_id: str,
        filename: Optional[str] = None,
        target_path: Optional[Path] = None,
        hf_token: Optional[str] = None,
        quant_preference: str = "q4_k_m",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Downloads GGUF weights directly from Hugging Face Hub.
        """
        token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

        # Resolve candidate filename if not specified
        resolved_filename = filename
        if not resolved_filename:
            # Check model metadata
            meta = self.fetch_hf_metadata(repo_id, hf_token=token)
            files = meta.get("files", [])
            gguf_files = [f for f in files if f.endswith(".gguf")]
            if gguf_files:
                # Prefer requested quantization
                pref = [f for f in gguf_files if quant_preference.lower() in f.lower()]
                resolved_filename = pref[0] if pref else gguf_files[0]
            else:
                spec = self.resolve_model_spec(repo_id)
                resolved_filename = spec.get("default_filename", "model.gguf")

        # Target destination
        if target_path is not None:
            dest = Path(target_path).resolve()
        else:
            dest = self.models_dir / resolved_filename

        dest.parent.mkdir(parents=True, exist_ok=True)

        if self.mock_mode:
            # In mock mode, write a lightweight mock binary file
            if not dest.exists():
                mock_content = (
                    b"GGUF\x03\x00\x00\x00"  # Valid GGUF magic header
                    b"\x00\x00\x00\x00\x00\x00\x00\x00"
                    + f"Mock weights for {repo_id}/{resolved_filename}".encode("utf-8")
                )
                dest.write_bytes(mock_content)
            if progress_callback:
                progress_callback(len(dest.read_bytes()), len(dest.read_bytes()))
            return dest

        # Strategy 1: huggingface_hub library
        try:
            from huggingface_hub import hf_hub_download
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=resolved_filename,
                token=token,
                local_dir=str(self.models_dir),
                local_dir_use_symlinks=False,
            )
            downloaded_path = Path(downloaded)
            if downloaded_path.resolve() != dest.resolve():
                shutil.copy2(downloaded_path, dest)
            return dest
        except Exception as e_hf:
            logger.debug(f"huggingface_hub direct download fallback: {e_hf}")

        # Strategy 2: Direct HTTP Streaming Download
        download_url = f"https://huggingface.co/{repo_id}/resolve/main/{resolved_filename}"
        headers = {"User-Agent": "K-CLI/0.2.0 ModelManager"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(download_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to download from HF ({download_url}): HTTP {resp.status}")

            total_bytes = int(resp.headers.get("content-length", 0))
            downloaded_bytes = 0

            temp_dest = dest.with_suffix(".tmp")
            with open(temp_dest, "wb") as f_out:
                while True:
                    chunk = resp.read(1024 * 1024 * 4) # 4MB chunks
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_bytes)

            temp_dest.replace(dest)

        return dest

    # --------------------------------------------------------------------------
    # 5. Modelfile Generation & Ollama Deployment
    # --------------------------------------------------------------------------

    def generate_modelfile(
        self,
        gguf_path: Union[str, Path],
        model_name: str = "bankai-7b",
        system_prompt: Optional[str] = None,
        template: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        repeat_penalty: Optional[float] = None,
    ) -> str:
        """
        Generates standard Modelfile content for Ollama model creation.
        """
        spec = self.resolve_model_spec(model_name)
        gguf_abs = Path(gguf_path).resolve()

        sys_prompt = system_prompt or spec.get("system_prompt", "")
        tmpl = template or DEFAULT_CHATML_TEMPLATE
        temp = temperature if temperature is not None else spec.get("temperature", 0.2)
        tp = top_p if top_p is not None else spec.get("top_p", 0.95)
        rp = repeat_penalty if repeat_penalty is not None else spec.get("repeat_penalty", 1.1)
        stop_tokens = spec.get("stop_tokens", ["<|im_start|>", "<|im_end|>"])

        lines = [
            f"FROM {gguf_abs}",
            "",
            'TEMPLATE """' + tmpl.strip() + '"""',
            "",
        ]

        for st in stop_tokens:
            lines.append(f'PARAMETER stop "{st}"')

        lines.append(f"PARAMETER temperature {temp}")
        lines.append(f"PARAMETER top_p {tp}")
        lines.append(f"PARAMETER repeat_penalty {rp}")
        lines.append("")
        lines.append(f'SYSTEM """{sys_prompt.strip()}"""')
        lines.append("")

        return "\n".join(lines)

    def write_modelfile(
        self,
        gguf_path: Union[str, Path],
        output_modelfile_path: Optional[Union[str, Path]] = None,
        model_name: str = "bankai-7b",
        system_prompt: Optional[str] = None,
    ) -> Path:
        """
        Writes generated Modelfile to disk and returns path.
        """
        content = self.generate_modelfile(
            gguf_path=gguf_path,
            model_name=model_name,
            system_prompt=system_prompt,
        )

        if output_modelfile_path is not None:
            out_p = Path(output_modelfile_path).resolve()
        else:
            clean_name = model_name.replace(":", "-").replace("/", "-")
            out_p = self.models_dir / f"Modelfile.{clean_name}"

        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(content, encoding="utf-8")
        return out_p

    def create_ollama_model(
        self,
        model_tag: str,
        modelfile_path: Union[str, Path],
    ) -> Tuple[bool, str]:
        """
        Registers model with local Ollama service using 'ollama create' CLI or API.
        """
        mf_path = Path(modelfile_path).resolve()
        if not mf_path.exists():
            return False, f"Modelfile not found at '{mf_path}'."

        if self.mock_mode:
            if model_tag not in self._mock_ollama_models:
                self._mock_ollama_models.append(model_tag)
            return True, f"Mock: Successfully created Ollama model '{model_tag}' from {mf_path.name}"

        # Strategy 1: Ollama CLI (`ollama create <tag> -f <modelfile>`)
        ollama_bin = shutil.which("ollama") or "/home/k/bin/ollama"
        if os.path.exists(ollama_bin) and os.access(ollama_bin, os.X_OK):
            try:
                cmd = [ollama_bin, "create", model_tag, "-f", str(mf_path)]
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if res.returncode == 0:
                    return True, f"Successfully created Ollama model '{model_tag}' via CLI."
                else:
                    logger.debug(f"Ollama CLI create failed (code {res.returncode}): {res.stderr}")
            except Exception as e_cli:
                logger.debug(f"Ollama CLI invocation error: {e_cli}")

        # Strategy 2: Ollama HTTP REST API (`/api/create`)
        try:
            create_url = f"{self.ollama_url}/api/create"
            modelfile_content = mf_path.read_text(encoding="utf-8")
            payload = {
                "name": model_tag,
                "modelfile": modelfile_content,
                "stream": False,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                create_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                if resp.status == 200:
                    return True, f"Successfully created Ollama model '{model_tag}' via API."
                return False, f"Ollama API returned HTTP {resp.status} during model creation."
        except Exception as e_api:
            return False, f"Failed to create Ollama model '{model_tag}': {e_api}"

    # --------------------------------------------------------------------------
    # 6. High-Level Automated Model Pull & Bootstrapping Pipeline
    # --------------------------------------------------------------------------

    def pull_model(
        self,
        model_identifier: str = "bankai-7b",
        ollama_tag: Optional[str] = None,
        hf_repo: Optional[str] = None,
        force: bool = False,
        verify_sha: bool = True,
        create_in_ollama: bool = True,
        expected_sha256: Optional[str] = None,
        quant: str = "q4_k_m",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ModelPullResult:
        """
        Executes end-to-end model synchronization:
        1. Resolves Hugging Face repo & target model spec.
        2. Checks local cache or downloads GGUF weights directly from Hugging Face Hub.
        3. Computes and verifies SHA256 integrity against expected or remote LFS hash.
        4. Generates Modelfile and registers the model in Ollama.
        """
        spec = self.resolve_model_spec(model_identifier)
        repo_id = hf_repo or spec.get("repo_id", f"krishivjoshi/{model_identifier}")
        tag = ollama_tag or spec.get("ollama_tag", model_identifier)

        # Check local cache first
        local_gguf = self.find_local_gguf(model_identifier) if not force else None
        downloaded = False

        if local_gguf and local_gguf.exists() and not force:
            gguf_path = local_gguf
            logger.info(f"Using cached GGUF artifact: {gguf_path}")
        else:
            try:
                gguf_path = self.download_from_hf(
                    repo_id=repo_id,
                    quant_preference=quant,
                    progress_callback=progress_callback,
                )
                downloaded = True
            except Exception as dl_err:
                return ModelPullResult(
                    success=False,
                    model_name=model_identifier,
                    ollama_tag=tag,
                    message=f"Failed to download '{repo_id}' from Hugging Face Hub: {dl_err}",
                    details={"error": str(dl_err)},
                )

        # Compute SHA256 hash
        computed_sha = None
        sha_verified = False
        try:
            computed_sha = self.compute_sha256(gguf_path)
            target_sha = expected_sha256
            if not target_sha:
                # Attempt to query HF metadata for LFS hash
                meta = self.fetch_hf_metadata(repo_id)
                target_sha = meta.get("lfs_sha256", {}).get(gguf_path.name)

            if target_sha:
                sha_verified = (computed_sha.lower() == target_sha.strip().lower())
                if verify_sha and not sha_verified:
                    return ModelPullResult(
                        success=False,
                        model_name=model_identifier,
                        ollama_tag=tag,
                        gguf_path=gguf_path,
                        sha256=computed_sha,
                        sha256_verified=False,
                        message=(
                            f"SHA256 integrity mismatch for '{gguf_path.name}'. "
                            f"Expected {target_sha}, got {computed_sha}"
                        ),
                        details={"expected_sha": target_sha, "computed_sha": computed_sha},
                    )
            else:
                if verify_sha and not self.mock_mode:
                    return ModelPullResult(
                        success=False,
                        model_name=model_identifier,
                        ollama_tag=tag,
                        gguf_path=gguf_path,
                        sha256=computed_sha,
                        sha256_verified=False,
                        message=(
                            f"No trusted SHA256 reference is available for '{gguf_path.name}'. "
                            "Refusing to install an unverified model."
                        ),
                        details={"computed_sha": computed_sha},
                    )
                sha_verified = self.mock_mode
        except Exception as sha_err:
            logger.warning(f"SHA256 verification warning: {sha_err}")

        # Generate Modelfile
        modelfile_path = self.write_modelfile(
            gguf_path=gguf_path,
            model_name=model_identifier,
        )

        # Ollama Health & Model Registration
        ollama_healthy = self.is_ollama_available()
        ollama_created = False
        create_msg = ""

        if create_in_ollama:
            if ollama_healthy:
                ollama_created, create_msg = self.create_ollama_model(
                    model_tag=tag,
                    modelfile_path=modelfile_path,
                )
            else:
                create_msg = f"Ollama daemon not reachable at {self.ollama_url}. Modelfile ready at {modelfile_path}."

        success = (gguf_path.exists() and (not create_in_ollama or ollama_created or not ollama_healthy))

        return ModelPullResult(
            success=success,
            model_name=model_identifier,
            ollama_tag=tag,
            gguf_path=gguf_path,
            modelfile_path=modelfile_path,
            sha256=computed_sha,
            sha256_verified=sha_verified,
            ollama_created=ollama_created,
            ollama_healthy=ollama_healthy,
            message=create_msg or f"Model '{model_identifier}' successfully staged at {gguf_path}",
            details={
                "downloaded": downloaded,
                "repo_id": repo_id,
                "quant": quant,
            },
        )

    def init_environment(
        self,
        default_model: str = "bankai-7b",
        sync_model: bool = True,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Scaffolds the full K-CLI local directory hierarchy and provisions the default Bankai model.
        """
        # 1. Scaffolding directory tree
        subdirs = ["docs", "repos", "logs", "khoj_index", "parsers", "models"]
        created_dirs = []
        for sd in subdirs:
            d = DEFAULT_KCLI_DIR / sd
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d))

        # 2. Check Ollama Health
        ollama_status = self.check_ollama_health()

        # 3. Pull / Sync default Bankai model
        pull_res: Optional[ModelPullResult] = None
        if sync_model:
            pull_res = self.pull_model(
                model_identifier=default_model,
                force=force,
                verify_sha=True,
                create_in_ollama=True,
            )

        return {
            "kcli_home": str(DEFAULT_KCLI_DIR),
            "directories": created_dirs,
            "ollama": ollama_status,
            "model_pull": pull_res.to_dict() if pull_res else None,
            "ready": True if (not sync_model or (pull_res and pull_res.success)) else False,
        }

    def pull_ollama_tag(
        self,
        model_tag: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Pulls a model tag directly from Ollama registry (e.g. qwen2.5-coder:7b)."""
        if self.mock_mode:
            if model_tag not in self._mock_ollama_models:
                self._mock_ollama_models.append(model_tag)
            if progress_callback:
                progress_callback(f"Mock: Pulled {model_tag} 100%")
            return True, f"Mock: Pulled {model_tag} successfully."

        # Check Ollama CLI
        ollama_bin = shutil.which("ollama") or "/home/k/bin/ollama"
        if os.path.exists(ollama_bin) and os.access(ollama_bin, os.X_OK):
            try:
                proc = subprocess.Popen(
                    [ollama_bin, "pull", model_tag],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                if proc.stdout:
                    for line in proc.stdout:
                        if progress_callback and line.strip():
                            progress_callback(line.strip())
                proc.wait(timeout=600)
                if proc.returncode == 0:
                    return True, f"Successfully pulled {model_tag} into Ollama."
            except Exception as e:
                logger.debug(f"CLI pull error: {e}")

        # Fallback to Ollama HTTP API /api/pull
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/pull",
                data=json.dumps({"name": model_tag, "stream": False}).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "K-CLI"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600.0) as resp:
                if resp.status == 200:
                    return True, f"Successfully pulled {model_tag} via Ollama API."
        except Exception as e:
            return False, f"Failed to pull {model_tag}: {e}"

        return False, f"Could not pull {model_tag}"


# ------------------------------------------------------------------------------
# Curated Local Coding Models Catalog with In-Depth Pros & Cons
# ------------------------------------------------------------------------------
LOCAL_CODING_MODELS: List[Dict[str, Any]] = [
    {
        "id": "qwen2.5-coder:7b",
        "name": "Qwen 2.5 Coder 7B",
        "size": "4.7 GB",
        "ram": "8 GB RAM / 6 GB VRAM",
        "context": "32K / 128K",
        "speed": "~65 tok/s (GPU)",
        "pros": [
            "🏆 #1 Open-Weight Coding Model in 7B class (HumanEval 88.4%)",
            "✨ Flawless Multi-File AST & Surgical SEARCH/REPLACE reasoning",
            "⚡ Fast inference speed with low memory footprint",
            "🌐 Supports 92+ programming languages including Python, Rust, C++, Go",
        ],
        "cons": [
            "⚠️ Needs 6GB+ VRAM for full GPU offload",
            "⚠️ May struggle with ultra-large monolithic repos without AST slicing",
        ],
        "hf_repo": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        "ollama_tag": "qwen2.5-coder:7b",
    },
    {
        "id": "qwen2.5-coder:14b",
        "name": "Qwen 2.5 Coder 14B",
        "size": "9.0 GB",
        "ram": "16 GB RAM / 10 GB VRAM",
        "context": "32K / 128K",
        "speed": "~45 tok/s (GPU)",
        "pros": [
            "🧠 Rivals proprietary GPT-4o-mini and Claude 3.5 Haiku on coding evals",
            "🏗️ Outstanding architectural design and refactoring synthesis",
            "🛡️ High precision on type safety, unit tests, and edge cases",
        ],
        "cons": [
            "⚠️ Requires 10GB+ VRAM (or 16GB Mac Unified Memory)",
            "⚠️ Slower execution on pure CPU without AVX-512",
        ],
        "hf_repo": "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
        "ollama_tag": "qwen2.5-coder:14b",
    },
    {
        "id": "qwen2.5-coder:1.5b",
        "name": "Qwen 2.5 Coder 1.5B (Ultra-Light)",
        "size": "1.0 GB",
        "ram": "2 GB RAM / 1 GB VRAM",
        "context": "32K",
        "speed": "~140 tok/s (GPU) / ~45 tok/s (CPU)",
        "pros": [
            "🚀 Ultra-fast generation (<10ms time-to-first-token)",
            "💾 Runs on any laptop, Raspberry Pi, or low-spec VM",
            "💰 100% Free, zero CPU throttle, ideal for autocomplete & inline diffs",
        ],
        "cons": [
            "⚠️ Limited reasoning depth for complex concurrency & race conditions",
            "⚠️ Lower context capacity for multi-file refactors",
        ],
        "hf_repo": "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "ollama_tag": "qwen2.5-coder:1.5b",
    },
    {
        "id": "deepseek-r1:7b",
        "name": "DeepSeek-R1 Distill Qwen 7B (Reasoning)",
        "size": "4.7 GB",
        "ram": "8 GB RAM / 6 GB VRAM",
        "context": "32K / 64K",
        "speed": "~50 tok/s (GPU)",
        "pros": [
            "🧠 Deep Chain-of-Thought reasoning inside visible <think> blocks",
            "🔬 Excellent at finding subtle bugs, race conditions, and cryptographic flaws",
            "⚖️ Self-corrects mistakes before emitting final verified code",
        ],
        "cons": [
            "⚠️ Slower total task time due to generating extensive thinking tokens",
            "⚠️ Can overthink trivial tasks like docstrings or variable renames",
        ],
        "hf_repo": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        "ollama_tag": "deepseek-r1:7b",
    },
    {
        "id": "deepseek-r1:14b",
        "name": "DeepSeek-R1 Distill Qwen 14B (Advanced Reasoning)",
        "size": "9.0 GB",
        "ram": "16 GB RAM / 10 GB VRAM",
        "context": "32K / 64K",
        "speed": "~35 tok/s (GPU)",
        "pros": [
            "🎓 Frontier-grade mathematical and algorithmic problem solving",
            "🛡️ Compiler-level verification and multi-step theorem proving",
            "🏆 Top-performing 14B model for complex full-stack architectures",
        ],
        "cons": [
            "⚠️ High VRAM requirement (10GB+)",
            "⚠️ Extended latency per response",
        ],
        "hf_repo": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B-GGUF",
        "ollama_tag": "deepseek-r1:14b",
    },
    {
        "id": "llama3.3:70b",
        "name": "Meta Llama 3.3 70B (Flagship)",
        "size": "42 GB (Q4_K_M)",
        "ram": "48 GB RAM / 40 GB VRAM",
        "context": "128K",
        "speed": "~25 tok/s (Multi-GPU)",
        "pros": [
            "👑 World-class general knowledge and massive 128k context window",
            "📚 Flawless technical documentation, architectural synthesis, and RFC generation",
            "⚡ Matches or exceeds GPT-4-0613 across software engineering evals",
        ],
        "cons": [
            "⚠️ Massive hardware requirements (requires dual RTX 3090/4090 or Mac Studio)",
            "⚠️ Unusable on low-spec single-GPU machines",
        ],
        "hf_repo": "meta-llama/Llama-3.3-70B-Instruct-GGUF",
        "ollama_tag": "llama3.3:70b",
    },
    {
        "id": "phi4:14b",
        "name": "Microsoft Phi-4 14B",
        "size": "9.1 GB",
        "ram": "16 GB RAM / 10 GB VRAM",
        "context": "16K",
        "speed": "~40 tok/s (GPU)",
        "pros": [
            "🔬 State-of-the-art synthetic data training by Microsoft Research",
            "📐 Dense algorithmic reasoning per parameter count",
        ],
        "cons": [
            "⚠️ Smaller 16k context window compared to Qwen 2.5",
            "⚠️ Strict system prompt sensitivity",
        ],
        "hf_repo": "microsoft/phi-4-gguf",
        "ollama_tag": "phi4:14b",
    },
    {
        "id": "starcoder2:15b",
        "name": "BigCode StarCoder2 15B",
        "size": "9.5 GB",
        "ram": "16 GB RAM / 10 GB VRAM",
        "context": "16K",
        "speed": "~40 tok/s (GPU)",
        "pros": [
            "📜 Fully open, permissively licensed training data (The Stack v2)",
            "🌐 600+ programming language coverage",
        ],
        "cons": [
            "⚠️ Weaker natural language chat instruction following",
        ],
        "hf_repo": "bigcode/starcoder2-15b-gguf",
        "ollama_tag": "starcoder2:15b",
    },
]

BANKAI_CUSTOM_MODELS: List[Dict[str, Any]] = [
    {
        "id": "bankai-7b",
        "name": "Bankai-7B GGUF (Flagship Code & AST Healer)",
        "repo_id": "krishivjoshi/bankai-7b",
        "default_filename": "bankai-7b.gguf",
        "size": "4.7 GB",
        "ram": "1.0-4.0 GB RAM Budget",
        "ollama_tag": "bankai:7b",
        "description": "Custom fine-tuned compiler-grounded model with AST patch synthesis, test generation, and <think> chain-of-thought.",
    },
    {
        "id": "bankai-10b",
        "name": "Bankai-10B GGUF (Multi-File Architecture)",
        "repo_id": "krishivjoshi/bankai-10b",
        "default_filename": "bankai-10b.gguf",
        "size": "6.5 GB",
        "ram": "6.0 GB RAM Budget",
        "ollama_tag": "bankai:10b",
        "description": "High-capacity architecture model for 10+ file scaffolding, 3-way merge conflict resolution, and PR reviews.",
    },
    {
        "id": "bankai-3b",
        "name": "Bankai-3B GGUF (Sovereign 1.0GB RAM Edition)",
        "repo_id": "krishivjoshi/bankai-3b",
        "default_filename": "bankai-3b.gguf",
        "size": "2.2 GB",
        "ram": "1.0 GB RAM Budget",
        "ollama_tag": "bankai:3b",
        "description": "Engineered strictly for memory-constrained environments, edge devices, and 100% offline air-gapped development.",
    },
    {
        "id": "bankai-1.5b",
        "name": "Bankai-1.5B GGUF (Fast Background Daemon)",
        "repo_id": "krishivjoshi/bankai-1.5b",
        "default_filename": "bankai-1.5b.gguf",
        "size": "1.1 GB",
        "ram": "512 MB - 1.0 GB RAM",
        "ollama_tag": "bankai:1.5b",
        "description": "Ultra-lightweight background model for Ghost crash interception, conventional commit generation, and real-time linting.",
    },
]


def list_local_coding_models() -> List[Dict[str, Any]]:
    """Returns the list of curated local models with pros/cons."""
    return list(LOCAL_CODING_MODELS)


def list_bankai_models() -> List[Dict[str, Any]]:
    """Returns the list of custom Bankai models on Hugging Face."""
    return list(BANKAI_CUSTOM_MODELS)

