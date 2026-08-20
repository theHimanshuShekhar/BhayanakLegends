export interface Chip {
  initials: string;
  name: string;
  sub: string;
  you?: boolean;
  enemyLane?: boolean;
  dim?: boolean;
}

export interface Tip {
  phase: string;
  phaseTone: "teal" | "amber" | "blue";
  text: string;
}

export interface PickCard {
  initials: string;
  name: string;
  sub: string;
  vs: string;
  vsTone: "teal" | "red";
  tag: string;
  tagTone: "neutral" | "amber";
  note: string;
  dim?: boolean;
}

export interface CompBar {
  label: string;
  value: string;
  pct: number;
  tone: "amber" | "teal" | "red";
}

export interface StatCard {
  label: string;
  delta: string;
  deltaTone: "teal" | "red";
  value: string;
  valueTone?: "teal" | "red";
  barPct: number;
  barTone: "teal" | "red";
  markPct: number;
  benchmark: string;
}

export interface PlayerLine {
  initials: string;
  name: string;
  stats: string;
  level: number;
  you?: boolean;
}

export interface SummonerRow {
  initials: string;
  name: string;
  spells: { label: string; tone: "blue" | "neutral" | "amber" }[];
  iconTone: "red" | "plain";
}

export interface CdRow {
  initials: string;
  name: string;
  iconTone: "red" | "plain";
  a: { label: string; tone: "teal" | "red" };
  b: { label: string; tone: "neutral" | "teal" | "amber" };
}

export interface ObjRow {
  name: string;
  sub: string;
  time: string;
  hot?: boolean;
}

export interface Drill {
  title: string;
  sub: string;
  state: "done" | "focus" | "todo";
}

export interface PoolRow {
  initials: string;
  name: string;
  games: string;
  wr: string;
  wrTone: "teal" | "neutral" | "red";
}

export interface GameRow {
  champ: string;
  role: string;
  score: string;
  lp: string;
  result: "win" | "loss";
}

export const summoner = "vexlily #euw";
export const rank = "Emerald II · 47 LP";

export const draft = {
  timer: "0:24",
  phase: "PICK PHASE",
  phasePct: 62,
  allies: [
    { initials: "OR", name: "Ornn", sub: "M7 · 118g" },
    { initials: "VI", name: "Viego", sub: "M5 · 64g" },
    { initials: "YOU", name: "Picking…", sub: "Mid · 0:24", you: true },
    { initials: "JH", name: "Jhin", sub: "M6 · 71g" },
    { initials: "?", name: "Support", sub: "choosing", dim: true },
  ] as Chip[],
  enemies: [
    { initials: "KS", name: "K'Sante", sub: "M4 · 52g" },
    { initials: "LI", name: "Lillia", sub: "M3 · 29g" },
    {
      initials: "SY",
      name: "Syndra",
      sub: "M7 · 214g · lane",
      enemyLane: true,
    },
    { initials: "KA", name: "Kai'Sa", sub: "M6 · 88g" },
    { initials: "RA", name: "Rakan", sub: "M5 · 41g" },
  ] as Chip[],
};

export const lane = {
  enemyInitials: "SY",
  enemyName: "Syndra",
  enemySub: "Mastery 7 · 214 games · 56% WR",
  youWin: "43%",
  sampled: "247 games sampled",
  pills: [
    { label: "Outranges you", tone: "red" },
    { label: "Lvl 6 burst", tone: "amber" },
    { label: "Weak to dives", tone: "neutral" },
  ],
  tips: [
    {
      phase: "Early",
      phaseTone: "teal",
      text: "Shove waves 1–3. She has to walk up to farm and her Q is her only safe answer — punish the second she steps past the minion line.",
    },
    {
      phase: "Mid",
      phaseTone: "amber",
      text: "From level 6 she one-shots you at 3 spheres. Count them. Buy the early Null-Magic Mantle over the second Dorans.",
    },
    {
      phase: "Late",
      phaseTone: "blue",
      text: "Never sidelane alone against her. Group, and make her use ult on your frontline before you commit.",
    },
  ] as Tip[],
};

