from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CompanyFeed(StrEnum):
    """Enums representing the sources the companies crawl reads (`CRAWLER_SOURCE=companies`, `CRAWLER_TARGET`).

    Attributes:
        EDGAR (str): SEC EDGAR `companyfacts`, the statements filed in XBRL (10-K, 10-Q, 20-F, 40-F) since 2009.
        GOOGLE_FINANCE (str): Google Finance quote pages, the statements of the last 10 years and 8 quarters.
        GOOGLE_PATENTS (str): Google Patents search, every publication of the companies' assignees.
        GOOGLE_PATENT_PAGES (str): Google Patents publication pages, the citations, family and classes of each.
        OPENALEX (str): OpenAlex, the research papers of the companies' institutions and their authors.
        EDGAR_SCHEDULES (str): SEC EDGAR full submissions of 1993 to 2001, the financial data schedules (EX-27).
        REPORTED (str): The figures researched by hand from the annual reports (`data/curated/figures.json`),
            written without network.
        SEC_IDENTITY (str): SEC EDGAR's tickers and submissions, the filers of the listed companies (identity
            resolver).
        OPENALEX_IDENTITY (str): OpenAlex institutions, the company entries named as the companies (identity
            resolver).
        ASSIGNEE_IDENTITY (str): The assignees of the stored patents, the variants and homonyms of the companies'
            assignee searches (identity resolver, without network).
        FIGURE_CHECK (str): The documents the researched figures cite (SEC filings, archived pages), read to check
            that they state the figures.
    """

    EDGAR = "edgar-financials"
    GOOGLE_FINANCE = "gfinance-statements"
    GOOGLE_PATENTS = "google-patents"
    GOOGLE_PATENT_PAGES = "google-patents-pages"
    OPENALEX = "openalex"
    EDGAR_SCHEDULES = "edgar-schedules"
    REPORTED = "reported-figures"
    SEC_IDENTITY = "sec-identity"
    OPENALEX_IDENTITY = "openalex-identity"
    ASSIGNEE_IDENTITY = "assignee-identity"
    FIGURE_CHECK = "figure-check"


@unique
class FinancialSource(StrEnum):
    """Enums representing where a stored financial figure comes from.

    Attributes:
        EDGAR (str): The XBRL facts filed with the SEC.
        GOOGLE_FINANCE (str): The statements of Google Finance.
        EDGAR_FDS (str): The financial data schedules (EX-27) filed with the SEC from 1993 to 2001.
        REPORTED (str): A figure researched by hand from an annual report, a filing or the press, with its source.
    """

    EDGAR = "edgar"
    GOOGLE_FINANCE = "gfinance"
    EDGAR_FDS = "edgar-fds"
    REPORTED = "reported"


@unique
class FinancialGranularity(StrEnum):
    """Enums representing the period a financial figure or an indicator covers.

    Attributes:
        INSTANT (str): A balance at a date (an asset, a debt, the shares outstanding).
        WEEK (str): A week, dated by its last trading day (the market capitalisation and the enterprise value).
        QUARTER (str): A fiscal quarter, dated by its last day.
        YEAR (str): A fiscal year, dated by its last day (a calendar year for the patents and the papers).
        TTM (str): The trailing twelve months, the four quarters ending on the date.
    """

    INSTANT = "instant"
    WEEK = "week"
    QUARTER = "quarter"
    YEAR = "year"
    TTM = "ttm"


@unique
class FinancialNature(StrEnum):
    """Enums representing how a financial figure adds up over time.

    Attributes:
        FLOW (str): Earned or spent over a period (revenue, cash flow): quarters add up to the year.
        BALANCE (str): Held at a date (assets, debt): read at the end of each period.
        PER_SHARE (str): Divided by the shares (earnings per share): quarters do not add up exactly.
    """

    FLOW = "flow"
    BALANCE = "balance"
    PER_SHARE = "per-share"


