/**
 * [InfluenceOps] CampaignDashboardPage.jsx
 * ==============================================================================
 * 캠페인 목록 및 통합 관리 대시보드 화면
 *
 * 주요 기능:
 *   1. 캠페인 목록 카드: 제품 미니 썸네일, 제품명, [제품 보러가기] 링크, 후보 수 표기
 *   2. 3단계 상태 변경: 준비/분석(READY) <-> 진행 중(IN_PROGRESS) <-> 종료(COMPLETED)
 *   3. 캠페인 일정 관리: D-Day 자동 계산 및 클릭 시 기간 연기/연장 모달 지원
 *   4. 협찬 컨셉 복사(Copy): 기존 캠페인의 제품·포맷·5대 가이드라인을 새 캠페인으로 복제
 *   5. 소프트 삭제 및 휴지통 탭: 30일 보관 카운트다운, 즉시 복원(Restore) 및 영구 삭제
 * ==============================================================================
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Search,
  ChevronRight,
  Sparkles,
  ArrowRight,
  Upload,
  Trash2,
  RotateCcw,
  Copy,
  Calendar,
  X,
  Package,
  ExternalLink,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { campaignsApi } from '../api/client';

const STATUS_META = {
  READY: {
    label: '준비',
    badgeClass: 'bg-sky-50 text-brand-sky border-sky-200',
  },
  IN_PROGRESS: {
    label: '진행 중',
    badgeClass: 'bg-emerald-50 text-brand-mint border-emerald-200',
  },
  COMPLETED: {
    label: '종료',
    badgeClass: 'bg-slate-100 text-slate-500 border-slate-200',
  },
};

function getTodayYMD() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function resolveCampaignStatus(camp) {
  const today = getTodayYMD();
  const start = (camp?.start_date || '').trim();
  const end = (camp?.end_date || '').trim();

  if (start && today < start) return 'READY'; // 시작일 이전(후 일정)
  if (end && today > end) return 'COMPLETED'; // 종료일 경과
  if (start || end) return 'IN_PROGRESS'; // 오늘이 일정 기간 내 해당
  return camp?.status || 'READY'; // 일정 미지정 시 기본 상태
}

function calcDDayText(endDateStr) {
  if (!endDateStr) return null;
  try {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const end = new Date(endDateStr + 'T00:00:00');
    const diff = Math.ceil((end.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    if (diff > 0) return `D-${diff}`;
    if (diff === 0) return 'D-Day';
    return `만료(${Math.abs(diff)}일 경과)`;
  } catch {
    return null;
  }
}

function calcTrashDaysLeft(deletedAtIso) {
  if (!deletedAtIso) return 30;
  try {
    const del = new Date(deletedAtIso);
    const expire = new Date(del.getTime() + 30 * 24 * 60 * 60 * 1000);
    const diff = Math.ceil((expire.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    return Math.max(0, diff);
  } catch {
    return 30;
  }
}

export default function CampaignDashboardPage({
  user,
  campaigns = [],
  loading,
  onCreateClick,
  onCloneCampaign,
  onRefreshCampaigns,
  onSelectCampaign,
  onGoToDna,
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTab, setFilterTab] = useState('all'); // 'all' | 'READY' | 'IN_PROGRESS' | 'COMPLETED' | 'trash'
  const [trashCampaigns, setTrashCampaigns] = useState([]);
  const [editingPeriod, setEditingPeriod] = useState(null); // { id, title, start_date, end_date }
  const [savingPeriod, setSavingPeriod] = useState(false);

  const safeCampaigns = Array.isArray(campaigns) ? campaigns : [];

  const fetchTrash = useCallback(async () => {
    try {
      const rows = await campaignsApi.list(true);
      setTrashCampaigns(Array.isArray(rows) ? rows : []);
    } catch {
      setTrashCampaigns([]);
    }
  }, []);

  useEffect(() => {
    fetchTrash();
  }, [fetchTrash, safeCampaigns]);

  const totalCampaigns = safeCampaigns.length;
  const analyzedCampaigns = safeCampaigns.filter((c) => (c.total_candidates || 0) > 0).length;
  const waitingUpload = safeCampaigns.filter((c) => (c.total_candidates || 0) === 0).length;
  const readyCount = safeCampaigns.filter((c) => resolveCampaignStatus(c) === 'READY').length;
  const inProgressCount = safeCampaigns.filter((c) => resolveCampaignStatus(c) === 'IN_PROGRESS').length;
  const completedCount = safeCampaigns.filter((c) => resolveCampaignStatus(c) === 'COMPLETED').length;
  const totalCandidates = safeCampaigns.reduce((acc, c) => acc + (c.total_candidates || 0), 0);

  const sourceList = filterTab === 'trash' ? trashCampaigns : safeCampaigns;
  const filtered = sourceList.filter((c) => {
    const matchSearch =
      !searchQuery ||
      c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.product_name || '').toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchSearch) return false;
    if (filterTab === 'trash' || filterTab === 'all') return true;
    return resolveCampaignStatus(c) === filterTab;
  });

  const handleStatusChange = async (e, campId, newStatus) => {
    e.stopPropagation();
    try {
      await campaignsApi.update(campId, { status: newStatus });
      onRefreshCampaigns && onRefreshCampaigns();
    } catch {
      alert('상태 변경 중 오류가 발생했습니다.');
    }
  };

  const handleSoftDelete = async (e, camp) => {
    e.stopPropagation();
    if (
      !window.confirm(
        `'${camp.title}' 캠페인을 휴지통으로 이동하시겠습니까?\n(30일간 보관되며 언제든 복구할 수 있습니다.)`
      )
    ) {
      return;
    }
    try {
      await campaignsApi.softDelete(camp.id);
      onRefreshCampaigns && onRefreshCampaigns();
      fetchTrash();
    } catch {
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  const handleRestore = async (e, campId) => {
    e.stopPropagation();
    try {
      await campaignsApi.restore(campId);
      onRefreshCampaigns && onRefreshCampaigns();
      fetchTrash();
    } catch {
      alert('복구 중 오류가 발생했습니다.');
    }
  };

  const handlePermanentDelete = async (e, camp) => {
    e.stopPropagation();
    if (
      !window.confirm(
        `'${camp.title}' 캠페인을 영구 삭제하시겠습니까?\n삭제 후에는 복구할 수 없습니다.`
      )
    ) {
      return;
    }
    try {
      await campaignsApi.permanentDelete(camp.id);
      fetchTrash();
    } catch {
      alert('영구 삭제 중 오류가 발생했습니다.');
    }
  };

  const handleSavePeriod = async (e) => {
    e.preventDefault();
    if (!editingPeriod) return;
    setSavingPeriod(true);
    try {
      await campaignsApi.update(editingPeriod.id, {
        start_date: editingPeriod.start_date,
        end_date: editingPeriod.end_date,
      });
      setEditingPeriod(null);
      onRefreshCampaigns && onRefreshCampaigns();
    } catch {
      alert('기간 조정 저장 중 오류가 발생했습니다.');
    } finally {
      setSavingPeriod(false);
    }
  };

  const handleToggleSourcing = async (e, camp) => {
    e.stopPropagation();
    try {
      const nextState = !camp.is_sourcing_completed;
      await campaignsApi.update(camp.id, { is_sourcing_completed: nextState });
      onRefreshCampaigns && onRefreshCampaigns();
    } catch {
      alert('섭외 상태 변경 중 오류가 발생했습니다.');
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '오늘';
    try {
      const d = new Date(iso);
      return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
    } catch {
      return '오늘';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">캠페인 대시보드</h1>
          <p className="text-sm text-slate-500 mt-1">
            브랜드에 맞는 크리에이터를 발견하고, 확신 있게 결정하세요.
          </p>
        </div>
        <button
          onClick={onCreateClick}
          className="px-5 py-2.5 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-sm font-semibold flex items-center gap-2 shadow-sm transition"
        >
          <Plus className="w-4 h-4" /> 새 캠페인 만들기
        </button>
      </div>

      {/* 4 KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">전체 캠페인</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-navy">{totalCampaigns}</span>
            <span className="text-xs text-slate-400">워크스페이스 누적</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">분석 완료 캠페인</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-navy">{analyzedCampaigns}</span>
            <span className="text-xs text-slate-400">결과 확인 가능</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">업로드 대기</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-orange">{waitingUpload}</span>
            <span className="text-xs text-slate-400">후보 등록 필요</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">누적 분석 후보</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-mint">{totalCandidates}</span>
            <span className="text-xs text-slate-400">명 분석 완료</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Campaign List (Left 8) + Brand DNA & Activity (Right 4) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Campaign Table */}
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-brand-navy">캠페인 목록</h2>
              <span className="text-xs font-semibold text-slate-400">{campaigns.length}</span>
            </div>
            <div className="relative w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="캠페인 검색"
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
              />
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 mb-3 text-xs">
            <div className="flex flex-wrap items-center gap-4">
              {[
                { id: 'all', label: '전체', count: totalCampaigns },
                { id: 'READY', label: '준비', count: readyCount },
                { id: 'IN_PROGRESS', label: '진행 중', count: inProgressCount },
                { id: 'COMPLETED', label: '종료', count: completedCount },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setFilterTab(t.id)}
                  className={`font-semibold transition ${
                    filterTab === t.id ? 'text-brand-navy' : 'text-slate-400 hover:text-slate-600'
                  }`}
                >
                  {t.label} <span className="ml-0.5 text-[11px]">{t.count}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setFilterTab('trash')}
              className={`font-semibold inline-flex items-center gap-1 transition ${
                filterTab === 'trash'
                  ? 'text-rose-600'
                  : 'text-slate-400 hover:text-slate-600'
              }`}
            >
              <Trash2 className="w-3.5 h-3.5" />
              휴지통 <span className="text-[11px]">{trashCampaigns.length}</span>
            </button>
          </div>

          {filterTab === 'trash' && (
            <div className="mb-3 px-3.5 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-[11px] text-amber-800">
              휴지통에 보관된 캠페인은 삭제일로부터 <strong>30일 후 자동으로 영구 삭제</strong>됩니다. 그 전에는 언제든 복구할 수 있습니다.
            </div>
          )}

          {loading ? (
            <div className="py-12 text-center text-sm text-slate-400">캠페인 목록을 불러오는 중...</div>
          ) : filtered.length === 0 ? (
            <div className="py-14 text-center">
              <p className="text-sm text-slate-500 mb-4">
                {filterTab === 'trash'
                  ? '휴지통이 비어 있습니다.'
                  : '해당 조건에 맞는 캠페인이 없습니다.'}
              </p>
              {filterTab !== 'trash' && (
                <button
                  onClick={onCreateClick}
                  className="px-4 py-2 rounded-xl bg-brand-sky text-white text-xs font-semibold"
                >
                  + 첫 캠페인 만들기
                </button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filtered.map((camp) => {
                const hasCandidates = (camp.total_candidates || 0) > 0;
                const statusKey = resolveCampaignStatus(camp);
                const statusInfo = STATUS_META[statusKey] || STATUS_META.READY;
                const dDay = calcDDayText(camp.end_date);
                const formatEmoji =
                  camp.preferred_format === 'REELS'
                    ? '🎬 릴스'
                    : camp.preferred_format === 'FEED'
                    ? '📷 피드'
                    : '✨ 혼합';

                if (filterTab === 'trash') {
                  const daysLeft = calcTrashDaysLeft(camp.deleted_at);
                  return (
                    <div
                      key={camp.id}
                      className="py-4 px-2 rounded-xl flex items-center justify-between gap-4 flex-nowrap bg-slate-50/40"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-bold text-slate-600 truncate">{camp.title}</div>
                        <div className="text-xs text-slate-400 mt-0.5 truncate flex items-center gap-2">
                          <span className="truncate">{camp.product_name || '스킨케어 제품'}</span>
                          <span className="shrink-0">·</span>
                          <span className="shrink-0 whitespace-nowrap">후보 {camp.total_candidates || 0}명</span>
                          <span className="shrink-0">·</span>
                          <span className="text-rose-500 font-semibold shrink-0 whitespace-nowrap">{daysLeft}일 후 영구 삭제</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={(e) => handleRestore(e, camp.id)}
                          className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:border-brand-sky hover:text-brand-sky text-xs font-bold text-brand-navy inline-flex items-center gap-1 shrink-0 whitespace-nowrap transition"
                        >
                          <RotateCcw className="w-3.5 h-3.5" /> 되돌리기(복구)
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handlePermanentDelete(e, camp)}
                          className="px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-600 hover:text-white text-rose-600 border border-rose-200 text-xs font-bold shrink-0 whitespace-nowrap transition"
                        >
                          영구 삭제
                        </button>
                      </div>
                    </div>
                  );
                }

                return (
                  <div
                    key={camp.id}
                    onClick={() => onSelectCampaign(camp, hasCandidates ? 'results' : 'upload')}
                    className="py-4 px-2 hover:bg-slate-50/80 rounded-xl transition cursor-pointer flex items-center justify-between gap-3 flex-nowrap"
                  >
                    <div className="min-w-0 flex-1 flex items-center gap-3">
                      <div className="w-11 h-11 rounded-xl border border-slate-200 bg-slate-50 shrink-0 overflow-hidden flex items-center justify-center">
                        {camp.product_image_url ? (
                          <img
                            src={camp.product_image_url}
                            alt={camp.product_name || camp.title}
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Package className="w-4 h-4 text-slate-400" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-brand-navy truncate">{camp.title}</span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] font-semibold text-slate-600 shrink-0 whitespace-nowrap">
                            {formatEmoji}
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5 truncate flex items-center gap-2">
                          <span className="truncate font-medium text-slate-500">
                            {camp.product_name || '스킨케어 제품'}
                          </span>
                          {camp.product_url && (
                            <a
                              href={camp.product_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-brand-sky hover:underline shrink-0 whitespace-nowrap"
                              title="제품 보러가기"
                            >
                              제품 보러가기 <ExternalLink className="w-2.5 h-2.5" />
                            </a>
                          )}
                          <span className="shrink-0">·</span>
                          <span className="shrink-0 whitespace-nowrap">후보 {camp.total_candidates || 0}명</span>
                        </div>
                      </div>
                    </div>

                    {/* Period & Adjust Button */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingPeriod({
                          id: camp.id,
                          title: camp.title,
                          start_date: camp.start_date || '',
                          end_date: camp.end_date || '',
                        });
                      }}
                      title="클릭하여 캠페인 기간 조정(연기/연장)"
                      className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:border-brand-sky text-[11px] text-slate-600 inline-flex items-center gap-1.5 shrink-0 whitespace-nowrap transition"
                    >
                      <Calendar className="w-3 h-3 text-slate-400 shrink-0" />
                      {camp.start_date && camp.end_date ? (
                        <span className="whitespace-nowrap">
                          {camp.start_date.slice(5)}~{camp.end_date.slice(5)}
                          {dDay && <strong className="ml-1 text-brand-navy">({dDay})</strong>}
                        </span>
                      ) : (
                        <span className="text-slate-400 whitespace-nowrap">기간 설정</span>
                      )}
                    </button>

                    {/* Schedule-Synced Automatic Status Badge */}
                    <span
                      title="오늘 날짜 및 캠페인 일정에 따라 자동 반영됩니다"
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border whitespace-nowrap shrink-0 ${statusInfo.badgeClass}`}
                    >
                      {statusInfo.label}
                    </span>

                    {/* Sourcing Status Badge / Interactive Toggle */}
                    <button
                      type="button"
                      onClick={(e) => handleToggleSourcing(e, camp)}
                      title={
                        camp.is_sourcing_completed
                          ? '인플루언서 섭외가 마감된 캠페인입니다. 클릭하면 섭외 진행 중으로 변경됩니다.'
                          : '인플루언서 서칭 및 섭외가 진행 중인 캠페인입니다. 인원 확정 완료 시 클릭하여 마감하세요.'
                      }
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border inline-flex items-center gap-1 shrink-0 whitespace-nowrap transition cursor-pointer ${
                        camp.is_sourcing_completed
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                          : 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100'
                      }`}
                    >
                      {camp.is_sourcing_completed ? (
                        <>
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" /> 섭외 완료
                        </>
                      ) : (
                        <>
                          <Clock className="w-3 h-3 text-amber-600" /> 섭외 진행 중
                        </>
                      )}
                    </button>

                    {/* Action Icons: Upload / Clone Concept / Soft Delete */}
                    <div className="flex items-center gap-1 shrink-0 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      {!hasCandidates && (
                        <button
                          type="button"
                          onClick={() => onSelectCampaign(camp, 'upload')}
                          className="p-1.5 rounded-lg text-brand-sky hover:bg-sky-50 shrink-0"
                          title="후보 업로드"
                        >
                          <Upload className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onCloneCampaign && onCloneCampaign(camp)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-brand-navy hover:bg-slate-100 shrink-0 transition"
                        title="협찬 컨셉 복사 (새 캠페인에 가이드라인 복제)"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => handleSoftDelete(e, camp)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 shrink-0 transition"
                        title="휴지통으로 이동 (30일 보관)"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <ChevronRight
                        onClick={() => onSelectCampaign(camp, hasCandidates ? 'results' : 'upload')}
                        className="w-4 h-4 text-slate-300 cursor-pointer shrink-0"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: Brand DNA Summary Card */}
        <div className="lg:col-span-4 space-y-5">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-brand-navy">우리 브랜드 DNA</h3>
              <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-brand-mint text-[11px] font-semibold">
                저장됨
              </span>
            </div>

            <div className="text-base font-bold text-brand-navy">{user?.company_name || '내 워크스페이스'}</div>
            <div className="text-xs text-slate-400 mt-0.5 truncate">
              {user?.brand_url || '자사몰 미등록'}
            </div>

            <div className="flex flex-wrap gap-1.5 mt-3">
              {['자연광', '순한 성분', '미니멀'].map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 rounded-md bg-slate-100 text-slate-600 text-[11px] font-semibold"
                >
                  {tag}
                </span>
              ))}
            </div>

            <div className="mt-4 p-3 rounded-xl bg-slate-50 border border-slate-200/60 text-xs text-slate-600 leading-relaxed">
              {user?.brand_dna_summary ||
                '따뜻한 자연광과 깨끗한 피부결·일상 여백의 미를 지향하는 클린 라이프스타일 브랜드 페르소나입니다.'}
            </div>

            <button
              onClick={onGoToDna}
              className="mt-4 w-full py-2 rounded-xl border border-slate-200 text-xs font-semibold text-brand-navy hover:bg-slate-50 flex items-center justify-center gap-1.5 transition"
            >
              <Sparkles className="w-3.5 h-3.5 text-brand-sky" /> 브랜드 기준 확인 →
            </button>
          </div>
        </div>
      </div>

      {/* Period Adjustment Modal */}
      {editingPeriod && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4"
          onClick={() => setEditingPeriod(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md p-6 space-y-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-brand-navy">캠페인 기간 조정 (연기/연장)</h3>
              <button
                type="button"
                onClick={() => setEditingPeriod(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="text-xs text-slate-500">
              대상 캠페인: <strong className="text-brand-navy">{editingPeriod.title}</strong>
            </div>
            <form onSubmit={handleSavePeriod} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">시작일</label>
                <input
                  type="date"
                  required
                  value={editingPeriod.start_date}
                  onChange={(e) =>
                    setEditingPeriod((prev) => ({ ...prev, start_date: e.target.value }))
                  }
                  className="w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">종료일</label>
                <input
                  type="date"
                  required
                  min={editingPeriod.start_date}
                  value={editingPeriod.end_date}
                  onChange={(e) =>
                    setEditingPeriod((prev) => ({ ...prev, end_date: e.target.value }))
                  }
                  className="w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingPeriod(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={savingPeriod}
                  className="px-5 py-2 rounded-xl bg-brand-navy hover:bg-slate-800 text-white text-xs font-bold transition disabled:opacity-50"
                >
                  {savingPeriod ? '저장 중...' : '기간 저장'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
