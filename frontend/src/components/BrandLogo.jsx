import React from 'react';

export function BrandLogo({ dark = false, showSubtext = false }) {
  return (
    <div className="inline-flex flex-col select-none">
      <div className="flex items-center gap-1 text-xl font-extrabold tracking-tight">
        <span className={dark ? 'text-white' : 'text-brand-navy'}>Influence</span>
        <span className="text-brand-sky">Ops</span>
        <span className="text-brand-mint text-base leading-none ml-0.5">✦</span>
      </div>
      {showSubtext && (
        <span className="text-[10px] font-medium tracking-[0.22em] text-slate-400 mt-0.5">
          BRAND INTELLIGENCE
        </span>
      )}
    </div>
  );
}
