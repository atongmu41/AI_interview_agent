"""
简历解析：从 PDF 提取文本，并解析出基本信息（姓名、联系方式、教育、经历等）。
依赖 pdfplumber。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.base import ToolSpec

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore


def _extract_text_from_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 PDF 文件，当前: {path.suffix}")

    if pdfplumber is None:
        raise RuntimeError("请安装 pdfplumber：pip install pdfplumber")

    text_parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


# 常见正则：邮箱、手机（国内）、教育/工作段落
_RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_RE_PHONE_CN = re.compile(r"1[3-9]\d{9}|\d{3,4}[-\s]?\d{7,8}|\+86\s*\d{2,3}[-\s]?\d{4}[-\s]?\d{4}")
_RE_SPLIT_LINES = re.compile(r"\n\s*\n")


def _parse_basic_info(raw_text: str) -> Dict[str, Any]:
    """从纯文本中启发式提取基本信息。"""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    full_text = "\n".join(lines)

    # 邮箱（取第一个）
    emails = _RE_EMAIL.findall(full_text)
    email = emails[0] if emails else ""

    # 电话（取第一个）
    phones = _RE_PHONE_CN.findall(full_text)
    phone = phones[0].strip() if phones else ""

    # 姓名：常出现在前几行，且不含邮箱/电话/“简历”等
    name = ""
    skip = {"简历", "resume", "个人简介", "求职", "应聘", "电话", "邮箱", "手机", "email", "phone"}
    for ln in lines[:8]:
        ln_lower = ln.lower()
        if any(s in ln_lower or s in ln for s in skip):
            continue
        if _RE_EMAIL.search(ln) or _RE_PHONE_CN.search(ln):
            continue
        if 2 <= len(ln) <= 20 and not ln.isdigit():
            name = ln
            break

    # 教育经历：含“本科/硕士/博士/大学/学院/专业”的段落
    education: List[str] = []
    for ln in lines:
        if any(k in ln for k in ("大学", "学院", "学校", "本科", "硕士", "博士", "专业", "学历", "毕业")):
            education.append(ln)

    # 工作/项目经历：含“公司/实习/项目/经验/负责”等
    experience: List[str] = []
    for ln in lines:
        if any(k in ln for k in ("公司", "实习", "项目", "经验", "负责", "开发", "工程师", "技术")):
            if ln not in education:
                experience.append(ln)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "education": education[:10],
        "experience": experience[:15],
        "raw_text_preview": full_text[:1500].strip(),  # 前 1500 字供后续技能/问题匹配用
    }


def run(pdf_path: str, **kwargs: Any) -> str:
    """
    解析 PDF 简历，提取基本信息。
    - pdf_path: PDF 文件路径（绝对或相对当前工作目录）
    返回 JSON 字符串，包含 name, email, phone, education, experience, raw_text_preview。
    """
    try:
        text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    if not text.strip():
        return json.dumps({"error": "PDF 未提取到文本", "name": "", "email": "", "phone": "", "education": [], "experience": [], "raw_text_preview": ""}, ensure_ascii=False)

    info = _parse_basic_info(text)
    return json.dumps(info, ensure_ascii=False, indent=2)


SPEC = ToolSpec(
    name="resume_parser",
    description="解析 PDF 简历，提取姓名、邮箱、电话、教育经历、工作经历及原文预览",
    parameters={
        "type": "object",
        "properties": {"pdf_path": {"type": "string", "description": "PDF 文件路径"}},
        "required": ["pdf_path"],
    },
)
