import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LiveStatus } from "../api/types";
import { useEvents } from "../api/sse";
import { usePack } from "../api/hooks";
import { pickHero } from "../components/champ-select/shared";
import { BanStrip } from "../components/champ-select/BanStrip";
import { YourLaneCard } from "../components/champ-select/YourLaneCard";
import { MasteryCard } from "../components/champ-select/MasteryCard";
import { HowToPlayCard } from "../components/champ-select/HowToPlayCard";
import { SuggestedPicks } from "../components/champ-select/SuggestedPicks";
import { CompReadCard } from "../components/champ-select/CompReadCard";
import { LoadoutCard } from "../components/champ-select/LoadoutCard";
import { BanAdvisorCard } from "../components/champ-select/BanAdvisorCard";
import { YourSideCard } from "../components/champ-select/YourSideCard";
import { MatchStartCard } from "../components/champ-select/MatchStartCard";

export function ChampSelectPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["live-status"],
    queryFn: api.liveStatus,
    refetchInterval: 3000,
  });
  const packQuery = usePack();

  // Poll is primary; SSE live.state frames update the same cache the moment
  // the sidecar pushes them (fallback when a poll window misses a transition).
  useEvents((msg) => {
    if (msg.type === "live.state") {
      queryClient.setQueryData<LiveStatus>(["live-status"], msg.data as LiveStatus);
    }
    if (msg.type === "pack.updated") {
      void queryClient.invalidateQueries({ queryKey: ["pack"] });
    }
  });

  const status = statusQuery.data;
  const active = status?.champ_select.active ?? false;
  const phase = status?.champ_select.phase ?? null;
  const hero = pickHero(packQuery.data);

  return (
    <div
      style={{ fontFamily: "var(--font-mono)", letterSpacing: "-.01em" }}
      data-testid="champ-select-page"
    >
      <BanStrip active={active} phase={phase} lastError={status?.last_error ?? null} />

      <div style={{ display: "grid", gridTemplateColumns: "368px 1fr 316px", gap: 14, paddingTop: 14 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 11, minHeight: 0 }}>
          <YourLaneCard />
          <MasteryCard pack={packQuery.data} />
          <HowToPlayCard />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <SuggestedPicks pack={packQuery.data} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, flex: 1, minHeight: 0 }}>
            <CompReadCard />
            <LoadoutCard />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <BanAdvisorCard pack={packQuery.data} />
          <YourSideCard active={active} phase={phase} />
          <MatchStartCard active={active} pick={hero?.champion} />
        </div>
      </div>
    </div>
  );
}
