import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FindingsPackV2 } from "../../api/pack-v2";
import type { InGameSnapshot } from "../../api/types";
import { WinProbabilityCard } from "./WinProbabilityCard";

const readyPack = {
  feature_contracts: { models: { live_wp: "live-wp-v2" } },
  models: {
    live_wp: {
      release_status: "available",
      artifact: {},
      model_card: {},
    },
  },
} as unknown as FindingsPackV2;

const inference: InGameSnapshot["inference"] = {
  status: "available",
  probability: 0.5,
  observed_game_time_s: 30,
  model_version: "fixture-live-v1",
  pack_version: "fixture-pack-v1",
  reason: null,
};

describe("WinProbabilityCard event deltas", () => {
  it("renders an exact zero movement instead of an unavailable label", () => {
    render(
      <WinProbabilityCard
        pack={readyPack}
        clockS={30}
        active
        packVersion="fixture-pack-v1"
        inference={inference}
        eventDeltas={[
          {
            event_id: "0:TurretKilled:20",
            source_order: 0,
            name: "TurretKilled",
            t_s: 20,
            baseline_probability: 0.5,
            event_probability: 0.5,
            delta_probability: 0,
            pre_observed_game_time_s: 10,
            post_observed_game_time_s: 30,
            model_version: "fixture-live-v1",
            pack_version: "fixture-pack-v1",
            suppression_status: "available",
            reason: null,
          },
        ]}
      />,
    );

    expect(screen.getByTestId("wp-event-deltas")).toHaveTextContent("+0.0 pp");
    expect(screen.getByTestId("wp-event-deltas")).not.toHaveTextContent("Unavailable");
  });

  it("keeps a suppressed supported event visibly unavailable", () => {
    render(
      <WinProbabilityCard
        pack={readyPack}
        clockS={30}
        active
        packVersion="fixture-pack-v1"
        inference={inference}
        eventDeltas={[
          {
            event_id: "0:DragonKill:20",
            source_order: 0,
            name: "DragonKill",
            t_s: 20,
            baseline_probability: null,
            event_probability: null,
            delta_probability: null,
            pre_observed_game_time_s: null,
            post_observed_game_time_s: 30,
            model_version: "fixture-live-v1",
            pack_version: "fixture-pack-v1",
            suppression_status: "suppressed",
            reason: "exact pre/post live vectors unavailable",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("wp-event-deltas")).toHaveTextContent(
      "Unavailable: exact pre/post live vectors unavailable",
    );
    expect(screen.getByTestId("wp-event-deltas")).not.toHaveTextContent("+0.0 pp");
  });
});
