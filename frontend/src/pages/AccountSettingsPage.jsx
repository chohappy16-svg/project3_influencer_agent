import React from 'react';
import { ShieldCheck, Sparkles, Dna, Cpu, CreditCard, LogOut, ArrowRight } from 'lucide-react';

export default function AccountSettingsPage({ user, onGoToDna, onLogout }) {
  return (
    <div className="max-w-3xl space-y-6 pb-12">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">계정 및 워크스페이스 설정</h1>
        <p className="text-sm text-slate-500 mt-1">
          로그인 계정 정보 및 이용 중인 플랜을 확인합니다.
        </p>
      </div>

      {/* 계정 정보 카드 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-7 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-xl bg-brand-navy text-white flex items-center justify-center font-bold text-sm">
              {(user?.company_name || 'I')[0]}
            </div>
            <div>
              <h2 className="text-base font-bold text-brand-navy">{user?.company_name || '클린뷰티 랩'}</h2>
              <p className="text-xs text-slate-500">{user?.email}</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-brand-mint text-xs font-bold border border-emerald-200">
            <ShieldCheck className="w-3.5 h-3.5" /> 인증된 워크스페이스
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-slate-100">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70">
            <div className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
              <CreditCard className="w-3.5 h-3.5 text-brand-sky" /> 현재 이용 플랜
            </div>
            <div className="text-sm font-extrabold text-brand-navy mt-1">Pro Plan · 50인 병렬 분석</div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              CSV 대량 업로드, AI 자동 랭킹, 2인 비교, 엑셀 내보내기 활성화
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70">
            <div className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-brand-mint" /> 적용된 분석 엔진
            </div>
            <div className="text-sm font-extrabold text-brand-navy mt-1">스마트 매칭 검증 시스템</div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              기본 적합성 확인 후 브랜드 핏 심층 분석
            </div>
          </div>
        </div>
      </div>

      {/* 브랜드 DNA 연동 바로가기 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-sky-50 text-brand-sky flex items-center justify-center shrink-0">
            <Dna className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-brand-navy">브랜드 DNA 관리</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              자사몰 URL 재추출 및 AI가 기억하는 브랜드 톤앤매너 수정은 브랜드 DNA 메뉴에서 관리합니다.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onGoToDna}
          className="px-4 py-2.5 rounded-xl bg-brand-navy hover:bg-slate-800 text-white text-xs font-bold inline-flex items-center gap-1.5 transition"
        >
          <Sparkles className="w-3.5 h-3.5 text-brand-sky" /> 브랜드 DNA 수정하기 <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 로그아웃 영역 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 flex items-center justify-between">
        <div>
          <div className="text-sm font-bold text-brand-navy">로그아웃</div>
          <div className="text-xs text-slate-400 mt-0.5">현재 기기에서 안전하게 로그아웃합니다.</div>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="px-4 py-2.5 rounded-xl border border-red-200 bg-red-50/50 hover:bg-red-100 text-red-600 text-xs font-bold inline-flex items-center gap-1.5 transition"
        >
          <LogOut className="w-3.5 h-3.5" /> 로그아웃
        </button>
      </div>
    </div>
  );
}
