from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from agents.supervisor import State, Supervisor
from services.llm import LLMClient
import sys
import json
import argparse
import re

from agents.evaluator import EvaluatorAgent
from services.question_bank import QuestionBank
from agents.interviewer import Interviewer
from tools import get_default_registry


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_simple_prompts_yaml(yaml_text: str) -> Dict[str, Dict[str, str]]:
    """
    极简解析器：只为当前 prompts.yaml 的简单结构服务。
    返回形如 {"interviewer": {"temperature": "0.7", ...}, "evaluator": {...}}
    """
    result: Dict[str, Dict[str, str]] = {}
    current: str | None = None

    for raw in yaml_text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if line.endswith(":"):
                current = line[:-1].strip()
                result.setdefault(current, {})
            else:
                current = None
            continue
        if current is None:
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        result[current][k.strip()] = v.strip().strip('"').strip("'")

    return result


_ANSWER_TAG_RE = re.compile(r"^\s*<([^>]+)>\s*")


def _strip_answer_tag(text: str) -> Tuple[str, str]:
    """
    从模型输出中剥离 Answer 标签。
    返回 (纯文本, 标签字符串或 \"\")。
    """
    if not text:
        return "", ""
    m = _ANSWER_TAG_RE.match(text)
    if not m:
        return text.strip(), ""
    tag = m.group(1).strip()
    pure = text[m.end() :].strip()
    return pure, tag


