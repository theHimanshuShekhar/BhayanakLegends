export type AvatarTone = "plain" | "acc" | "red" | "enemy" | "teal";

export function avatar(
  initials: string,
  size: string,
  tone: AvatarTone = "plain"
): string {
  return `<div class="avatar-${tone} ${size}">${initials}</div>`;
}

export function bar(
  pct: number,
  tone: "teal" | "red" | "amber" | "acc" | "s3",
  extra = ""
): string {
  const fill: Record<string, string> = {
    teal: "bg-linear-to-r from-[#2f7f6d] to-rc-teal",
    red: "bg-linear-to-r from-[#7d3348] to-rc-red",
    amber: "bg-linear-to-r from-rc-amber to-[#f0d29c]",
    acc: "bg-linear-to-r from-rc-acc to-[#c9b8ff]",
    s3: "bg-rc-s3",
  };
  return `<div class="h-[7px] flex-1 overflow-hidden rounded-full bg-rc-deep shadow-[inset_0_2px_4px_rgba(0,0,0,.7)] ${extra}"><div class="h-full rounded-full ${fill[tone]}" style="width:${pct}%"></div></div>`;
}

export function track(extra = ""): string {
  return `<div class="h-[7px] overflow-hidden rounded-full bg-rc-deep shadow-[inset_0_2px_4px_rgba(0,0,0,.7)] ${extra}"></div>`;
}