@unique
class FinancialMetric(StrEnum):
    """Enums representing the statement lines read from the filings and from Google Finance.

    Attributes:
        REVENUE (str): The sales of the period.
        COST_OF_REVENUE (str): The cost of the goods and services sold.
        GROSS_PROFIT (str): The revenue less its cost.
        OPERATING_EXPENSES (str): The operating expenses (research, selling, general and administrative).
        RD_EXPENSE (str): The research and development expense.
        SGA_EXPENSE (str): The selling, general and administrative expense.
        OPERATING_INCOME (str): The operating income (the profit of the main activity).
        DEPRECIATION (str): The depreciation and amortization (added back to the operating income for the EBITDA).
        EBITDA (str): The earnings before interest, taxes, depreciation and amortization, as Google Finance states it.
        PRETAX_INCOME (str): The income before income taxes.
        INCOME_TAX (str): The income tax expense.
        NET_INCOME (str): The net income attributable to the shareholders.
        EPS_DILUTED (str): The diluted earnings per share.
        DILUTED_SHARES (str): The weighted average diluted shares of the period.
        TOTAL_ASSETS (str): The total assets.
        CURRENT_ASSETS (str): The current assets.
        CASH (str): The cash and cash equivalents.
        SHORT_TERM_INVESTMENTS (str): The short-term investments and marketable securities.
        RECEIVABLES (str): The accounts receivable.
        INVENTORY (str): The inventories.
        GOODWILL (str): The goodwill.
        INTANGIBLES (str): The intangible assets other than goodwill.
        TOTAL_LIABILITIES (str): The total liabilities.
        CURRENT_LIABILITIES (str): The current liabilities.
        ACCOUNTS_PAYABLE (str): The accounts payable.
        CURRENT_DEBT (str): The debt due within a year.
        LONG_TERM_DEBT (str): The debt due after a year.
        CURRENT_BONDS (str): The bonds due within a year, when filed apart from the borrowings (IFRS filers).
        NONCURRENT_BONDS (str): The bonds due after a year, when filed apart from the borrowings (IFRS filers).
        TOTAL_EQUITY (str): The equity of the shareholders.
        RETAINED_EARNINGS (str): The retained earnings (or accumulated deficit).
        SHARES_OUTSTANDING (str): The shares outstanding at a date.
        OPERATING_CASH_FLOW (str): The cash provided by the operating activities.
        INVESTING_CASH_FLOW (str): The cash used by the investing activities.
        FINANCING_CASH_FLOW (str): The cash used by the financing activities.
        CAPEX (str): The purchases of property, plant and equipment (a positive amount spent).
        DIVIDENDS_PAID (str): The dividends paid (a positive amount paid).
        BUYBACKS (str): The repurchases of the company's shares (a positive amount paid).
        FREE_CASH_FLOW (str): The free cash flow, as Google Finance states it (levered).
        CAPITALISED_DEVELOPMENT (str): The development costs entered as intangible assets (software included).
        MARKET_CAP (str): The market capitalisation at a date, as Google Finance's quote states it.
        INTEREST_EXPENSE (str): The interest expense of the period (a positive amount paid).
        EMPLOYEES (str): The employees at a date (a headcount, without currency).
        FUNDING_RAISED (str): The capital raised by a private company in a funding round, dated by the round.
        REVENUE_RUN_RATE (str): An annualized revenue a private company states at a date (not a fiscal year).
    """

    REVENUE = "revenue"
    COST_OF_REVENUE = "cost-of-revenue"
    GROSS_PROFIT = "gross-profit"
    OPERATING_EXPENSES = "operating-expenses"
    RD_EXPENSE = "rd-expense"
    SGA_EXPENSE = "sga-expense"
    OPERATING_INCOME = "operating-income"
    DEPRECIATION = "depreciation"
    EBITDA = "ebitda"
    PRETAX_INCOME = "pretax-income"
    INCOME_TAX = "income-tax"
    NET_INCOME = "net-income"
    EPS_DILUTED = "eps-diluted"
    DILUTED_SHARES = "diluted-shares"
    TOTAL_ASSETS = "total-assets"
    CURRENT_ASSETS = "current-assets"
    CASH = "cash"
    SHORT_TERM_INVESTMENTS = "short-term-investments"
    RECEIVABLES = "receivables"
    INVENTORY = "inventory"
    GOODWILL = "goodwill"
    INTANGIBLES = "intangibles"
    TOTAL_LIABILITIES = "total-liabilities"
    CURRENT_LIABILITIES = "current-liabilities"
    ACCOUNTS_PAYABLE = "accounts-payable"
    CURRENT_DEBT = "current-debt"
    LONG_TERM_DEBT = "long-term-debt"
    CURRENT_BONDS = "current-bonds"
    NONCURRENT_BONDS = "noncurrent-bonds"
    TOTAL_EQUITY = "total-equity"
    RETAINED_EARNINGS = "retained-earnings"
    SHARES_OUTSTANDING = "shares-outstanding"
    OPERATING_CASH_FLOW = "operating-cash-flow"
    INVESTING_CASH_FLOW = "investing-cash-flow"
    FINANCING_CASH_FLOW = "financing-cash-flow"
    CAPEX = "capex"
    DIVIDENDS_PAID = "dividends-paid"
    BUYBACKS = "buybacks"
    FREE_CASH_FLOW = "free-cash-flow"
    CAPITALISED_DEVELOPMENT = "capitalised-development"
    MARKET_CAP = "market-cap"
    INTEREST_EXPENSE = "interest-expense"
    EMPLOYEES = "employees"
    FUNDING_RAISED = "funding-raised"
    REVENUE_RUN_RATE = "revenue-run-rate"


