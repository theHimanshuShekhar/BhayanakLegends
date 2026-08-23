# Each installation uses its own Riot personal API key

Distribution stays friends-only, which is exactly Riot's sanctioned use case for personal API keys ("small private community"): permanent keys, no production application required. Every user registers their own free personal key on the Riot developer portal and pastes it into settings once; rate limits (20 req/s, 100/2 min) are therefore per-user, and no key is a shared secret. Development uses a `.env` file (gitignored); release installs store the key via Windows DPAPI / Credential Manager.

## Constraints this records

- LCU and Live Client Data need no key; only match-history sync consumes the user's key.
- Compliance guardrails honored by the product: no enemy summoner names displayed in ranked champ select; no enemy ability/ult timers (Riot policy, March 2025).
- If distribution ever outgrows the friend group, a production-key application becomes mandatory before anything resembling public consumption.
