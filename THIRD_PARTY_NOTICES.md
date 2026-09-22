# Third-party notices

This project studies and adapts architectural patterns from open-source A-share tooling.

## A-Stock-Skills
- Upstream: https://github.com/ZICXR/A-Stock-Skills
- License: MIT
- Reused/adapted concepts: Agent Skill packaging, multi-source quote fallback, normalized market-data schema, health checks, retry/failure transparency.
- We do not blindly mirror the upstream trading-signal logic; the local regime/risk/position decision engine is independently implemented.

When substantial upstream code is incorporated later, its MIT copyright and permission notice must be retained with the relevant code/distribution.

## Tushare Skills
- Upstream: https://github.com/waditu-tushare/skills
- Used as an API/workflow reference only unless licensing is explicitly verified for the exact material being incorporated.
