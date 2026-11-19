import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

export function InfoTooltip({ title, children, position = 'bottom' }) {
  const [open, setOpen] = useState(false);

  const posClasses =
    position === 'top'
      ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
      : 'top-full mt-2 left-1/2 -translate-x-1/2';

  const arrowClasses =
    position === 'top'
      ? 'top-full left-1/2 -translate-x-1/2 border-t-brand-navy'
      : 'bottom-full left-1/2 -translate-x-1/2 border-b-brand-navy';

  return (
    <span
      className="relative inline-flex items-center ml-1 align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={(e) => {
        e.stopPropagation();
        setOpen((v) => !v);
      }}
    >
      <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-brand-sky cursor-help transition" />
      {open && (
        <div
          className={`absolute ${posClasses} z-50 w-64 bg-brand-navy text-white text-[11px] font-normal leading-relaxed rounded-xl p-3 shadow-2xl border border-slate-700 whitespace-normal text-left pointer-events-none`}
        >
          {title && <div className="font-bold text-brand-sky mb-1">{title}</div>}
          <div className="text-slate-200 space-y-1">{children}</div>
          <div className={`absolute ${arrowClasses} border-4 border-transparent`} />
        </div>
      )}
    </span>
  );
}
