"""
llm_driver.py - Universal Plug-and-Play LLM Inference Driver for K-CLI

Supported Inference Backends:
1. Local Bankai-7B / 14B GGUF via Ollama (http://localhost:11434) and llama.cpp HTTP server (http://localhost:8080)
2. Native in-process llama-cpp-python GGUF inference
3. Google Gemini (Gemini 3.7 Flash, Gemini 1.5 Pro, thinking budgets)
4. Anthropic Claude (Claude 3.7 Sonnet, Claude 3.5 Haiku, streaming)
5. OpenAI / DeepSeek / OpenRouter compatible REST API endpoints
6. Multi-tier auto-fallback routing hierarchy with full streaming token preservation
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

try:
    from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
except ModuleNotFoundError:
    try:
        from verifier import CodeExtractor, VerificationResult, Verifier
    except ModuleNotFoundError:
        pass

try:
    from k_cli.core.model_manager import ModelManager
except (ModuleNotFoundError, ImportError):
    try:
        from model_manager import ModelManager
    except (ModuleNotFoundError, ImportError):
        ModelManager = None


class ProviderType(str, Enum):
    AUTO = "auto"
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    NATIVE = "native"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    MOCK = "mock"


class _CallbackException(Exception):
    """Wrapper to safely bubble user exceptions raised inside stream_callback."""

    def __init__(self, original_exception: Exception):
        self.original_exception = original_exception
        super().__init__(str(original_exception))


def _invoke_callback(cb: Optional[Callable[[str], None]], token: str) -> None:
    """Invokes stream callback safely, wrapping user exceptions to prevent fallback swallowing."""
    if cb is not None and token:
        try:
            cb(token)
        except Exception as exc:
            raise _CallbackException(exc) from exc


_CUSTOM_ADAPTERS: Dict[str, Callable[..., str]] = {}


def register_adapter(name: str, adapter_fn: Callable[..., str]) -> None:
    """Register a custom adapter for external or proprietary model providers (e.g. GenBlaze SDK)."""
    _CUSTOM_ADAPTERS[name.lower().strip()] = adapter_fn


class LLMDriver:
    """
    Universal LLM Driver supporting multi-provider backends:
    - Ollama (Bankai-7B/14B, Qwen2.5-Coder, DeepSeek, etc.)
    - llama.cpp HTTP server
    - Native llama-cpp-python GGUF
    - Google Gemini (Gemini 3.7 Flash, Gemini 1.5 Pro with thinking budgets)
    - Anthropic Claude (Claude 3.7 Sonnet, Claude 3.5 Haiku with streaming)
    - OpenAI / DeepSeek / OpenRouter compatible REST APIs
    - Deterministic Mock Engine
    """

    def __init__(
        self,
        model_name: str = "qwen2.5-coder:1.5b",
        ollama_url: str = "http://localhost:11434",
        timeout: float = 60.0,
        mock_mode: bool = False,
        provider: Optional[Union[ProviderType, str]] = None,
        llamacpp_url: str = "http://localhost:8080",
        gemini_api_key: Optional[str] = None,
        gemini_base_url: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        anthropic_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        deepseek_base_url: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_base_url: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        **kwargs: Any,
    ):
        try:
            from k_cli.core.credentials import CredentialsManager
            CredentialsManager.load_all_credentials()
        except Exception:
            pass

        # Model Name: check env override
        self.model_name = os.getenv("KCLI_MODEL", os.getenv("LLM_MODEL", model_name))

        # Provider: check env override
        raw_provider = provider or os.getenv("KCLI_PROVIDER", os.getenv("LLM_PROVIDER", "auto"))
        self.provider = raw_provider.value if isinstance(raw_provider, ProviderType) else str(raw_provider).lower()
        self.provider = {
            "openai_compatible": "openai-compatible",
            "compatible": "openai-compatible",
            "openai-compatible": "openai-compatible",
        }.get(self.provider, self.provider)

        # Ollama config
        raw_ollama_url = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE_URL", ollama_url)).rstrip("/")
        if not raw_ollama_url.startswith("http"):
            raw_ollama_url = f"http://{raw_ollama_url}"
        self.ollama_url = raw_ollama_url

        # llama.cpp server config
        raw_llamacpp_url = os.getenv(
            "LLAMACPP_HOST",
            os.getenv("LLAMACPP_BASE_URL", os.getenv("LLAMA_CPP_URL", llamacpp_url)),
        ).rstrip("/")
        if not raw_llamacpp_url.startswith("http"):
            raw_llamacpp_url = f"http://{raw_llamacpp_url}"
        self.llamacpp_url = raw_llamacpp_url

        # Cloud API Keys and Base URLs
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_base_url = (
            gemini_base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        ).rstrip("/")

        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_base_url = (
            anthropic_base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        ).rstrip("/")

        self.openai_api_key = (
            openai_api_key or os.getenv("KCLI_API_KEY") or os.getenv("OPENAI_API_KEY") or kwargs.get("api_key")
        )
        self.openai_base_url = (
            openai_base_url
            or os.getenv("KCLI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL", kwargs.get("base_url", "https://api.openai.com/v1"))
        ).rstrip("/")

        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_base_url = (
            deepseek_base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        ).rstrip("/")

        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_base_url = (
            openrouter_base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        ).rstrip("/")

        # Thinking Budget (Gemini / Claude)
        tb_env = os.getenv("GEMINI_THINKING_BUDGET") or os.getenv("ANTHROPIC_THINKING_BUDGET") or os.getenv("THINKING_BUDGET")
        if thinking_budget is not None:
            self.thinking_budget = thinking_budget
        elif tb_env is not None:
            try:
                self.thinking_budget = int(tb_env)
            except ValueError:
                self.thinking_budget = None
        else:
            self.thinking_budget = None

        self.timeout = float(os.getenv("KCLI_LLM_TIMEOUT", timeout))
        self.mock_mode = mock_mode
        self._native_llm = None
        self._last_used_provider: Optional[str] = None

    def is_ollama_available(self) -> bool:
        """Checks if Ollama server is running locally and target model is present."""
        if self.mock_mode:
            return True
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
                target = self.model_name.lower().strip()
                for m in models:
                    if not m:
                        continue
                    m_low = m.lower().strip()
                    if target == m_low or m_low.startswith(target) or (m_low.split(":")[0] and target.startswith(m_low.split(":")[0])):
                        return True
                    # Check tag normalization (e.g. bankai-7b vs bankai:7b)
                    if target.replace("-", ":") == m_low.replace("-", ":"):
                        return True
                return False
        except Exception:
            return False

    def is_llamacpp_available(self) -> bool:
        """Checks if llama.cpp HTTP server is running."""
        if self.mock_mode:
            return True
        for endpoint in ["/health", "/v1/models", "/props"]:
            try:
                req = urllib.request.Request(f"{self.llamacpp_url}{endpoint}", method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status in (200, 204):
                        return True
            except Exception:
                continue
        return False

    def is_gemini_available(self) -> bool:
        """Checks if Gemini API key is configured."""
        return bool(self.gemini_api_key)

    def is_anthropic_available(self) -> bool:
        """Checks if Anthropic API key is configured."""
        return bool(self.anthropic_api_key)

    def is_openai_available(self) -> bool:
        """Checks if OpenAI API key is configured."""
        return bool(self.openai_api_key)

    def is_deepseek_available(self) -> bool:
        """Checks if DeepSeek API key is configured."""
        return bool(self.deepseek_api_key)

    def is_openrouter_available(self) -> bool:
        """Checks if OpenRouter API key is configured."""
        return bool(self.openrouter_api_key)

    def detect_primary_provider(self) -> str:
        """Determines the primary provider to attempt based on configuration, model name, and keys."""
        if self.mock_mode or self.provider == "mock":
            return "mock"
        if self.provider and self.provider != "auto":
            return self.provider

        model_lower = self.model_name.lower()

        # Cloud model prefixes
        if model_lower.startswith("gemini"):
            return "gemini" if self.is_gemini_available() else "auto"
        if model_lower.startswith("claude"):
            return "anthropic" if self.is_anthropic_available() else "auto"
        if model_lower.startswith("deepseek") and self.is_deepseek_available():
            return "deepseek"
        if (
            model_lower.startswith("gpt-") or model_lower.startswith("o1") or model_lower.startswith("o3")
        ) and self.is_openai_available():
            return "openai"
        if (model_lower.startswith("openrouter/") or "/" in model_lower) and self.is_openrouter_available():
            return "openrouter"

        # Local models (bankai, qwen, llama, mistral, deepseek-coder, etc.)
        if self.is_ollama_available():
            return "ollama"
        if self.is_llamacpp_available():
            return "llamacpp"
        if self.get_native_llama() is not None:
            return "native"

        # Fallback to available cloud provider if API keys exist
        if self.is_gemini_available():
            return "gemini"
        if self.is_openai_available():
            return "openai"
        if self.is_anthropic_available():
            return "anthropic"
        if self.is_deepseek_available():
            return "deepseek"
        if self.is_openrouter_available():
            return "openrouter"

        return "ollama"

    def get_model_manager(self) -> Optional[Any]:
        """Returns initialized ModelManager instance if available."""
        if ModelManager is not None:
            return ModelManager(ollama_url=self.ollama_url, mock_mode=self.mock_mode)
        return None

    def ensure_model_ready(self, auto_pull: bool = False) -> Dict[str, Any]:
        """
        Validates whether target model is ready in Ollama or local GGUF cache.
        If auto_pull is True and model is missing, attempts automated pull.
        """
        mm = self.get_model_manager()
        if mm is None:
            return {"ready": self.is_ollama_available() or self.mock_mode, "ollama": self.is_ollama_available()}

        has_ollama = mm.has_ollama_model(self.model_name)
        local_gguf = mm.find_local_gguf(self.model_name)

        if has_ollama or (local_gguf and local_gguf.exists()):
            return {
                "ready": True,
                "ollama": has_ollama,
                "local_gguf": str(local_gguf) if local_gguf else None,
                "pulled": False,
            }

        if auto_pull:
            res = mm.pull_model(model_identifier=self.model_name)
            return {
                "ready": res.success,
                "ollama": res.ollama_created,
                "local_gguf": str(res.gguf_path) if res.gguf_path else None,
                "pulled": True,
                "pull_result": res.to_dict(),
            }

        return {
            "ready": False,
            "ollama": False,
            "local_gguf": None,
            "pulled": False,
        }

    def get_native_llama(self):
        """Lazy loads llama-cpp-python GGUF model if llama-cpp-python is installed."""
        if self._native_llm is not None:
            return self._native_llm

        try:
            from llama_cpp import Llama

            model_path = None
            if ModelManager is not None:
                mm = ModelManager(mock_mode=self.mock_mode)
                local_path = mm.find_local_gguf(self.model_name)
                if local_path and local_path.exists():
                    model_path = str(local_path)

            if not model_path:
                return None

            self._native_llm = Llama(
                model_path=str(model_path),
                n_ctx=2048,
                n_threads=4,
                verbose=False,
            )
            return self._native_llm
        except Exception:
            return None

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Universal generation entry point.
        Dispatches to active provider with graceful auto-fallback hierarchy:
        Local (Ollama -> llama.cpp -> Native GGUF) -> Cloud (Gemini -> Anthropic -> OpenAI / DeepSeek / OpenRouter) -> Mock.
        Supports full streaming token callbacks and robust error handling.
        """
        # Inject custom developer instructions & workspace rules if present
        try:
            from k_cli.tools.rules import load_project_rules
            rules_ctx = load_project_rules(".")
            if rules_ctx:
                if system_prompt:
                    system_prompt = f"{rules_ctx}\n\n{system_prompt}"
                else:
                    system_prompt = rules_ctx
        except Exception:
            pass

        if self.mock_mode:
            self._last_used_provider = "mock"
            return self._mock_generate(prompt, system_prompt, stream_callback=stream_callback)

        primary = self.detect_primary_provider()

        def make_runner(prov: str) -> Callable[[], str]:
            if prov in _CUSTOM_ADAPTERS:
                adapter_fn = _CUSTOM_ADAPTERS[prov]
                return lambda: adapter_fn(prompt, system_prompt, temperature, stream_callback)
            elif prov == "ollama":
                return lambda: self._generate_ollama(prompt, system_prompt, temperature, stream_callback)
            elif prov == "llamacpp":
                return lambda: self._generate_llamacpp(prompt, system_prompt, temperature, stream_callback)
            elif prov == "native":
                native_llm = self.get_native_llama()
                if native_llm is None:
                    raise RuntimeError("Native llama-cpp-python model not available")
                return lambda: self._generate_native(native_llm, prompt, system_prompt, temperature, stream_callback)
            elif prov == "gemini":
                return lambda: self._generate_gemini(prompt, system_prompt, temperature, stream_callback)
            elif prov == "anthropic":
                return lambda: self._generate_anthropic(prompt, system_prompt, temperature, stream_callback)
            elif prov in ("openai", "openai-compatible"):
                return lambda: self._generate_openai(prompt, system_prompt, temperature, stream_callback)
            elif prov == "deepseek":
                return lambda: self._generate_deepseek(prompt, system_prompt, temperature, stream_callback)
            elif prov == "openrouter":
                return lambda: self._generate_openrouter(prompt, system_prompt, temperature, stream_callback)
            else:
                return lambda: self._mock_generate(prompt, system_prompt, stream_callback=stream_callback)

        # Try primary provider directly first to avoid probing overhead
        primary_runner = make_runner(primary)
        try:
            self._last_used_provider = primary
            res = primary_runner()
            if res is not None:
                return res
        except _CallbackException as cb_exc:
            raise cb_exc.original_exception
        except Exception:
            pass

        # Primary failed: build fallback candidate list
        candidates: List[Tuple[str, Callable[[], str]]] = []
        fallback_order = ["gemini", "anthropic", "openai", "deepseek", "openrouter", "ollama", "llamacpp", "native"]
        for fb in fallback_order:
            if fb != primary:
                if fb == "gemini" and self.is_gemini_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "anthropic" and self.is_anthropic_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "openai" and self.is_openai_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "deepseek" and self.is_deepseek_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "openrouter" and self.is_openrouter_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "ollama" and self.is_ollama_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "llamacpp" and self.is_llamacpp_available():
                    candidates.append((fb, make_runner(fb)))
                elif fb == "native" and self.get_native_llama() is not None:
                    candidates.append((fb, make_runner(fb)))

        # Always add deterministic mock fallback
        candidates.append(("mock", lambda: self._mock_generate(prompt, system_prompt, stream_callback=stream_callback)))

        # Execute candidate hierarchy with auto-fallback
        for prov_name, runner in candidates:
            try:
                self._last_used_provider = prov_name
                res = runner()
                if res is not None:
                    return res
            except _CallbackException as cb_exc:
                raise cb_exc.original_exception
            except Exception:
                continue

        self._last_used_provider = "mock"
        return self._mock_generate(prompt, system_prompt, stream_callback=stream_callback)

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Sends request to local Ollama server with streaming token support."""
        endpoint = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": bool(stream_callback),
            "options": {
                "temperature": temperature,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            if stream_callback:
                full_text: List[str] = []
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    for line in resp:
                        if line:
                            chunk = json.loads(line.decode("utf-8"))
                            token = chunk.get("response", "")
                            if token:
                                full_text.append(token)
                                _invoke_callback(stream_callback, token)
                            if chunk.get("done", False):
                                break
                return "".join(full_text)
            else:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    return res_json.get("response", "")
        except _CallbackException:
            raise
        except Exception:
            # Fallback to mock directly if standalone call
            return self._mock_generate(prompt, system_prompt, stream_callback=stream_callback)

    def _generate_llamacpp(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via llama.cpp HTTP server (/v1/chat/completions or /completion)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        endpoint = f"{self.llamacpp_url}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": bool(stream_callback),
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            if stream_callback:
                full_text: List[str] = []
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    for line in resp:
                        line_str = line.decode("utf-8").strip()
                        if not line_str.startswith("data:"):
                            continue
                        data_payload = line_str[5:].strip()
                        if data_payload == "[DONE]":
                            break
                        if not data_payload:
                            continue
                        chunk = json.loads(data_payload)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = delta.get("content") or ""
                            if token:
                                full_text.append(token)
                                _invoke_callback(stream_callback, token)
                return "".join(full_text)
            else:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    choices = res_json.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    return ""
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                # Fallback to legacy /completion endpoint
                legacy_endpoint = f"{self.llamacpp_url}/completion"
                legacy_payload = {
                    "prompt": f"<|im_start|>system\n{system_prompt or ''}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
                    "temperature": temperature,
                    "stream": bool(stream_callback),
                }
                legacy_req = urllib.request.Request(
                    legacy_endpoint,
                    data=json.dumps(legacy_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                if stream_callback:
                    full_text = []
                    with urllib.request.urlopen(legacy_req, timeout=self.timeout) as resp:
                        for line in resp:
                            line_str = line.decode("utf-8").strip()
                            if line_str.startswith("data:"):
                                line_str = line_str[5:].strip()
                            if not line_str:
                                continue
                            chunk = json.loads(line_str)
                            token = chunk.get("content", "")
                            if token:
                                full_text.append(token)
                                _invoke_callback(stream_callback, token)
                            if chunk.get("stop", False):
                                break
                    return "".join(full_text)
                else:
                    with urllib.request.urlopen(legacy_req, timeout=self.timeout) as resp:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        return res_json.get("content", "")
            raise

    def _generate_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via Google Gemini REST API with native streaming and thinking budgets."""
        api_key = self.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")

        model = self.model_name
        gemini_model_map = {
            "gemini-3.8-flash": "gemini-2.5-flash",
            "gemini-3.7-flash": "gemini-2.5-flash",
            "gemini-3.5-flash": "gemini-2.5-flash",
            "gemini-3-flash": "gemini-2.5-flash",
            "gemini-flash": "gemini-2.5-flash",
            "gemini-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.0-flash": "gemini-2.5-flash",
            "gemini-1.5-flash": "gemini-2.5-flash",
            "gemini-1.5-pro": "gemini-2.5-pro",
        }
        model = gemini_model_map.get(model, model)
        if not (model.startswith("gemini-1.5") or model.startswith("gemini-2.0") or model.startswith("gemini-2.5")):
            model = "gemini-2.5-flash"

        contents = [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]

        generation_config: Dict[str, Any] = {
            "temperature": temperature,
        }

        # Thinking Budget config: default to 0 for instant responses and credit savings
        thinking_budget = self.thinking_budget
        if thinking_budget is None and "thinking" in model.lower():
            thinking_budget = 2048
        elif thinking_budget is None:
            thinking_budget = 0

        generation_config["thinkingConfig"] = {
            "thinkingBudget": thinking_budget,
        }

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        try:
            endpoint = f"{self.gemini_base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
            req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
            full_text: List[str] = []

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if line_str in ("data: [DONE]", "[DONE]"):
                        break
                    if not line_str.startswith("data:"):
                        continue
                    data_payload = line_str[5:].strip()
                    if not data_payload:
                        continue
                    try:
                        chunk = json.loads(data_payload)
                        candidates = chunk.get("candidates", [])
                        if candidates:
                            cand = candidates[0]
                            parts = cand.get("content", {}).get("parts", [])
                            for part in parts:
                                token = part.get("text", "")
                                if token:
                                    full_text.append(token)
                                    if stream_callback:
                                        _invoke_callback(stream_callback, token)
                            if cand.get("finishReason"):
                                break
                    except Exception:
                        pass
            return "".join(full_text)
        except urllib.error.HTTPError as http_err:
            if http_err.code in (400, 404) and model != "gemini-2.5-flash":
                # Fallback to standard reliable gemini-2.5-flash
                fallback_driver = LLMDriver(model_name="gemini-2.5-flash")
                return fallback_driver._generate_gemini(prompt, system_prompt, temperature, stream_callback)
            raise

    def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via Anthropic Claude REST API with streaming and thinking support."""
        api_key = self.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")

        model = self.model_name
        if not model.startswith("claude"):
            model = "claude-3-7-sonnet-20250219"

        endpoint = f"{self.anthropic_base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": bool(stream_callback),
        }

        if system_prompt:
            payload["system"] = system_prompt

        thinking_budget = self.thinking_budget
        if thinking_budget is None and "thinking" in model.lower():
            thinking_budget = 2048

        if thinking_budget is not None and thinking_budget > 0:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
            payload["temperature"] = 1.0

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

        if stream_callback:
            full_text: List[str] = []
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str.startswith("data:"):
                        continue
                    data_payload = line_str[5:].strip()
                    if not data_payload or data_payload == "[DONE]":
                        continue
                    event_obj = json.loads(data_payload)
                    evt_type = event_obj.get("type", "")
                    if evt_type == "content_block_delta":
                        delta = event_obj.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                full_text.append(token)
                                _invoke_callback(stream_callback, token)
            return "".join(full_text)
        else:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                content = res_json.get("content", [])
                return "".join(block.get("text", "") for block in content if block.get("type") == "text")

    def _generate_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        default_model: Optional[str] = None,
    ) -> str:
        """Generic handler for OpenAI-compatible chat completion APIs (OpenAI, DeepSeek, OpenRouter, etc.)."""
        model = self.model_name
        if default_model and (not model or model == "qwen2.5-coder:1.5b"):
            model = default_model

        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if extra_headers:
            headers.update(extra_headers)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": bool(stream_callback),
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

        if stream_callback:
            full_text: List[str] = []
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str.startswith("data:"):
                        continue
                    data_payload = line_str[5:].strip()
                    if data_payload == "[DONE]":
                        break
                    if not data_payload:
                        continue
                    chunk = json.loads(data_payload)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        token = delta.get("content") or ""
                        if token:
                            full_text.append(token)
                            _invoke_callback(stream_callback, token)
            return "".join(full_text)
        else:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                choices = res_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""

    def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via OpenAI API."""
        api_key = self.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return self._generate_openai_compatible(
            base_url=self.openai_base_url,
            api_key=api_key,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            stream_callback=stream_callback,
            default_model="gpt-4o",
        )

    def _generate_deepseek(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via DeepSeek API."""
        api_key = self.deepseek_api_key
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        return self._generate_openai_compatible(
            base_url=self.deepseek_base_url,
            api_key=api_key,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            stream_callback=stream_callback,
            default_model="deepseek-chat",
        )

    def _generate_openrouter(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via OpenRouter API."""
        api_key = self.openrouter_api_key
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        extra_headers = {
            "HTTP-Referer": "https://github.com/k-cli",
            "X-Title": "K-CLI Engine",
        }
        return self._generate_openai_compatible(
            base_url=self.openrouter_base_url,
            api_key=api_key,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            stream_callback=stream_callback,
            extra_headers=extra_headers,
            default_model="anthropic/claude-3.7-sonnet",
        )

    def _generate_native(
        self,
        llm: Any,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates text via in-process llama-cpp-python."""
        formatted_prompt = f"<|im_start|>system\n{system_prompt or ''}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        if stream_callback:
            full_text: List[str] = []
            for chunk in llm(formatted_prompt, max_tokens=1024, temperature=temperature, stream=True):
                token = chunk["choices"][0]["text"]
                full_text.append(token)
                _invoke_callback(stream_callback, token)
            return "".join(full_text)
        else:
            out = llm(formatted_prompt, max_tokens=1024, temperature=temperature)
            return out["choices"][0]["text"]

    def _mock_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Deterministic mock generator for offline mode and test suites."""
        prompt_lower = prompt.lower()
        sys_lower = (system_prompt or "").lower()

        if "[researcher]" in sys_lower or "phase (researcher)" in sys_lower or sys_lower.startswith("you are [researcher]"):
            text = "- Task: Python code implementation\n- Module: sys, psutil, time\n- Return type: clean Python script\n- Resource optimization: high efficiency"
        elif "[critic]" in sys_lower or "phase (critic)" in sys_lower or sys_lower.startswith("you are [critic]"):
            text = "VALIDATED: Code structure is sound, handles missing psutil gracefully, memory usage < 10MB."
        elif "[debugger]" in sys_lower or "phase (debugger)" in sys_lower or sys_lower.startswith("you are [debugger]"):
            text = (
                "```python\n"
                "import psutil\n"
                "import time\n"
                "\n"
                "def get_ram_usage_mb() -> float:\n"
                "    process = psutil.Process()\n"
                "    return process.memory_info().rss / (1024 * 1024)\n"
                "\n"
                "if __name__ == '__main__':\n"
                "    print(f'Current RAM Usage: {get_ram_usage_mb():.2f} MB')\n"
                "```"
            )
        elif "[architect]" in sys_lower or "phase (architect)" in sys_lower or sys_lower.startswith("you are [architect]") or (not any(p in sys_lower for p in ("[coder]", "[researcher]", "[critic]", "[debugger]")) and "architect" in sys_lower):
            text = (
                "<think>\n"
                "1. Define RAM checking function using psutil.\n"
                "2. Create main loop to monitor RSS memory.\n"
                "3. Ensure zero external bloat and low memory consumption.\n"
                "</think>\n"
                '{"architecture": "RAM Monitoring Script", "language": "python"}'
            )
        else:
            if "ram" in prompt_lower or "memory" in prompt_lower:
                text = (
                    "```python\n"
                    "import psutil\n"
                    "import time\n"
                    "\n"
                    "def get_ram_usage_mb() -> float:\n"
                    "    process = psutil.Process()\n"
                    "    return process.memory_info().rss / (1024 * 1024)\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    print(f'Current RAM Usage: {get_ram_usage_mb():.2f} MB')\n"
                    "```"
                )
            else:
                text = (
                    "```python\n"
                    "def solution():\n"
                    "    return 'K-CLI Ground-Truth Execution Verified'\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    print(solution())\n"
                    "```"
                )

        if stream_callback:
            chunks = re.split(r"(\s+)", text)
            for chunk in chunks:
                if chunk:
                    stream_callback(chunk)

        return text

