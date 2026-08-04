# DEPRECATED: Factory functions below exist for future dependency-injection migration but are
# NOT currently used. Services are instantiated directly at call sites. When DI is introduced
# (e.g., FastAPI Depends), replace direct instantiation with these factory functions.
# TODO: Wire into DI container once migration is planned.

"""服务层 — 业务逻辑 (惰性导入, 避免数据库未就绪时崩溃)"""

__all__ = [
    "QAService",
    "DashboardService",
    "TestService",
    "ReportService",
    "WebEvalService",
    "KBService",
]


def get_qa_service():
    from .qa_service import QAService
    return QAService()


def get_dashboard_service():
    from .dashboard_service import DashboardService
    return DashboardService()


def get_test_service():
    from .test_service import TestService
    return TestService()


def get_report_service():
    from .report_service import ReportService
    return ReportService()


def get_web_eval_service():
    from .web_eval_service import WebEvalService
    return WebEvalService()


def get_kb_service():
    from .kb_service import KBService
    return KBService()
