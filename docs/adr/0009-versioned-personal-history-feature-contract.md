# Personal History parity-v2 feature contract

Status: Accepted; supersedes ADR-0001 and the earlier Personal History
contract wording.

ADR-0001 selected the `loltrends` package as the app's extraction library, but
LoLTrends does not currently publish an installable wheel. Waiting for that
wheel would block the companion app even though the app needs only a bounded,
well-defined checkpoint subset and already keeps population findings in the
Findings Pack. The app therefore owns a small extractor for this subset. The
implementation is replaceable only when the replacement preserves this
contract or publishes a new contract version.

The application has one storage and feature shape: the v2 schema and
`loltrends-parity-v2` feature contract. Database initialization creates only
that shape. The current definitions are the only supported definitions; fields
with different semantics are not interchangeable.

## Normative contract: `loltrends-parity-v2`

The v2 extractor emits the following Personal History feature fields. A
required observation that is absent, malformed, ambiguous, or outside its
observation horizon produces `null`; a proxy or a value from a differently
defined feature is never substituted.

| App field | Unit | Definition |
| --- | --- | --- |
| `cs10` | minion kills | At 10 minutes, `minionsKilled + jungleMinionsKilled` for the local participant. Missing counters count as zero. |
| `level10` | champion levels | The local participant's level at 10 minutes. A missing level counts as zero. |
| `gold_diff_10` | gold | Local `totalGold` minus the median `totalGold` of every participant in the selected 10-minute frame; non-numeric gold is excluded from the median pool. |
| `team_gold_diff_15m` | gold | Local team total gold minus the opposing team total gold in the selected 15-minute frame. All ten participants and two five-player teams are required. |
| `recalls_before_15m` | recalls | Count of conservative fountain-arrival observations before 15 minutes. |
| `avg_banked_gold_at_recall_by_15m` | gold | Mean `currentGold` at those pre-15-minute recall arrivals; unavailable when any selected arrival value is missing or has an ordering-ambiguous purchase event. |
| `avg_banked_gold_at_recall_by_20m` | gold | Mean `currentGold` at all conservative recall arrivals before 20 minutes, with the same missing-data rule. |
| `unseen_recall_share_by_15m` | share | Fraction of pre-15-minute recall arrivals with no enemy observed within the configured proximity threshold; unavailable when enemy visibility is unknown for any selected arrival. |
| `unseen_recall_share_by_20m` | share | Fraction of pre-20-minute recall arrivals with no enemy observed within the configured proximity threshold; unavailable when enemy visibility is unknown for any selected arrival. |
| `first_dragon_by_20m_s` | seconds | Timestamp of the first local-team `DRAGON` elite-monster kill at or before 20 minutes. |
| `first_riftherald_by_20m_s` | seconds | Timestamp of the first local-team `RIFTHERALD` elite-monster kill at or before 20 minutes. |
| `first_baron_by_20m_s` | seconds | Timestamp of the first local-team `BARON_NASHOR` elite-monster kill at or before 20 minutes. |
| `smite_contests_before_15m` | contests | Unavailable because match-v5 timelines do not provide contest provenance. |
| `smite_contests_before_20m` | contests | Unavailable because match-v5 timelines do not provide contest provenance. |
| `early_fight_participation_rate` | share | Local participation in early fight groups divided by the number of groups. Groups join kills no more than 10 seconds apart and within 4,000 map units; the horizon is before 14 minutes. |
| `plates_taken_by_14m` | plates | Turret plates destroyed by the local participant at or before 14 minutes. Only TOP, MIDDLE, and BOTTOM lane roles qualify. |

## Observation and eligibility rules

Ten-minute values use the latest populated frame at or before 600 seconds, but
a populated frame at or after 600 seconds must first prove that the timeline
reached the checkpoint. `team_gold_diff_15m` uses the same rule at 900
seconds and requires every participant snapshot to contain numeric gold.
Pre-20-minute recall and objective features require a populated frame at or
after 1,200 seconds; the final available frame is never used as a horizon
proxy.

Recall observations require a usable event stream, complete participant
identity and team data, a transition from outside the fountain radius to
inside it, a bounded frame gap, and no intervening respawn or teleport. Event
arrays that are absent, malformed, or ambiguous with respect to an emitted
feature withhold that feature rather than becoming an empty stream.

Personal History eligibility is independently determined from match detail:
Classic map 11 queues (400, 420, 440, 490, or 700), at least 300 seconds,
and no early surrender. Unknown eligibility remains unknown metadata; it never
becomes a fabricated eligibility result.

## Contract boundaries

`backend/src/bhayanak_legends/extract_v2.py` is pure and emits only the
current feature names above, plus match identity and contract metadata. The
Findings Pack may join a personal value only when its declared
`feature_contract` names the matching `loltrends-parity-v2` definition.
Similar names with different units, checkpoints, or populations are not
interchangeable.

A definition, formula, unit, checkpoint, or missing-data rule change requires
a new contract version and coordinated fixture and consumer updates. Every
consumer must reject an undeclared or mismatched contract instead of guessing
which definition was intended.

## Consequences

- ADR-0001's package dependency is not a prerequisite for app startup; the
  extractor remains intentionally small and auditable.
- Feature joins stay inside the declared v2 subset. New features require an
  explicit contract entry and independent expected outputs.
- Post-game habits are emitted only when an exact extractor and threshold
  exist. When one is unavailable, the digest carries no habit row and the UI
  says outcomes are unavailable; it never fabricates a verdict.
- ADR-0003's tier and phrasing discipline is unchanged: this decision changes
  feature provenance and definitions, not wording rules for findings.
