from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ValueInvestorsClub.ValueInvestorsClub.models.Base import Base


class IdeaTotalReturn(Base):
    __tablename__ = "idea_total_returns"

    idea_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    matched_ticker: Mapped[str] = mapped_column(String, nullable=False)
    start_period: Mapped[str] = mapped_column(String, nullable=False)
    end_period: Mapped[str] = mapped_column(String, nullable=False)
    start_price: Mapped[float] = mapped_column(Float, nullable=False)
    end_price: Mapped[float] = mapped_column(Float, nullable=False)
    dividends: Mapped[float] = mapped_column(Float, nullable=False)
    stock_total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    idea_total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    annualized_idea_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    benchmark_total_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    benchmark_annualized_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    excess_total_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    excess_annualized_return_pct: Mapped[float] = mapped_column(Float, nullable=True)
    periods_held: Mapped[int] = mapped_column(Integer, nullable=False)
    calculation_note: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[str] = mapped_column(String, nullable=False)