@unique
class IndicatorFamily(StrEnum):
    """Enums representing the families of the indicators (the sections of the indicators note).

    Attributes:
        SIZE (str): The size and the value of the company.
        PROFITABILITY (str): Its profitability.
        SOLIDITY (str): Its cash and its financial solidity.
        RD_EFFORT (str): Its research and development effort (input).
        RD_OUTPUT (str): Its research and development results (output).
        RD_EFFICIENCY (str): The efficiency of its research and development.
        LIQUIDITY (str): Its ability to pay its short-term debts.
        GROWTH (str): The growth of its revenue, profit and research effort.
        SCORES (str): The composite scores of its financial strength (Altman, Piotroski).
        PRIVATE (str): The figures a private company makes public (funding, valuation, headcount, run-rate).
    """

    SIZE = "size"
    PROFITABILITY = "profitability"
    SOLIDITY = "solidity"
    RD_EFFORT = "rd-effort"
    RD_OUTPUT = "rd-output"
    RD_EFFICIENCY = "rd-efficiency"
    LIQUIDITY = "liquidity"
    GROWTH = "growth"
    SCORES = "scores"
    PRIVATE = "private"


@unique
class IndicatorUnit(StrEnum):
    """Enums representing the unit of an indicator.

    Attributes:
        CURRENCY (str): An amount in the company's reporting currency (its US-dollar value is stored beside it).
        RATIO (str): A ratio without unit (debt to equity, current ratio).
        PERCENT (str): A percentage (margins, returns, intensity).
        COUNT (str): A count (patents, papers, citations).
        SCORE (str): A composite score (Altman Z, Piotroski F), read against its own thresholds.
    """

    CURRENCY = "currency"
    RATIO = "ratio"
    PERCENT = "percent"
    COUNT = "count"
    SCORE = "score"