def _build_interviewer_messages(
    interviewer_md: str,
    prompts_yaml: str,
    asked_questions: List[str],
    current_round: List[Tuple[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "你是技术面试官。你的目标是用简洁清晰的问题评估候选人真实能力。\n"
        "你必须遵循下面的《面试官 Agent 设计说明》。\n\n"
        f"{interviewer_md}\n\n"
        "下面是当前 prompts.yaml（用于理解参数与意图，不要求严格按 YAML 输出）。\n\n"
        f"{prompts_yaml}\n\n"
        "输出要求：\n"
        "- 只输出你要对候选人说的话（不要加 '面试官：' 前缀）。\n"
        "- 如果需要追问，请提出一个追问问题；如果不需要追问，请明确告诉我“进入评估”。\n"
    )

    user = (
        "当前已问过的主问题列表：\n"
        + ("\n".join(f"- {q}" for q in asked_questions) if asked_questions else "- （无）")
        + "\n\n"
        "本轮对话记录（Q/A，含追问）：\n"
        + ("\n".join(f"Q: {q}\nA: {a}" for q, a in current_round) if current_round else "（无）")
        + "\n\n"
        "请：\n"
        "1) 如果当前还没有主问题：生成一个新的主问题。\n"
        "2) 如果当前已经有主问题且候选人已回答：决定追问或进入评估。\n"
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_evaluator_messages(
    evaluator_md: str,
    prompts_yaml: str,
    question: str,
    current_round: List[Tuple[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "你是技术面试评估官。你的目标是基于对话证据给出结构化评估。\n"
        "你必须遵循下面的《评估 Agent 设计说明》。\n\n"
        f"{evaluator_md}\n\n"
        "下面是当前 prompts.yaml（用于理解参数与意图）。\n\n"
        f"{prompts_yaml}\n\n"
        "输出要求：\n"
        "- 用中文输出。\n"
        "- 用清晰分段输出：overall_score、dimension_scores、evidence、strengths、gaps、risk_flags、recommended_followups。\n"
        "- evidence 必须引用候选人回答中的原话或明确片段。\n"
    )

    user = (
        f"题目：{question}\n\n"
        "对话记录（Q/A，含追问）：\n"
        + "\n".join(f"Q: {q}\nA: {a}" for q, a in current_round)
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def main() -> None:
    # 尽量避免 Windows 控制台中文乱码（不保证所有终端都生效）
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="ai-interview-agent 模块联调入口（文本版）")
    parser.add_argument("--offline", action="store_true", help="离线模式：不调用 LLM，用题库出题并用本地评估兜底")
    parser.add_argument("--role", default="backend_python", help="题库岗位 key，如 backend_python / frontend_web")
    parser.add_argument("--difficulty", default="junior", help="难度，如 junior / mid / senior")
    parser.add_argument("--seed", type=int, default=42, help="抽题随机种子（可复现）")
    parser.add_argument("--resume", action="store_true", help="简历模式：基于简历上下文 + ReAct 提问（需手动在代码中注入简历摘要）")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    prompts_path = root / "config" / "prompts.yaml"
    interviewer_md_path = root / "prompts" / "interviewer.md"
    evaluator_md_path = root / "prompts" / "evaluator.md"
    questions_path = root / "config" / "questions.yaml"

    prompts_yaml = _read_text(prompts_path) if prompts_path.is_file() else ""
    interviewer_md = _read_text(interviewer_md_path) if interviewer_md_path.is_file() else ""
    evaluator_md = _read_text(evaluator_md_path) if evaluator_md_path.is_file() else ""

    prompts_cfg = _parse_simple_prompts_yaml(prompts_yaml)
    interviewer_temperature = float(prompts_cfg.get("interviewer", {}).get("temperature", "0.7") or 0.7)
    interviewer_max_tokens = int(prompts_cfg.get("interviewer", {}).get("max_tokens", "500") or 500)
    evaluator_temperature = float(prompts_cfg.get("evaluator", {}).get("temperature", "0.3") or 0.3)
    evaluator_max_tokens = int(prompts_cfg.get("evaluator", {}).get("max_tokens", "800") or 800)

    llm = LLMClient()
    interviewer = Interviewer(llm=llm)
    registry = get_default_registry()
    # 始终为 Supervisor 注入工具与 Interviewer，让 ReAct 可以自主决策提问/结束
    sup = Supervisor(llm=llm, tool_registry=registry, interviewer=interviewer)
    evaluator = EvaluatorAgent(llm=llm, prompts_yaml_path=prompts_path)

    try:
        qb = QuestionBank.load(questions_path)
    except Exception as exc:
        qb = None
        print(f"题库加载失败（将无法离线出题）：{exc}")

    print("文本版 AI 面试（指令：/interrupt 打断，/continue 继续，/end 结束）")
    if args.offline:
        print(f"已启用离线模式：role={args.role} difficulty={args.difficulty} seed={args.seed}")

    asked_questions: List[str] = []
    asked_question_ids: List[str] = []
    current_question: str = ""
    current_round: List[Tuple[str, str]] = []
    followup_count = 0
    followup_limit = 2
    dialog_history: List[Tuple[str, str]] = []

    sup.continue_()  # INIT -> QUESTION

    while not sup.is_ended:
        if sup.state == State.QUESTION:
            current_round = []
            followup_count = 0
            current_question = ""

            if args.offline and qb is not None:
                picked = qb.sample(
                    role=args.role,
                    difficulty=args.difficulty,
                    n=1,
                    exclude_ids=asked_question_ids,
                    seed=args.seed + len(asked_question_ids),
                )
                if not picked:
                    print("\n题库已无可抽题，自动结束。")
                    sup.end()
                    break
                qobj = picked[0]
                asked_question_ids.append(qobj.id)
                current_question, _ = _strip_answer_tag(qobj.prompt.strip())
            else:
                # 在线模式：交给 ReAct + Supervisor 决定问什么问题/是否结束
                reply, obs = sup.run_react(
                    State.QUESTION,
                    messages=dialog_history,
                    candidate_latest="",
                    max_steps=5,
                )
                question_text, tag = _strip_answer_tag(reply)
                if "结束面试" in tag:
                    sup.end()
                    break
                if not question_text:
                    question_text = "我们先从简单的自我介绍开始，可以吗？"
                current_question = question_text
            asked_questions.append(current_question)
            current_round.append((current_question, ""))

            print(f"\n面试官：{current_question}")
            print("你：", end="")
            try:
                ans = input().strip()
            except EOFError:
                sup.end()
                break

            if ans == "/end":
                # 终止前基于当前轮次进行评估
                if any(a for _, a in current_round):
                    try:
                        result = evaluator.evaluate(
                            question=current_question,
                            qa_pairs=current_round,
                            role=args.role if args.offline else "",
                            level=args.difficulty if args.offline else "",
                        )
                    except Exception:
                        result = evaluator.evaluate_local(
                            question=current_question,
                            qa_pairs=current_round,
                        )
                    print("\n--- 终止面试 · 评估报告 ---")
                    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
                    print("-------------------\n")
                else:
                    print("\n当前无有效对话，无法生成评估。\n")
                sup.end()
                break
            if ans == "/interrupt":
                sup.interrupt()
                continue
            if ans == "/continue":
                sup.continue_()
                continue

            current_round[-1] = (current_question, ans)
            dialog_history.append(("面试官", current_question))
            dialog_history.append(("候选人", ans))
            sup.continue_()  # QUESTION -> FOLLOWUP
            continue

        if sup.state == State.FOLLOWUP:
            if args.offline:
                # 离线模式：固定 1 次追问，然后进入评估
                if followup_count >= 1:
                    sup.continue_()
                    continue
                followup_q = "你能举一个具体例子/项目场景来说明你的回答吗？"
                current_round.append((followup_q, ""))
                followup_count += 1

                print(f"\n面试官（追问）：{followup_q}")
                print("你：", end="")
                try:
                    ans = input().strip()
                except EOFError:
                    sup.end()
                    break

                if ans == "/end":
                    # 终止前基于当前轮次进行评估
                    if any(a for _, a in current_round):
                        try:
                            result = evaluator.evaluate(
                                question=current_question,
                                qa_pairs=current_round,
                                role=args.role if args.offline else "",
                                level=args.difficulty if args.offline else "",
                            )
                        except Exception:
                            result = evaluator.evaluate_local(
                                question=current_question,
                                qa_pairs=current_round,
                            )
                        print("\n--- 终止面试 · 评估报告 ---")
                        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
                        print("-------------------\n")
                    else:
                        print("\n当前无有效对话，无法生成评估。\n")
                    sup.end()
                    break
                if ans == "/interrupt":
                    sup.interrupt()
                    continue
                if ans == "/continue":
                    sup.continue_()  # FOLLOWUP -> EVALUATE
                    continue

                current_round[-1] = (followup_q, ans)
                dialog_history.append(("面试官", followup_q))
                dialog_history.append(("候选人", ans))
                continue

            # 在线模式：由 ReAct 决定是否继续追问 / 进入评估 / 结束面试
            last_candidate = ""
            for role, text in reversed(dialog_history):
                if role == "候选人":
                    last_candidate = text
                    break
            reply, obs = sup.run_react(
                State.FOLLOWUP,
                messages=dialog_history,
                candidate_latest=last_candidate,
                max_steps=5,
            )
            followup_q, tag = _strip_answer_tag(reply)

            if "结束面试" in tag:
                sup.end()
                break
            if "进入评估" in tag or followup_count >= followup_limit:
                sup.continue_()  # FOLLOWUP -> EVALUATE
                continue

            current_round.append((followup_q, ""))
            followup_count += 1

            print(f"\n面试官（追问）：{followup_q}")
            print("你：", end="")
            try:
                ans = input().strip()
            except EOFError:
                sup.end()
                break

            if ans == "/end":
                # 终止前基于当前轮次进行评估
                if any(a for _, a in current_round):
                    try:
                        result = evaluator.evaluate(
                            question=current_question,
                            qa_pairs=current_round,
                            role=args.role if args.offline else "",
                            level=args.difficulty if args.offline else "",
                        )
                    except Exception:
                        result = evaluator.evaluate_local(
                            question=current_question,
                            qa_pairs=current_round,
                        )
                    print("\n--- 终止面试 · 评估报告 ---")
                    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
                    print("-------------------\n")
                else:
                    print("\n当前无有效对话，无法生成评估。\n")
                sup.end()
                break
            if ans == "/interrupt":
                sup.interrupt()
                continue
            if ans == "/continue":
                # 允许直接跳到评估
                sup.continue_()  # FOLLOWUP -> EVALUATE
                continue

            current_round[-1] = (followup_q, ans)
            dialog_history.append(("面试官", followup_q))
            dialog_history.append(("候选人", ans))
            continue

        if sup.state == State.EVALUATE:
            try:
                result = evaluator.evaluate(
                    question=current_question,
                    qa_pairs=current_round,
                    role=args.role if args.offline else "",
                    level=args.difficulty if args.offline else "",
                )
                evaluation = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            except Exception as exc:
                print(f"\n评估失败（将使用本地兜底）：{exc}")
                result = evaluator.evaluate_local(question=current_question, qa_pairs=current_round)
                evaluation = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

            print("\n--- 评估结果 ---")
            print(evaluation)
            print("---------------\n")

            print("输入 /continue 继续下一题，或 /end 结束：", end="")
            try:
                cmd = input().strip()
            except EOFError:
                sup.end()
                break
            if cmd == "/end":
                sup.end()
                break
            sup.interrupt()  # 回到 QUESTION 开始下一题
            continue

    print("\n面试已结束。")


if __name__ == "__main__":
    main()

