"""Модуль отчётов для раздела «Отчёты» в порталах ФФ и селлера."""

from .period import CompareMode, DateRange, PeriodPreset, ReportingPeriod
from .registry import ChartType, Portal, ReportSpec, get_report_spec, get_reports_registry
from .scope import ReportingScope, resolve_reporting_scope

__all__ = [
    "ChartType",
    "CompareMode",
    "DateRange",
    "PeriodPreset",
    "Portal",
    "ReportingPeriod",
    "ReportingScope",
    "ReportSpec",
    "get_report_spec",
    "get_reports_registry",
    "resolve_reporting_scope",
]