@unique
class CompanyIndicator(StrEnum):
    """Enums representing the indicators of a company's wealth and research effort, stored as time series.

    Attributes:
        REVENUE (str): The revenue.
        NET_INCOME (str): The net income.
        OPERATING_INCOME (str): The operating income.
        EBITDA (str): The EBITDA (operating income plus depreciation and amortization, or as Google states it).
        TOTAL_ASSETS (str): The total assets.
        TOTAL_EQUITY (str): The equity of the shareholders.
        MARKET_CAP (str): The market capitalisation (closing price times the shares outstanding).
        ENTERPRISE_VALUE (str): The market capitalisation plus the debt less the cash.
        GROSS_MARGIN (str): The gross profit over the revenue, in percent.
        OPERATING_MARGIN (str): The operating income over the revenue, in percent.
        NET_MARGIN (str): The net income over the revenue, in percent.
        ROE (str): The net income over the average equity, in percent.
        ROA (str): The net income over the average total assets, in percent.
        ROIC (str): The operating income after tax over the invested capital (equity plus debt less cash), percent.
        FREE_CASH_FLOW (str): The operating cash flow less the capital expenditure.
        CASH (str): The cash, cash equivalents and short-term investments.
        TOTAL_DEBT (str): The current and long-term debt.
        NET_DEBT (str): The total debt less the cash.
        DEBT_TO_EQUITY (str): The total debt over the equity.
        NET_DEBT_TO_EBITDA (str): The net debt over the EBITDA of the last twelve months.
        CURRENT_RATIO (str): The current assets over the current liabilities.
        QUICK_RATIO (str): The current assets less the inventories, over the current liabilities.
        RD_EXPENSE (str): The research and development expense.
        RD_INTENSITY (str): The research and development expense over the revenue, in percent.
        CAPITALISED_DEVELOPMENT (str): The development costs entered as intangible assets.
        RD_RETURN (str): The revenue growth over a year divided by the research expense of the year before.
        PATENT_FILINGS (str): The patent publications of the company by priority year (the first filing).
        PATENT_FAMILIES (str): The patent families of the company by the priority year of their first member.
        PATENT_GRANTS (str): The patents granted to the company in the year.
        PATENT_CITATIONS (str): The citations received by the company's patents of a priority year.
        CITATIONS_PER_PATENT (str): The citations received per patent of a priority year.
        PAPERS (str): The research papers of the company's researchers published in the year.
        PAPER_CITATIONS (str): The citations received by the papers of a publication year.
        PAPER_FWCI (str): The mean field-weighted citation impact of the papers of a publication year.
        REVENUE_GROWTH (str): The revenue growth over a year, in percent.
        NET_INCOME_GROWTH (str): The net income growth over a year, in percent (none after a loss).
        RD_GROWTH (str): The research and development expense growth over a year, in percent.
        INTEREST_COVERAGE (str): The operating income over the interest expense.
        CASH_CONVERSION (str): The free cash flow over the net income, in percent (none after a loss).
        WORKING_CAPITAL (str): The current assets less the current liabilities.
        PAYOUT_RATIO (str): The dividends and share repurchases over the net income, in percent.
        ALTMAN_Z (str): The 1968 Altman Z-score of a listed company (its market value over its liabilities).
        ALTMAN_Z_DOUBLE_PRIME (str): The 1995 Altman Z''-score, on book values, for every company.
        PIOTROSKI_F (str): The Piotroski F-score, from 0 to 9 (nine yearly tests of profit, leverage, efficiency).
        EMPLOYEES (str): The employees at a date.
        FUNDING_RAISED (str): The capital a private company raised in its funding rounds of the year.
        FUNDING_TOTAL (str): The capital a private company raised since its creation, at each round.
        VALUATION (str): The valuation of a company in a deal (a funding round, an acquisition), in US dollars.
        REVENUE_RUN_RATE (str): The annualized revenue a private company states at a date.
    """

    REVENUE = "revenue"
    NET_INCOME = "net-income"
    OPERATING_INCOME = "operating-income"
    EBITDA = "ebitda"
    TOTAL_ASSETS = "total-assets"
    TOTAL_EQUITY = "total-equity"
    MARKET_CAP = "market-cap"
    ENTERPRISE_VALUE = "enterprise-value"
    GROSS_MARGIN = "gross-margin"
    OPERATING_MARGIN = "operating-margin"
    NET_MARGIN = "net-margin"
    ROE = "roe"
    ROA = "roa"
    ROIC = "roic"
    FREE_CASH_FLOW = "free-cash-flow"
    CASH = "cash"
    TOTAL_DEBT = "total-debt"
    NET_DEBT = "net-debt"
    DEBT_TO_EQUITY = "debt-to-equity"
    NET_DEBT_TO_EBITDA = "net-debt-to-ebitda"
    CURRENT_RATIO = "current-ratio"
    QUICK_RATIO = "quick-ratio"
    RD_EXPENSE = "rd-expense"
    RD_INTENSITY = "rd-intensity"
    CAPITALISED_DEVELOPMENT = "capitalised-development"
    RD_RETURN = "rd-return"
    PATENT_FILINGS = "patent-filings"
    PATENT_FAMILIES = "patent-families"
    PATENT_GRANTS = "patent-grants"
    PATENT_CITATIONS = "patent-citations"
    CITATIONS_PER_PATENT = "citations-per-patent"
    PAPERS = "papers"
    PAPER_CITATIONS = "paper-citations"
    PAPER_FWCI = "paper-fwci"
    REVENUE_GROWTH = "revenue-growth"
    NET_INCOME_GROWTH = "net-income-growth"
    RD_GROWTH = "rd-growth"
    INTEREST_COVERAGE = "interest-coverage"
    CASH_CONVERSION = "cash-conversion"
    WORKING_CAPITAL = "working-capital"
    PAYOUT_RATIO = "payout-ratio"
    ALTMAN_Z = "altman-z"
    ALTMAN_Z_DOUBLE_PRIME = "altman-z-double-prime"
    PIOTROSKI_F = "piotroski-f"
    EMPLOYEES = "employees"
    FUNDING_RAISED = "funding-raised"
    FUNDING_TOTAL = "funding-total"
    VALUATION = "valuation"
    REVENUE_RUN_RATE = "revenue-run-rate"