export const picks = {
  hero: {
    initials: "TA",
    name: "Taliyah",
    vsLabel: "VS SYNDRA",
    vsValue: "57%",
    yourLabel: "YOUR WR",
    yourValue: "58%",
    reason:
      "Matches her range, and your team has no wave clear. You've played her 34 times this season at 58%.",
  },
  cards: [
    {
      initials: "OR",
      name: "Orianna",
      sub: "M5 · 22 games",
      vs: "53% vs",
      vsTone: "teal",
      tag: "Safe",
      tagTone: "neutral",
      note: "Even lane, but shield + ult fits the Ornn engage.",
    },
    {
      initials: "FI",
      name: "Fizz",
      sub: "M4 · 9 games",
      vs: "61% vs",
      vsTone: "teal",
      tag: "Low games",
      tagTone: "amber",
      note: "Hard counter on paper — you've only played 9. Risky.",
    },
    {
      initials: "AH",
      name: "Ahri",
      sub: "M7 · 61 games",
      vs: "44% vs",
      vsTone: "red",
      tag: "Comfort",
      tagTone: "neutral",
      note: "Your most-played, but she out-trades you pre-6.",
      dim: true,
    },
  ] as PickCard[],
};

export const comp = {
  pill: "Frontline heavy",
  bars: [
    { label: "Damage mix", value: "72% AD / 28% AP", pct: 72, tone: "amber" },
    { label: "Engage", value: "Strong", pct: 81, tone: "teal" },
    { label: "Scaling", value: "Weak", pct: 34, tone: "red" },
  ] as CompBar[],
  note: "You're the only AP threat. An AD pick here makes them build one item and ignore your whole team.",
};

export const build = {
  pill: "54% · 2.1k",
  advice: "Swap boots to Mercury's Treads — 3 of their 5 deal magic damage.",
  keystone: "Electrocute",
  secondary: "Inspiration",
  slots: 6,
  accSlot: 3,
};

export const enemySummoners = {
  rows: [
    {
      initials: "SY",
      name: "Syndra",
      iconTone: "red",
      spells: [
        { label: "Flash", tone: "blue" },
        { label: "TP", tone: "neutral" },
      ],
    },
    {
      initials: "LI",
      name: "Lillia",
      iconTone: "plain",
      spells: [
        { label: "Flash", tone: "blue" },
        { label: "Smite", tone: "neutral" },
      ],
    },
    {
      initials: "RA",
      name: "Rakan",
      iconTone: "plain",
      spells: [
        { label: "Flash", tone: "blue" },
        { label: "Ignite", tone: "amber" },
      ],
    },
  ] as SummonerRow[],
  note: "Tracker goes live at the loading screen and counts down from every use.",
};

export const objectives = {
  rows: [
    {
      name: "First grubs",
      sub: "Ornn + Viego want you shoving at 4:30.",
      time: "5:00",
      hot: true,
    },
    { name: "First drake", sub: "spawn window.", time: "14:00" },
    { name: "Baron", sub: "your comp wants it early.", time: "20:00" },
  ] as ObjRow[],
};

export const bans = 6;

