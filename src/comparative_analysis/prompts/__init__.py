"""
Prompt templates package for Comparative Analysis agents.
"""

from src.comparative_analysis.prompts.company_summary_prompt import COMPANY_SUMMARY_SYSTEM_PROMPT, COMPANY_SUMMARY_USER_PROMPT
from src.comparative_analysis.prompts.competitor_summary_prompt import COMPETITOR_SUMMARY_SYSTEM_PROMPT, COMPETITOR_SUMMARY_USER_PROMPT
from src.comparative_analysis.prompts.comparative_analysis_prompt import COMPARATIVE_ANALYSIS_SYSTEM_PROMPT, COMPARATIVE_ANALYSIS_USER_PROMPT
from src.comparative_analysis.prompts.recommendation_prompt import RECOMMENDATION_SYSTEM_PROMPT, RECOMMENDATION_USER_PROMPT
from src.comparative_analysis.prompts.innovation_prompt import INNOVATION_SYSTEM_PROMPT, INNOVATION_USER_PROMPT

__all__ = [
    "COMPANY_SUMMARY_SYSTEM_PROMPT",
    "COMPANY_SUMMARY_USER_PROMPT",
    "COMPETITOR_SUMMARY_SYSTEM_PROMPT",
    "COMPETITOR_SUMMARY_USER_PROMPT",
    "COMPARATIVE_ANALYSIS_SYSTEM_PROMPT",
    "COMPARATIVE_ANALYSIS_USER_PROMPT",
    "RECOMMENDATION_SYSTEM_PROMPT",
    "RECOMMENDATION_USER_PROMPT",
    "INNOVATION_SYSTEM_PROMPT",
    "INNOVATION_USER_PROMPT",
]
