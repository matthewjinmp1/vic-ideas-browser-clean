"""
Pydantic models for request/response schemas for the ValueInvestorsClub API.
"""
from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel


class PerformanceResponse(BaseModel):
    """Performance metrics for an investment idea."""
    # Base performance values
    nextDayOpen: Optional[float] = None
    nextDayClose: Optional[float] = None
    
    # Traditional performance metrics
    oneWeekClosePerf: Optional[float] = None
    twoWeekClosePerf: Optional[float] = None
    oneMonthPerf: Optional[float] = None
    threeMonthPerf: Optional[float] = None
    sixMonthPerf: Optional[float] = None
    oneYearPerf: Optional[float] = None
    twoYearPerf: Optional[float] = None
    threeYearPerf: Optional[float] = None
    fiveYearPerf: Optional[float] = None
    
    # Timeline data for each performance period
    # These could be used to create time-series visualizations
    timeline_labels: Optional[List[str]] = None
    timeline_values: Optional[List[float]] = None
    
    # Performance breakdown by time period with normalized values
    # Useful for comparing across different time periods
    performance_periods: Optional[Dict[str, float]] = None

    model_config = {"from_attributes": True}


class TotalReturnResponse(BaseModel):
    """Approximate total return calculated from local QuickFS quarter-end data."""
    idea_id: str
    ticker: str
    matched_ticker: str
    start_period: str
    end_period: str
    start_price: float
    end_price: float
    dividends: float
    stock_total_return_pct: float
    idea_total_return_pct: float
    annualized_idea_return_pct: Optional[float] = None
    benchmark_total_return_pct: Optional[float] = None
    benchmark_annualized_return_pct: Optional[float] = None
    excess_total_return_pct: Optional[float] = None
    excess_annualized_return_pct: Optional[float] = None
    periods_held: int
    calculation_note: str
    computed_at: str

    model_config = {"from_attributes": True}


class IdeaExportRow(BaseModel):
    """Flattened idea row for spreadsheet export."""
    idea_id: str
    ticker: str
    matched_ticker: Optional[str] = None
    company_name: Optional[str] = None
    date: datetime
    side: str
    is_contest_winner: bool
    author: Optional[str] = None
    author_link: str
    latest_revenue: Optional[float] = None
    latest_revenue_period: Optional[str] = None
    annual_idea_return_pct: Optional[float] = None
    total_idea_return_pct: Optional[float] = None
    stock_total_return_pct: Optional[float] = None
    benchmark_annual_return_pct: Optional[float] = None
    benchmark_total_return_pct: Optional[float] = None
    excess_annual_return_pct: Optional[float] = None
    excess_total_return_pct: Optional[float] = None
    start_period: Optional[str] = None
    end_period: Optional[str] = None
    start_price: Optional[float] = None
    end_price: Optional[float] = None
    dividends: Optional[float] = None
    years_held: Optional[float] = None
    vic_link: Optional[str] = None


class Sp500TotalReturnRow(BaseModel):
    """S&P 500 Total Return Index row for spreadsheet export."""
    date: str
    period: str
    index_value: float
    normalized_value: float
    period_return_pct: Optional[float] = None
    cumulative_return_pct: float
    source: str
    computed_at: str


class DescriptionResponse(BaseModel):
    """Description of an investment idea."""
    description: str

    model_config = {"from_attributes": True}


class CatalystsResponse(BaseModel):
    """Catalysts for an investment idea."""
    catalysts: str

    model_config = {"from_attributes": True}


class CompanyResponse(BaseModel):
    """Company information."""
    ticker: str
    company_name: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """User information."""
    username: str
    user_link: str

    model_config = {"from_attributes": True}


class IdeaResponse(BaseModel):
    """Basic information about an investment idea."""
    id: str
    link: Optional[str] = ""  # Make link optional with default empty string
    company_id: str
    user_id: str
    date: datetime
    is_short: bool
    is_contest_winner: bool
    company: Optional[CompanyResponse] = None
    user: Optional[UserResponse] = None
    performance: Optional[PerformanceResponse] = None
    total_return: Optional[TotalReturnResponse] = None

    model_config = {"from_attributes": True}


class IdeaDetailResponse(IdeaResponse):
    """Detailed information about an investment idea, including related data."""
    company: Optional[CompanyResponse] = None
    user: Optional[UserResponse] = None
    description: Optional[DescriptionResponse] = None
    catalysts: Optional[CatalystsResponse] = None
    performance: Optional[PerformanceResponse] = None
    total_return: Optional[TotalReturnResponse] = None

    model_config = {"from_attributes": True}
