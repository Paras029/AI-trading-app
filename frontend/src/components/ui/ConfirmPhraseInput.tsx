import { useState } from "react";
import clsx from "clsx";

interface ConfirmPhraseInputProps {
  phrase: string;
  onConfirm: () => void;
  disabled?: boolean;
  pending?: boolean;
  buttonLabel: string;
  buttonClassName?: string;
}

export function ConfirmPhraseInput({
  phrase,
  onConfirm,
  disabled = false,
  pending = false,
  buttonLabel,
  buttonClassName,
}: ConfirmPhraseInputProps) {
  const [text, setText] = useState("");
  const matches = text === phrase;

  return (
    <div className="space-y-2">
      <p className="text-xs font-mono bg-white border border-stone-200 rounded px-2 py-1 text-stone-700">
        {phrase}
      </p>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type confirmation phrase"
        disabled={disabled}
        className="w-full border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-200 disabled:opacity-50"
      />
      <button
        onClick={() => {
          onConfirm();
          setText("");
        }}
        disabled={!matches || disabled || pending}
        className={clsx(
          "w-full px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors",
          buttonClassName ?? "bg-red-600 text-white hover:bg-red-700"
        )}
      >
        {buttonLabel}
      </button>
    </div>
  );
}