export const live = {
  timer: "14:22",
  gold: "+2.4k gold",
  kills: "13 — 9 KILLS",
  goldPct: 58,
  allies: [
    { initials: "OR", name: "Ornn", stats: "1/2/7 · 118cs", level: 11 },
    { initials: "VI", name: "Viego", stats: "4/3/4 · 89cs", level: 10 },
    {
      initials: "TA",
      name: "Taliyah",
      stats: "5/2/6 · 142cs",
      level: 12,
      you: true,
    },
    { initials: "JH", name: "Jhin", stats: "3/4/5 · 131cs", level: 11 },
    { initials: "NA", name: "Nautilus", stats: "0/5/9 · 22cs", level: 9 },
  ] as PlayerLine[],
  enemies: [
    { initials: "KS", name: "K'Sante", stats: "2/3/3 · 124cs", level: 11 },
    { initials: "LI", name: "Lillia", stats: "1/4/5 · 96cs", level: 10 },
    {
      initials: "SY",
      name: "Syndra",
      stats: "4/2/4 · 151cs",
      level: 13,
      enemyLane: true,
    },
    { initials: "KA", name: "Kai'Sa", stats: "2/2/3 · 138cs", level: 11 },
    { initials: "RA", name: "Rakan", stats: "0/3/8 · 19cs", level: 9 },
  ] as (PlayerLine & { enemyLane?: boolean })[],
  laneNote:
    "She's 9 CS and a level up. Her wave is pushing to you — take the free farm instead of contesting river.",
  laneStats: [
    { label: "CS", you: 142, them: 151, youTone: "red", themTone: "red" },
    {
      label: "GOLD",
      you: "9.1k",
      them: "8.4k",
      youTone: "teal",
      themTone: "neutral",
    },
    { label: "LEVEL", you: 12, them: 13, youTone: "neutral", themTone: "red" },
  ],
  tips: [
    {
      phase: "Now",
      phaseTone: "acc",
      text: "Drake in 0:47 and their jungler just showed top. Push mid to the tower, then rotate — you'll arrive before she does.",
    },
    {
      phase: "Watch",
      phaseTone: "amber",
      text: "Syndra hit her second item. She now one-shots Jhin from 900 units. Warn him before the fight.",
    },
    {
      phase: "Good",
      phaseTone: "teal",
      text: "You've survived the 10–15 window clean this game. That's your leak — keep doing exactly this.",
    },
  ] as Tip[],
  goldChart: {
    points:
      "0,66 55,72 110,80 165,74 220,62 275,68 330,54 385,58 440,44 495,50 550,34 605,30 660,22",
  },
  team: {
    bars: [
      {
        label: "DAMAGE",
        you: "48.2k",
        them: "41.6k",
        youPct: 54,
        themPct: 46,
        youTone: "teal",
      },
      {
        label: "TOWERS",
        you: 5,
        them: 3,
        youPct: 62,
        themPct: 38,
        youTone: "teal",
      },
      {
        label: "WARDS PLACED",
        you: 18,
        them: 27,
        youPct: 40,
        themPct: 60,
        youTone: "neutral",
        themTone: "red",
      },
    ],
    boxes: [
      { label: "DRAKES", value: 2, tone: "teal" },
      { label: "HERALD", value: 1, tone: "neutral" },
      { label: "GRUBS", value: 4, tone: "red" },
    ],
  },
  power: {
    pill: "Fight now",
    note: "Your comp peaks right now. Past 22 minutes their scaling passes you — force the next objective.",
    youPoints: "0,74 50,58 100,40 150,32 200,36 250,46 300,54",
    themPoints: "0,80 50,72 100,62 150,50 200,34 250,20 300,10",
  },
  damage: [
    { initials: "TA", name: "Taliyah", pct: 84, value: "16.2k", you: true },
    { initials: "JH", name: "Jhin", pct: 72, value: "13.9k" },
    { initials: "VI", name: "Viego", pct: 53, value: "10.1k" },
    { initials: "OR", name: "Ornn", pct: 31, value: "5.9k" },
    { initials: "NA", name: "Nautilus", pct: 11, value: "2.1k" },
  ],
  objTimers: [
    {
      name: "Ocean Drake",
      sub: "3rd stack — soul point",
      time: "0:47",
      hot: true,
    },
    { name: "Baron Nashor", sub: "spawns 20:00", time: "5:38" },
    { name: "Enemy blue", sub: "taken 12:41", time: "2:19" },
  ] as ObjRow[],
  cds: [
    {
      initials: "SY",
      name: "Syndra",
      iconTone: "red",
      a: { label: "Flash up", tone: "teal" },
      b: { label: "TP 1:12", tone: "neutral" },
    },
    {
      initials: "LI",
      name: "Lillia",
      iconTone: "plain",
      a: { label: "Flash 3:04", tone: "red" },
      b: { label: "Smite", tone: "teal" },
    },
    {
      initials: "RA",
      name: "Rakan",
      iconTone: "plain",
      a: { label: "Flash 4:41", tone: "red" },
      b: { label: "Ignite", tone: "amber" },
    },
  ] as CdRow[],
  build: {
    gold: "1,240g",
    slots: 6,
    filled: 3,
    advice:
      "Buy Zhonya's next, not Rabadon's — Syndra's ult is the only thing killing you.",
    deaths: "2 · below your average",
  },
};

