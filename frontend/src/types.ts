export interface Company {
  ticker: string;
  company_name: string;
}

export interface User {
  username: string;
  user_link: string;
}

export interface Performance {
  nextDayOpen: number | null;
  nextDayClose: number | null;
  oneWeekClosePerf: number | null;
  twoWeekClosePerf: number | null;
  oneMonthPerf: number | null;
  threeMonthPerf: number | null;
  sixMonthPerf: number | null;
  oneYearPerf: number | null;
  twoYearPerf: number | null;
  threeYearPerf: number | null;
  fiveYearPerf: number | null;
}

export interface TotalReturn {
  idea_id: string;
  ticker: string;
  matched_ticker: string;
  start_period: string;
  end_period: string;
  start_price: number;
  end_price: number;
  dividends: number;
  stock_total_return_pct: number;
  idea_total_return_pct: number;
  annualized_idea_return_pct: number | null;
  benchmark_total_return_pct: number | null;
  benchmark_annualized_return_pct: number | null;
  excess_total_return_pct: number | null;
  excess_annualized_return_pct: number | null;
  periods_held: number;
  calculation_note: string;
  computed_at: string;
}

export interface Idea {
  id: string;
  link: string;
  company_id: string;
  user_id: string;
  date: string;
  is_short: boolean;
  is_contest_winner: boolean;
  company?: Company | null;
  user?: User | null;
  performance?: Performance | null;
  total_return?: TotalReturn | null;
}

export interface IdeaDetail extends Idea {
  description?: { description: string } | null;
  catalysts?: { catalysts: string } | null;
}

export interface IdeaExportRow {
  idea_id: string;
  ticker: string;
  matched_ticker: string | null;
  company_name: string | null;
  date: string;
  side: 'Long' | 'Short';
  is_contest_winner: boolean;
  author: string | null;
  author_link: string;
  latest_revenue: number | null;
  latest_revenue_period: string | null;
  annual_idea_return_pct: number | null;
  total_idea_return_pct: number | null;
  stock_total_return_pct: number | null;
  benchmark_annual_return_pct: number | null;
  benchmark_total_return_pct: number | null;
  excess_annual_return_pct: number | null;
  excess_total_return_pct: number | null;
  start_period: string | null;
  end_period: string | null;
  start_price: number | null;
  end_price: number | null;
  dividends: number | null;
  years_held: number | null;
  vic_link: string | null;
}

export interface Sp500TotalReturnRow {
  date: string;
  period: string;
  index_value: number;
  normalized_value: number;
  period_return_pct: number | null;
  cumulative_return_pct: number;
  source: string;
  computed_at: string;
}

export interface IdeaListParams {
  skip: number;
  limit: number;
  search?: string;
}
