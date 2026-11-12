# 06 · News Fusion and Sentiment Factors

## Why this line started

To enhance signal quality by incorporating news sentiment data alongside technical indicators.

## Frozen scope

- Markets: US and CN_A
- Data source: News sentiment signals (external provider or simulated)
- Integration: News factor as optional signal component
- Fusion method: Weighted combination with technical signals

## Research flow

1. Define news sentiment schema and data contract
2. Implement news factor calculation module
3. Integrate news factor into signal generation pipeline
4. Test news-enhanced signals against baseline
5. Preserve news as optional feature with quality validation

## Key decisions and ideas

- News factor is optional; missing news data does not break the pipeline
- News weight can be zero for symbols with insufficient coverage
- Sentiment scores are normalized and bounded
- News fusion adds complexity; only use when coverage is adequate

## Result

News factor integration completed and tested. News-enhanced signals are available as an optional branch. The feature remains research-optional and is not required for production operation.

## Gate and current status

Status: `completed`. News fusion integrated as optional research feature.

## Source files

- Planning: `document/news_sentiment_schema.md` (if exists)
- Code: `core/news_factor.py`
- Tests: `tests/test_news_factor.py`

## Reproduction boundary

News-enhanced strategy variants are evaluated through ablation studies. Missing news coverage results in explicit fallback, not synthetic data.