export const progress = {
  rank: {
    tier: "Emerald II",
    lp: "47 LP · +112 this month",
    pct: 47,
  },
  history: {
    points:
      "0,104 62,96 124,101 186,82 248,86 310,64 372,71 434,48 496,55 558,32 620,26",
    months: ["MAR", "APR", "MAY", "JUN", "JUL", "AUG"],
  },
  stats: [
    {
      label: "CS / MIN",
      delta: "−1.1",
      deltaTone: "red",
      value: "5.4",
      valueTone: "red",
      barPct: 54,
      barTone: "red",
      markPct: 72,
      benchmark: "Emerald average 6.5",
    },
    {
      label: "KDA",
      delta: "+0.4",
      deltaTone: "teal",
      value: "3.1",
      barPct: 74,
      barTone: "teal",
      markPct: 65,
      benchmark: "Emerald average 2.7",
    },
    {
      label: "VISION / MIN",
      delta: "−0.3",
      deltaTone: "red",
      value: "0.6",
      valueTone: "red",
      barPct: 41,
      barTone: "red",
      markPct: 62,
      benchmark: "Emerald average 0.9",
    },
    {
      label: "DMG SHARE",
      delta: "+4%",
      deltaTone: "teal",
      value: "28%",
      barPct: 78,
      barTone: "teal",
      markPct: 67,
      benchmark: "Emerald average 24%",
    },
  ] as StatCard[],
  weakness: {
    cols: [
      { label: "0-5", pct: 18 },
      { label: "5-10", pct: 34 },
      { label: "10-15", pct: 92, hot: true },
      { label: "15-20", pct: 58 },
      { label: "20-25", pct: 44 },
      { label: "25+", pct: 30 },
    ],
    text: "You die most between 10 and 15 minutes — 2.4 deaths a game, nearly double the Emerald average. It's the window where lane phase ends and you keep farming your lane alone while the map rotates.",
  },
  roles: [
    { label: "Mid", pct: 68, wr: "54% WR", tone: "acc" },
    { label: "Bot", pct: 19, wr: "47% WR", tone: "s3" },
    { label: "Support", pct: 13, wr: "61% WR", tone: "s3" },
  ],
  roleTip:
    "Your best win rate is the role you almost never queue. Worth ten games.",
  drills: [
    {
      title: "Ward before you shove",
      sub: "Done in 4 of your last 5 games.",
      state: "done",
    },
    {
      title: "Recall at 11:00, not 13:00",
      sub: "Reset before the mid-game window opens.",
      state: "focus",
    },
    {
      title: "Hit 70 CS by 10 minutes",
      sub: "You're averaging 54. Three games running.",
      state: "todo",
    },
  ] as Drill[],
  pool: [
    {
      initials: "AH",
      name: "Ahri",
      games: "61 games",
      wr: "56%",
      wrTone: "teal",
    },
    {
      initials: "TA",
      name: "Taliyah",
      games: "34 games",
      wr: "58%",
      wrTone: "teal",
    },
    {
      initials: "OR",
      name: "Orianna",
      games: "22 games",
      wr: "49%",
      wrTone: "neutral",
    },
    {
      initials: "FI",
      name: "Fizz",
      games: "9 games",
      wr: "33%",
      wrTone: "red",
    },
  ] as PoolRow[],
  recent: {
    record: "12W · 8L",
    games: [
      {
        champ: "Taliyah · Mid",
        score: "9 / 2 / 11 · 28:41",
        lp: "+21",
        result: "win",
      },
      {
        champ: "Ahri · Mid",
        score: "4 / 7 / 6 · 31:02",
        lp: "−17",
        result: "loss",
      },
      {
        champ: "Ahri · Mid",
        score: "7 / 3 / 9 · 24:55",
        lp: "+19",
        result: "win",
      },
      {
        champ: "Orianna · Mid",
        score: "2 / 6 / 12 · 35:18",
        lp: "−18",
        result: "loss",
      },
    ] as GameRow[],
  },
};
