# Upstream evaluation

We intentionally **adapt rather than blindly fork**.

## Evaluated upstreams

- ZICXR/A-Stock-Skills: strongest fit for A-share Skill layout and multi-source market-data patterns.
- waditu-tushare/skills: strong Tushare natural-language/data-interface reference; useful as optional historical/fundamental provider.
- sfeng49/ashare-agent: useful principles around explicit data failure and analysis-only workflow.

## Reuse policy

Reuse/adapt:
- provider fallback patterns
- normalized quote schema
- retries/rate-limit/health concepts
- Skill packaging conventions
- public-data failure transparency

Keep custom:
- regime classifier
- multi-factor score
- HH/HL and false-breakout logic
- core vs T-position state
- concentration risk gate
- compact action card
- later walk-forward validation

Do not copy upstream indicator-vote buy/sell logic directly. Our decision engine must be regime-first and position-aware.

## License/provenance

Before copying any substantial upstream implementation verbatim, verify its license and retain attribution. Prefer clean local implementations of the patterns we need.
