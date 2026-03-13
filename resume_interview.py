from __future__ import annotations

"""
基于简历的面试主流程入口：

用户上传 PDF 简历 →
  resume_parser      解析姓名/邮箱/教育/经历
  skill_extractor    提取技术栈/项目经验
  question_matcher   匹配个性化问题列表
  Supervisor         加载上下文，调用 Interviewer 定制提问
  Evaluator          评估候选人回答，生成报告（结构化 JSON）
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agents.evaluator import EvaluatorAgent
from agents.interviewer import Interviewer
from agents.supervisor import State, Supervisor
from services.llm import LLMClient
from tools.resume_parser import run as resume_parse_run
from tools.skill_extractor import run as skill_extract_run
from tools.question_matcher import run as question_match_run
from tools import get_default_registry


def _load_json(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        return {}


def _summarize_resume(parsed: Dict[str, Any], skills_info: Dict[str, Any]) -> str:
    name = parsed.get("name") or "（未知姓名）"
    email = parsed.get("email") or "（无邮箱）"
    phone = parsed.get("phone") or "（无电话）"
    edu = parsed.get("education") or []
    exp = parsed.get("experience") or []
    skills = skills_info.get("skills") or []

    lines = [
        f"候选人姓名: {name}",
        f"邮箱: {email}",
        f"电话: {phone}",
        "",
        "教育背景（部分）：",
    ]
    lines.extend(f"- {e}" for e in edu[:5]) if edu else lines.append("- （无）")
    lines.append("")
    lines.append("工作/项目经历（部分行）：")
    lines.extend(f"- {e}" for e in exp[:8]) if exp else lines.append("- （无）")
    lines.append("")
    lines.append("技能栈（来自 skill_extractor）：")
    lines.append(", ".join(skills) if skills else "（无技能信息）")
    return "\n".join(lines)


def _summarize_questions(qs: List[Dict[str, Any]]) -> Tuple[str, str]:
    if not qs:
        return "（未匹配到个性化问题）", ""
    lines = []
    first_prompt = ""
    for i, q in enumerate(qs, start=1):
        title = q.get("title") or q.get("prompt") or ""
        prompt = q.get("prompt") or ""
        tags = q.get("tags") or []
        lines.append(f"{i}. {title}  [tags: {', '.join(tags)}]")
        if not first_prompt and prompt:
            first_prompt = prompt
    return "\n".join(lines), first_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="基于 PDF 简历的 AI 面试入口")
    parser.add_argument("pdf_path", help="候选人 PDF 简历路径")
    parser.add_argument("--role", default="backend_python", help="题库岗位 key（如 backend_python/frontend_web）")
    parser.add_argument("--difficulty", default="junior", help="难度（如 junior/mid/senior）")
    parser.add_argument("--offline-eval", action="store_true", help="评估失败时仅使用本地启发式评估")
    args = parser.parse_args()

    pdf_path = args.pdf_path
    if not Path(pdf_path).is_file():
        print(f"文件不存在: {pdf_path}")
        return

    print(f"[*] 解析简历: {pdf_path}")
    parsed_json = _load_json(resume_parse_run(pdf_path=pdf_path))
    if parsed_json.get("error"):
        print(f"[!] 简历解析失败: {parsed_json['error']}")
        return

    raw_text = parsed_json.get("raw_text_preview") or ""
    if not raw_text:
        print("[!] 简历文本为空，无法继续。")
        return

    print("[*] 提取技能与经历（skill_extractor）")
    skills_json = _load_json(skill_extract_run(text=raw_text))
    if skills_json.get("error"):
        print(f"[!] 技能提取失败: {skills_json['error']}")
        skills_json = {"skills": [], "experiences": [], "projects": []}

    print("[*] 匹配个性化问题（question_matcher）")
    skills = skills_json.get("skills") or []
    qm_json = _load_json(
        question_match_run(
            skills=skills,
            role=args.role,
            difficulty=args.difficulty,
            exclude_ids=[],
            use_vector=False,
        )
    )
    if qm_json.get("error"):
        print(f"[!] 问题匹配失败: {qm_json['error']}")
        questions = []
    else:
        questions = qm_json.get("questions") or []

    resume_summary = _summarize_resume(parsed_json, skills_json)
    questions_summary, first_question_prompt = _summarize_questions(questions)

    print("\n===== 简历摘要 =====")
    print(resume_summary)
    print("\n===== 候选个性化问题候选列表 =====")
    print(questions_summary)

    llm = LLMClient()
    interviewer = Interviewer(llm=llm)
    # 这里 Supervisor 不需要额外工具，可直接 None 或 get_default_registry()（如需 ReAct 工具调用可切换）
    sup = Supervisor(llm=llm, tool_registry=None, interviewer=interviewer)
    evaluator = EvaluatorAgent(llm=llm)

    # 构造对话上下文：系统向 Supervisor 解释背景与候选问题
    messages: List[Tuple[str, str]] = [
        ("系统", "以下是候选人的简历摘要：\n" + resume_summary),
        ("系统", "根据技能/经历匹配出的候选问题列表：\n" + questions_summary),
    ]
    candidate_latest = ""

    print("\n[*] 让 Interviewer 根据上下文生成首个定制问题...\n")
    reply, observations = sup.run_react(State.QUESTION, messages=messages, candidate_latest=candidate_latest)

    question_text = reply.strip() or first_question_prompt or "请你先做一个简单的自我介绍。"
    print(f"面试官：{question_text}")
    print("你：", end="")
    answer = input().strip()

    qa_pairs = [(question_text, answer)]

    print("\n[*] 对你的回答进行评估...\n")
    try:
        eval_result = evaluator.evaluate(
            question=question_text,
            qa_pairs=qa_pairs,
            role=args.role,
            level=args.difficulty,
        )
        eval_json = eval_result.to_dict()
    except Exception as exc:
        if not args.offline_eval:
            print(f"[!] 在线评估失败: {exc}，改用本地启发式评估。")
        eval_result = evaluator.evaluate_local(question=question_text, qa_pairs=qa_pairs)
        eval_json = eval_result.to_dict()

    print("===== 评估结果（JSON）=====")
    print(json.dumps(eval_json, ensure_ascii=False, indent=2))
    print("===== 面试流程结束 =====")


if __name__ == "__main__":
    main()

