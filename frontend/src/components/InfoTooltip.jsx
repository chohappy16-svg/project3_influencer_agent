import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

export function InfoTooltip({ title, children, position = 'bottom', align = 'center' }) {
  const [open, setOpen] = useState(false);

  const vertClasses = position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2';
  const horizClasses =
    align === 'left' ? 'left-0' : align === 'right' ? 'right-0' : 'left-1/2 -translate-x-1/2';

  const arrowVert = position === 'top' ? 'top-full border-t-brand-navy' : 'bottom-full border-b-brand-navy';
  const arrowHoriz =
    align === 'left' ? 'left-2' : align === 'right' ? 'right-2' : 'left-1/2 -translate-x-1/2';

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
          className={`absolute ${vertClasses} ${horizClasses} z-50 w-64 bg-brand-navy text-white text-[11px] font-normal leading-relaxed rounded-xl p-3 shadow-2xl border border-slate-700 whitespace-normal text-left pointer-events-none`}
        >
          {title && <div className="font-bold text-brand-sky mb-1">{title}</div>}
          <div className="text-slate-200 space-y-1">{children}</div>
          <div className={`absolute ${arrowVert} ${arrowHoriz} border-4 border-transparent`} />
        </div>
      )}
    </span>
  );
}