@unique
class PatentWindowStatus(StrEnum):
    """Enums representing the state of a window of the patents search.

    Attributes:
        COMPLETE (str): Every publication the search counts was read.
        SPLIT (str): The window counted more publications than one query returns: its halves were searched instead.
        INCOMPLETE (str): The window could not be split further and was read only in part.
        PENDING (str): The window was counted but not read yet (the crawl stopped first).
    """

    COMPLETE = "complete"
    SPLIT = "split"
    INCOMPLETE = "incomplete"
    PENDING = "pending"


@unique
class PatentCitationKind(StrEnum):
    """Enums representing a citation read on a publication page.

    Attributes:
        CITES (str): The publication cites the other one (a backward citation).
        CITED_BY (str): The other publication cites this one (a forward citation).
        FAMILY_CITES (str): A member of the publication's family cites the other one.
        FAMILY_CITED_BY (str): The other publication cites a member of the family.
    """

    CITES = "cites"
    CITED_BY = "cited-by"
    FAMILY_CITES = "family-cites"
    FAMILY_CITED_BY = "family-cited-by"


@unique
class CompanyFactKind(StrEnum):
    """Enums representing the kind of a fact streamed by a companies crawler (the `kind` key of the item).

    Attributes:
        FINANCIAL (str): A figure of a statement (`FinancialFact`).
        PATENT (str): A publication returned by a patents search (`PatentRecord`).
        PATENT_DETAIL (str): What a publication page states (`PatentDetail`).
        PATENT_WINDOW (str): A window of the patents search, searched (`PatentWindow`).
        PAPER (str): A research paper (`PaperRecord`).
        RESEARCHER (str): The profile of a researcher (`ResearcherRecord`).
        PAPER_COUNT (str): The papers of a company in a year (`PaperYearCount`).
        IDENTITY (str): An identifier a resolver found for a company (`IdentityCandidate`).
        DOCUMENT_NUMBERS (str): The numbers a document cited by researched figures states (`DocumentNumbers`).
    """

    FINANCIAL = "financial"
    PATENT = "patent"
    PATENT_DETAIL = "patent-detail"
    PATENT_WINDOW = "patent-window"
    PAPER = "paper"
    RESEARCHER = "researcher"
    PAPER_COUNT = "paper-count"
    IDENTITY = "identity"
    DOCUMENT_NUMBERS = "document-numbers"


@unique
class FigureBasis(StrEnum):
    """Enums representing what a researched figure (`data/curated/figures.json`) was read from.

    Attributes:
        ANNUAL_REPORT (str): The company's annual report (or its yearly results release).
        FILING (str): A filing with a regulator (a 10-K selected data table, a stock exchange filing).
        PRESS (str): The press reporting the company's own figure.
        ESTIMATE (str): An estimate by a third party (the company publishes none): drawn apart, never mixed.
        RUN_RATE (str): An annualized figure the company states at a date, not a fiscal year.
    """

    ANNUAL_REPORT = "annual-report"
    FILING = "filing"
    PRESS = "press"
    ESTIMATE = "estimate"
    RUN_RATE = "run-rate"


@unique
class FigureScale(StrEnum):
    """Enums representing the unit the amounts of a researched company are written in.

    Attributes:
        UNITS (str): The amounts as they are.
        THOUSANDS (str): The amounts in thousands.
        MILLIONS (str): The amounts in millions.
        BILLIONS (str): The amounts in billions.
    """

    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


@unique
class StatementKind(StrEnum):
    """Enums representing the shape of a company's statements, which decides the health indicators that apply.

    Attributes:
        INDUSTRIAL (str): A company selling goods or services (every indicator applies).
        BANK (str): A bank: no current assets, no gross margin, deposits as liabilities (the scores do not apply).
    """

    INDUSTRIAL = "industrial"
    BANK = "bank"


@unique
class FinancialControl(StrEnum):
    """Enums representing the controls of the company financials card (explained in `conf/help.yaml`).

    Attributes:
        COMPANIES (str): The companies drawn.
        INDICATOR (str): The indicator drawn.
        PERIOD (str): The period of the points (year, quarter, trailing twelve months).
        CURRENCY (str): The currency of the amounts (the company's own, or US dollars).
        DERIVATIVE (str): The rate of change instead of the value.
    """

    COMPANIES = "companies"
    INDICATOR = "indicator"
    PERIOD = "period"
    CURRENCY = "currency"
    DERIVATIVE = "derivative"
