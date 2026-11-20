import React, { useState } from 'react';
import { ShieldCheck, Sparkles, Dna, Cpu, CreditCard, LogOut, ArrowRight, UserX, AlertCircle, Loader2 } from 'lucide-react';
import { authApi } from '../api/client';

export default function AccountSettingsPage({ user, onGoToDna, onLogout }) {
  const [withdrawModalOpen, setWithdrawModalOpen] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState('');

  const handleWithdraw = async () => {
    setWithdrawing(true);
    setWithdrawError('');
    try {
      await authApi.deleteAccount();
      setWithdrawModalOpen(false);
      onLogout();
    } catch (err) {
      setWithdrawError(err.response?.data?.detail || '회원 탈퇴 처리 중 오류가 발생했습니다.');
    } finally {
      setWithdrawing(false);
    }
  };

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

      {/* 로그아웃 및 회원 탈퇴 영역 */}
      <div className="bg-white rounded-2xl border border-slate-200/80 divide-y divide-slate-100">
        <div className="p-6 flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-brand-navy">로그아웃</div>
            <div className="text-xs text-slate-400 mt-0.5">현재 기기에서 안전하게 로그아웃합니다.</div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-bold inline-flex items-center gap-1.5 transition"
          >
            <LogOut className="w-3.5 h-3.5" /> 로그아웃
          </button>
        </div>

        <div className="p-6 flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-rose-600">회원 탈퇴</div>
            <div className="text-xs text-slate-400 mt-0.5">
              계정 및 저장된 브랜드 DNA, 모든 캠페인 분석 내역을 영구 삭제합니다.
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setWithdrawError('');
              setWithdrawModalOpen(true);
            }}
            className="px-4 py-2.5 rounded-xl border border-rose-200 bg-rose-50/70 hover:bg-rose-100 text-rose-600 text-xs font-bold inline-flex items-center gap-1.5 transition"
          >
            <UserX className="w-3.5 h-3.5" /> 회원 탈퇴
          </button>
        </div>
      </div>

      {/* 회원 탈퇴 확인 모달 */}
      {withdrawModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl border border-slate-200 p-6">
            <div className="w-11 h-11 rounded-full bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 mb-4">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-brand-navy">정말 탈퇴하시겠습니까?</h3>
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              탈퇴하시면 <span className="font-semibold text-brand-navy">{user?.email}</span> 계정과 저장된 브랜드 DNA, 캠페인 및 인플루언서 분석 데이터가 모두 영구 삭제되며 복구할 수 없습니다.
            </p>
            {withdrawError && (
              <div className="mt-3 p-2.5 rounded-lg bg-rose-50 text-xs text-rose-600 border border-rose-200">
                {withdrawError}
              </div>
            )}
            <div className="mt-5 flex items-center gap-2">
              <button
                type="button"
                disabled={withdrawing}
                onClick={() => setWithdrawModalOpen(false)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 text-xs font-semibold transition"
              >
                취소
              </button>
              <button
                type="button"
                disabled={withdrawing}
                onClick={handleWithdraw}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition disabled:opacity-60"
              >
                {withdrawing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                탈퇴하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
