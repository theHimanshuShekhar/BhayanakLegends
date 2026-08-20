export function renderPlaceholder(title: string, note: string): string {
  return `<div class="view-enter flex flex-1 flex-col items-center justify-center gap-4">
    <div class="rounded-2xl bg-rc-s1 px-10 py-12 text-center shadow-z2 ring-1 ring-rc-line">
      <div class="section-title mb-2">${title}</div>
      <p class="max-w-[340px] text-[12px] leading-[1.6] text-rc-dim">${note}</p>
      <div class="mt-5 flex justify-center"><span class="pill-acc">Coming with live data</span></div>
    </div>
  </div>`;
}
