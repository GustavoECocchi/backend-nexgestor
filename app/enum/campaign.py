from enum import Enum


class CampaignStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    PAUSED = "PAUSED"


class MetricLevel(str, Enum):
    VERY_GOOD = "VERY_GOOD"
    GOOD = "GOOD"
    AVERAGE = "AVERAGE"
    BAD = "BAD"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    ATTENTION = "attention"
    WARNING = "warning"
    CRITICAL = "critical"


class FunnelStage(str, Enum):
    TOP = "top_of_funnel"
    MIDDLE = "middle_of_funnel"
    BOTTOM = "bottom_of_funnel"
    POST_CLICK = "post_click"
