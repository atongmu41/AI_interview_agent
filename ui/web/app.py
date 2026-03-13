from __future__ import annotations

"""
Web UI 后端入口（FastAPI）：
- 简历上传与解析
- 面试配置
- 简历解析结果/技能/匹配问题预览
（实时面试与评估接口预留，后续可接现有 Supervisor / Evaluator 流程）
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from services.llm import LLMClient
from agents.evaluator import EvaluatorAgent
from agents.supervisor import State, Supervisor
from agents.interviewer import Interviewer
from tools import get_default_registry
from main import _strip_answer_tag

from tools.resume_parser import run as resume_parse_run
from tools.skill_extractor import run as skill_extract_run
from tools.question_matcher import run as question_match_run
from tools.knowledge_base import run as knowledge_base_run


BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROMPTS_PATH = BASE_DIR / "config" / "prompts.yaml"

app = FastAPI(title="AI Resume Interview Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _safe_json(s: str) -> Dict[str, Any]:
    import json

    try:
        return json.loads(s)
    except Exception:
        return {}


def _create_supervisor() -> Supervisor:
    """
    为当前请求创建一个 Supervisor 实例。
    简化版本：不做跨请求 session 复用，由前端传回完整 history。
    """
    llm = LLMClient()
    interviewer = Interviewer(llm=llm)
    registry = get_default_registry()
    return Supervisor(llm=llm, tool_registry=registry, interviewer=interviewer)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = TEMPLATE_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/upload_resume")
async def upload_resume(
    file: UploadFile = File(...),
    role: str = Form("backend_python"),
    difficulty: str = Form("junior"),
) -> JSONResponse:
    """
    简历上传与解析：
    - 解析 PDF → 基本信息
    - 提取技能 → 技术栈/项目经验
    - 匹配问题 → 个性化问题列表
    - 生成岗位要求画像（占位实现，基于 knowledge_base 工具）
    """
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "仅支持 PDF 文件"}, status_code=400)

    tmp_path = BASE_DIR / "tmp_resume.pdf"
    content = await file.read()
    tmp_path.write_bytes(content)

    parsed = _safe_json(resume_parse_run(pdf_path=str(tmp_path)))
    if parsed.get("error"):
        return JSONResponse({"error": f"简历解析失败: {parsed['error']}"}, status_code=400)

    raw_text = parsed.get("raw_text_preview") or ""
    skills_info = _safe_json(skill_extract_run(text=raw_text))
    if skills_info.get("error"):
        skills_info = {"skills": [], "experiences": [], "projects": []}

    skills = skills_info.get("skills") or []
    matched = _safe_json(
        question_match_run(
            skills=skills,
            role=role,
            difficulty=difficulty,
            exclude_ids=[],
            use_vector=False,
        )
    )
    questions = matched.get("questions") or []

    # 岗位要求画像（占位实现：基于 knowledge_base 工具简要生成）
    # role_custom 可能通过 form body 传递，但 FastAPI 未直接声明；从 request.form 中兜底读取。
    job_profile = ""
    try:
        # 这里不引入 Request 依赖，先尝试从解析结果中构造占位岗位说明
        query = role or "（未提供岗位）"
        job_profile = knowledge_base_run(query=query, category="job_profile")
    except Exception:
        job_profile = "当前暂未能生成岗位要求画像。"

    return JSONResponse(
        {
            "resume": parsed,
            "skills": skills_info,
            "questions": questions,
            "job_profile": job_profile,
        }
    )


# 预留接口：实时面试 & 评估（以便前端完成「实时面试界面」「结果展示」交互）
@app.post("/api/interview_step")
async def interview_step(payload: Dict[str, Any]) -> JSONResponse:
    """
    使用 Supervisor + ReAct 决定下一句面试官发言。

    入参 JSON:
    {
      "state": "question" | "followup",
      "history": [{ "role": "面试官/候选人/系统", "text": "..." }, ...],
      "candidate_latest": "候选人最新回答"
    }

    出参 JSON:
    {
      "reply": "面试官下一句要说的话（不含标签）",
      "tag": "<继续提问|进入评估|结束面试|...>",
      "observations": ["ReAct 工具调用观察 ...", ...]
    }
    """
    state_str = (payload.get("state") or "question").lower()
    raw_history = payload.get("history") or []
    candidate_latest = (payload.get("candidate_latest") or "").strip()

    messages: List[Tuple[str, str]] = [
        (str(item.get("role") or "系统"), str(item.get("text") or ""))
        for item in raw_history
    ]

    sup = _create_supervisor()
    state = State.QUESTION if state_str == "question" else State.FOLLOWUP

    reply, observations = sup.run_react(
        state=state,
        messages=messages,
        candidate_latest=candidate_latest,
        max_steps=5,
    )
    pure, tag = _strip_answer_tag(reply or "")
    return JSONResponse(
        {
            "reply": pure or "（暂无回复）",
            "tag": tag,
            "observations": observations,
        }
    )


@app.post("/api/evaluate")
async def evaluate(payload: Dict[str, Any]) -> JSONResponse:
    """
    根据前端上传的对话历史生成评估结果。

    入参 JSON:
    {
      "history": [{ "role": "面试官/候选人/系统", "text": "..." }, ...],
      "role": "backend_python",
      "difficulty": "junior"
    }
    """
    raw_history = payload.get("history") or []
    role = str(payload.get("role") or "")
    difficulty = str(payload.get("difficulty") or "")

    qa_pairs: List[Tuple[str, str]] = []
    last_question: str = ""
    last_role: str = ""

    for item in raw_history:
        r = str(item.get("role") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if r == "面试官":
            last_question = text
            last_role = r
        elif r == "候选人" and last_role == "面试官" and last_question:
            qa_pairs.append((last_question, text))
            last_question = ""
            last_role = r

    if not qa_pairs:
        return JSONResponse({"error": "无有效对话，无法评估"}, status_code=400)

    question = qa_pairs[0][0]
    try:
        evaluator = EvaluatorAgent(llm=LLMClient(), prompts_yaml_path=PROMPTS_PATH)
        result = evaluator.evaluate(
            question=question,
            qa_pairs=qa_pairs,
            role=role,
            level=difficulty,
        )
    except Exception:
        evaluator = EvaluatorAgent(llm=LLMClient(), prompts_yaml_path=PROMPTS_PATH)
        result = evaluator.evaluate_local(question=question, qa_pairs=qa_pairs)

    return JSONResponse({"evaluation": result.to_dict()})


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ui.web.app:app", host="0.0.0.0", port=8000, reload=True)

