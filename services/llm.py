import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


DEFAULT_TIMEOUT = 30.0
_ENV_LOADED = False
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_BASE_S = 0.8


def _load_dotenv_if_needed() -> None:
    """
    从项目根目录下的 env/.env 加载环境变量。
    只加载一次，避免重复 IO。
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    # services/llm.py -> 项目根目录 -> env/.env
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[1]
    env_path = project_root / "env" / ".env"

    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 不覆盖已有环境变量（例如系统中已经设置的）
            os.environ.setdefault(key, value)

    _ENV_LOADED = True


@dataclass
class LLMConfig:
    """
    基础 LLM 配置，从环境变量或调用参数中读取。
    """

    api_key: str
    base_url: str
    model: str
    timeout: float = DEFAULT_TIMEOUT


class LLMClient:
    """
    统一封装所有与 LLM 服务交互的细节。

    - 从环境变量读取默认配置：
      - OPENAI_API_KEY
      - OPENAI_BASE_URL
      - MODEL_NAME
    - 对外只暴露简单的调用函数：
      - chat() / achat(): 进行对话补全
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.config = self._load_config(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
        self.max_retries = max(0, int(max_retries))

    @staticmethod
    def _load_config(
        api_key: Optional[str],
        base_url: Optional[str],
        model: Optional[str],
        timeout: float,
    ) -> LLMConfig:
        # 优先从 env/.env 中加载环境变量
        _load_dotenv_if_needed()

        api_key_val = api_key or os.getenv("OPENAI_API_KEY") or ""
        base_url_val = base_url or os.getenv("OPENAI_BASE_URL") or ""
        model_val = model or os.getenv("MODEL_NAME") or ""

        if not api_key_val:
            raise RuntimeError("LLM 未配置 API Key，请设置环境变量 OPENAI_API_KEY。")
        if not base_url_val:
            raise RuntimeError("LLM 未配置 Base URL，请设置环境变量 OPENAI_BASE_URL。")
        if not model_val:
            raise RuntimeError("LLM 未配置模型名称，请设置环境变量 MODEL_NAME。")

        return LLMConfig(
            api_key=api_key_val,
            base_url=base_url_val,
            model=model_val,
            timeout=timeout or DEFAULT_TIMEOUT,
        )

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        payload.update(extra)
        return payload

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _sleep_for_retry(attempt: int, base: float = DEFAULT_RETRY_BACKOFF_BASE_S) -> None:
        # 指数退避 + 少量抖动，attempt 从 0 开始
        delay = base * (2**attempt)
        delay += random.uniform(0, base)
        time.sleep(delay)

    async def achat(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> str:
        """
        异步调用聊天补全接口，返回文本内容。

        参数:
            messages: OpenAI 格式的对话历史，例如：
                [
                    {"role": "system", "content": "..."},
                    {"role": "user", "content": "..."},
                ]
            extra: 额外的参数，例如 temperature、max_tokens 等。
        """
        last_exc: Exception | None = None
        async with httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        ) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        "/chat/completions",
                        headers=self._build_headers(),
                        json=self._build_payload(messages, **extra),
                    )
                    if response.status_code >= 400:
                        if self._is_retryable_status(response.status_code) and attempt < self.max_retries:
                            self._sleep_for_retry(attempt)
                            continue
                        response.raise_for_status()
                    data = response.json()
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_exc = exc
                    if attempt < self.max_retries:
                        self._sleep_for_retry(attempt)
                        continue
                    raise RuntimeError(f"LLM 请求失败（网络/超时），已重试 {self.max_retries} 次。") from exc
            else:
                raise RuntimeError("LLM 请求失败（未知原因）。") from last_exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"LLM 返回数据格式异常: {data}") from exc

    def chat(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> str:
        """
        同步封装，内部使用 httpx.Client。
        """
        last_exc: Exception | None = None
        with httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        ) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(
                        "/chat/completions",
                        headers=self._build_headers(),
                        json=self._build_payload(messages, **extra),
                    )
                    if response.status_code >= 400:
                        if self._is_retryable_status(response.status_code) and attempt < self.max_retries:
                            self._sleep_for_retry(attempt)
                            continue
                        response.raise_for_status()
                    data = response.json()
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_exc = exc
                    if attempt < self.max_retries:
                        self._sleep_for_retry(attempt)
                        continue
                    raise RuntimeError(f"LLM 请求失败（网络/超时），已重试 {self.max_retries} 次。") from exc
            else:
                raise RuntimeError("LLM 请求失败（未知原因）。") from last_exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"LLM 返回数据格式异常: {data}") from exc


__all__ = ["LLMClient", "LLMConfig"]

