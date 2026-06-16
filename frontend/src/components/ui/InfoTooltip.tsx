export function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="relative group inline-flex items-center ml-1 align-middle">
      <span className="w-3.5 h-3.5 rounded-full bg-stone-200 text-stone-500 text-[9px] flex items-center justify-center cursor-help select-none font-medium">
        ?
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block w-60 text-xs bg-stone-800 text-white rounded-lg p-2.5 z-50 leading-relaxed shadow-xl">
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-stone-800" />
      </span>
    </span>
  );
}
