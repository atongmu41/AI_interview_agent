"""
工具注册表：所有工具在 Supervisor 侧统一发现与调用。
"""
from tools.base import ToolRegistry, ToolSpec
from tools.search import SPEC as SEARCH_SPEC, run as search_run
from tools.timer import SPEC as TIMER_SPEC, run as timer_run
from tools.candidate_db import SPEC as CANDIDATE_DB_SPEC, run as candidate_db_run
from tools.calendar import SPEC as CALENDAR_SPEC, run as calendar_run
from tools.notification import SPEC as NOTIFICATION_SPEC, run as notification_run
from tools.knowledge_base import SPEC as KNOWLEDGE_BASE_SPEC, run as knowledge_base_run
from tools.resume_parser import SPEC as RESUME_PARSER_SPEC, run as resume_parser_run
from tools.skill_extractor import SPEC as SKILL_EXTRACTOR_SPEC, run as skill_extractor_run
from tools.question_matcher import SPEC as QUESTION_MATCHER_SPEC, run as question_matcher_run


def get_default_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(SEARCH_SPEC, search_run)
    r.register(RESUME_PARSER_SPEC, resume_parser_run)
    r.register(SKILL_EXTRACTOR_SPEC, skill_extractor_run)
    r.register(QUESTION_MATCHER_SPEC, question_matcher_run)
    r.register(TIMER_SPEC, timer_run)
    r.register(CANDIDATE_DB_SPEC, candidate_db_run)
    r.register(CALENDAR_SPEC, calendar_run)
    r.register(NOTIFICATION_SPEC, notification_run)
    r.register(KNOWLEDGE_BASE_SPEC, knowledge_base_run)
    return r


__all__ = ["ToolRegistry", "ToolSpec", "get_default_registry"]
