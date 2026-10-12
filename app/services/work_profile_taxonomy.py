"""Meet The People network — role/function taxonomy for workflow routing."""

from typing import Literal

WorkFunction = Literal[
    "creative",
    "strategy",
    "account_client",
    "data_analytics",
    "media_performance",
    "technology_engineering",
    "operations",
    "leadership_general",
    "unknown",
]

SeniorityBand = Literal[
    "intern",
    "individual_contributor",
    "senior_ic",
    "manager",
    "director",
    "vp",
    "c_suite",
    "founder",
    "unknown",
]

AgencyOrientation = Literal[
    "creative_agency",
    "media_agency",
    "analytics_data",
    "full_service",
    "holding_company",
    "brand_in_house",
    "unknown",
]

# Hints for downstream products — expand as MTP platforms define real workflow IDs.
SuggestedWorkflow = Literal[
    "creative_brief_review",
    "concept_development",
    "campaign_trafficking",
    "media_planning",
    "performance_reporting",
    "data_analysis",
    "client_presentation",
    "stakeholder_updates",
    "team_management",
    "resource_planning",
    "technical_delivery",
    "unknown",
]

WORK_FUNCTIONS: tuple[str, ...] = (
    "creative",
    "strategy",
    "account_client",
    "data_analytics",
    "media_performance",
    "technology_engineering",
    "operations",
    "leadership_general",
    "unknown",
)

SENIORITY_BANDS: tuple[str, ...] = (
    "intern",
    "individual_contributor",
    "senior_ic",
    "manager",
    "director",
    "vp",
    "c_suite",
    "founder",
    "unknown",
)

AGENCY_ORIENTATIONS: tuple[str, ...] = (
    "creative_agency",
    "media_agency",
    "analytics_data",
    "full_service",
    "holding_company",
    "brand_in_house",
    "unknown",
)

SUGGESTED_WORKFLOWS: tuple[str, ...] = (
    "creative_brief_review",
    "concept_development",
    "campaign_trafficking",
    "media_planning",
    "performance_reporting",
    "data_analysis",
    "client_presentation",
    "stakeholder_updates",
    "team_management",
    "resource_planning",
    "technical_delivery",
    "unknown",
)
