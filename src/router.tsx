import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";
import type { ReactElement } from "react";
import { Layout } from "./components/Layout";
import { ChampSelectPage } from "./routes/champ-select";
import { LiveMatchPage } from "./routes/live-match";
import { PostGamePage } from "./routes/postgame";
import { ProgressPage } from "./routes/progress";
import { ChampionsPage } from "./routes/champions";
import { HistoryPage } from "./routes/history";

const rootRoute = createRootRoute({
  component: () => (
    <Layout>
      <Outlet />
    </Layout>
  ),
});

function page(path: string, component: () => ReactElement) {
  return createRoute({ getParentRoute: () => rootRoute, path, component });
}

const champSelectRoute = page("/champ-select", ChampSelectPage);
const liveRoute = page("/live", LiveMatchPage);
const postgameRoute = page("/postgame", PostGamePage);
const progressRoute = page("/progress", ProgressPage);
const championsRoute = page("/champions", ChampionsPage);
const historyRoute = page("/history", HistoryPage);

const indexRoute = page("/", LiveMatchPage);

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    champSelectRoute,
    liveRoute,
    postgameRoute,
    progressRoute,
    championsRoute,
    historyRoute,
  ]),
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
