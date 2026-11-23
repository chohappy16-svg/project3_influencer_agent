import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

const FIT_STATUS_MAP = {
  APPROVE: {
    label: '적합',
    cls: 'bg-emerald-50 text-brand-mint border-emerald-200',
  },
  CREATIVE_EXCEPTION: {
    label: '예외 추천',
    cls: 'bg-orange-50 text-brand-orange border-orange-200',
  },
  REJECT: {
    label: '부적합',
    cls: 'bg-red-50 text-red-600 border-red-200',
  },
  REVIEW_NEEDED: {
    label: '검토 필요',
    cls: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  DATA_INSUFFICIENT: {
    label: '판독 불가',
    cls: 'bg-slate-100 text-brand-slate border-slate-300',
  },
  UNANALYZABLE: {
    label: '판독 불가',
    cls: 'bg-slate-100 text-brand-slate border-slate-300',
  },
};

export function FitStatusBadge({ status, tooltipText }) {
  const [showTip, setShowTip] = useState(false);
  const cfg = FIT_STATUS_MAP[status] || {
    label: status || '대기',
    cls: 'bg-slate-100 text-brand-slate border-slate-200',
  };
  const isInsufficient = status === 'DATA_INSUFFICIENT' || status === 'UNANALYZABLE';

  return (
    <div
      className="relative inline-flex items-center shrink-0 whitespace-nowrap"
      onMouseEnter={() => isInsufficient && setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
    >
      <span
        onClick={() => isInsufficient && setShowTip((prev) => !prev)}
        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold border shrink-0 whitespace-nowrap ${cfg.cls} ${
          isInsufficient ? 'cursor-help' : ''
        }`}
      >
        {cfg.label}
        {isInsufficient && <HelpCircle className="w-3.5 h-3.5 text-brand-slate shrink-0" />}
      </span>

      {isInsufficient && showTip && (
        <div className="absolute z-30 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 rounded-lg bg-brand-navy text-white text-xs leading-relaxed shadow-lg pointer-events-none whitespace-normal text-left">
          <div className="font-semibold text-slate-200 mb-0.5">마케터 수동 확인 안내</div>
          <div className="text-slate-300">
            {tooltipText || '비공개 계정, 게시물 정보 부족 또는 AI 안전 필터로 인해 판독이 제한되었습니다.'}
          </div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-brand-navy" />
        </div>
      )}
    </div>
  );
}

export function ApprovalStateBadge({ state }) {
  if (state === 'APPROVED') {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-50 text-brand-mint border border-emerald-200 shrink-0 whitespace-nowrap">
        선정 완료
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-slate-50 text-slate-500 border border-slate-200 shrink-0 whitespace-nowrap">
      검토 대기
    </span>
  );
}
