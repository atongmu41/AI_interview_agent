"""
技能提取工具：从简历文本中提取技术栈、工作经验、项目经历。
- 输入：原始文本（通常来自 resume_parser 的 raw_text_preview）
- 实现：正则/关键词初筛 + LLM 结构化提取
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from services.llm import LLMClient
from tools.base import ToolSpec


def _heuristic_chunks(text: str) -> Dict[str, str]:
    """
    用规则把简历文本粗分为：skills / experience / projects 三类段落。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    skills_lines: List[str] = []
    exp_lines: List[str] = []
    proj_lines: List[str] = []

    for ln in lines:
        lower = ln.lower()
        # 技能/技术栈
        if any(k in lower for k in ["技能", "skill", "技术栈", "tech stack"]):
            skills_lines.append(ln)
            continue
        # 项目
        if any(k in lower for k in ["项目", "project", "案例"]):
            proj_lines.append(ln)
            continue
        # 工作/经历
        if any(k in lower for k in ["公司", "实习", "工作", "经验", "负责", "工程师"]):
            exp_lines.append(ln)
            continue

    return {
        "skills_text": "\n".join(skills_lines) or "",
        "experience_text": "\n".join(exp_lines) or "",
        "projects_text": "\n".join(proj_lines) or "",
        "full_text": "\n".join(lines),
    }


def _llm_extract_structured(texts: Dict[str, str]) -> Dict[str, Any]:
    """
    调用 LLM，对启发式切分的文本进行结构化提取。
    """
    llm = LLMClient()
    sys_prompt = (
        "你是一个简历分析助手，负责从候选人简历中提取技术栈、工作经验和项目经历。\n"
        "请严格按照指定 JSON 结构输出，不要添加多余说明。"
    )
    user_prompt = (
        "下面是从一份简历中提取的文本片段，请提取：\n"
        "1) skills: 归一化后的技术关键词列表，例如 ['Python', 'Django', 'PostgreSQL']。\n"
        "2) experiences: 工作/实习经历，包含公司名、职位、起止时间（若能识别）、概要描述。\n"
        "3) projects: 项目经历，包含项目名、角色、主要技术栈、职责概述。\n\n"
        "=== 技能相关文本 ===\n"
        f"{texts.get('skills_text') or '(无)'}\n\n"
        "=== 工作/实习相关文本 ===\n"
        f"{texts.get('experience_text') or '(无)'}\n\n"
        "=== 项目相关文本 ===\n"
        f"{texts.get('projects_text') or '(无)'}\n\n"
        "=== 完整文本（供补充参考） ===\n"
        f"{texts.get('full_text')[:2000]}\n\n"
        "请只输出一个 JSON，对象结构如下：\n"
        "{\n"
        '  "skills": ["Python", "Django", ...],\n'
        '  "experiences": [\n'
        '    {"company": "公司A", "title": "后端工程师", "duration": "2020-2023", "summary": "..."},\n'
        "    ...\n"
        "  ],\n"
        '  "projects": [\n'
        '    {"name": "项目X", "role": "负责人", "tech_stack": ["..."], "summary": "..."},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
    )
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]
    raw = llm.chat(messages, temperature=0.2, max_tokens=800)
    # 尝试解析 JSON；失败则返回空结构 + 原始文本
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    skills = data.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    if not isinstance(skills, list):
        skills = []
    experiences = data.get("experiences") or []
    if not isinstance(experiences, list):
        experiences = []
    projects = data.get("projects") or []
    if not isinstance(projects, list):
        projects = []
    return {
        "skills": [str(s).strip() for s in skills if str(s).strip()],
        "experiences": experiences,
        "projects": projects,
    }


def run(text: str, **kwargs: Any) -> str:
    """
    从简历文本中提取：
    - skills: 技术栈（归一化关键词列表）
    - experiences: 工作/实习经历
    - projects: 项目经历

    参数:
      - text: 简历原文或预处理后的文本（建议传 resume_parser 的 raw_text_preview）

    返回 JSON 字符串。
    """
    text = (text or "").strip()
    if not text:
        return json.dumps({"error": "text 为空"}, ensure_ascii=False)

    chunks = _heuristic_chunks(text)
    structured = _llm_extract_structured(chunks)
    result = {
        "skills": structured.get("skills", []),
        "experiences": structured.get("experiences", []),
        "projects": structured.get("projects", []),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


SPEC = ToolSpec(
    name="skill_extractor",
    description="从简历文本中提取技术栈、工作/实习经历、项目经历（正则 + LLM）",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "简历原文或预处理文本"},
        },
        "required": ["text"],
    },
)

