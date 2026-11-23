/**
 * [InfluenceOps] CampaignResultsPage.jsx
 * ==============================================================================
 * 캠페인별 인플루언서 분석 결과 대시보드 화면
 *
 * 주요 기능:
 *   1. 상단 타겟 제품 정보 요약 바(Context Bar): 제품명, 대표 썸네일, 공식 판매처 링크
 *   2. 효율적 2단계 분석 결과 요약 배너 및 핵심 KPI 4종 카드
 *   3. 인플루언서 목록 테이블 (매칭률 순 정렬, 비공개/협찬불가 후보 최하단 강제 배치)
 *   4. 체크박스 다중 선택 기반 일괄 상태 변경 (대기자 일괄 승인 / 승인완료 일괄 취소)
 *   5. 개별 [⚖ 비교] 버튼 기반 1:1~1:3 다자 비교 플로팅 도크 (Compare Dock)
 *   6. 첫 방문 마케터 대상 비교 기능 온보딩 코칭 팝업 (localStorage 연동)
 *   7. 최종 선정자 명단 엑셀(.xlsx) 내보내기 다운로드
 * ==============================================================================
 */

import React, { useState, useEffect } from 'react';
import {
  Search,
  Download,
  Upload,
  ExternalLink,
  ArrowRight,
  Sparkles,
  CheckSquare,
  Square,
  CheckCircle2,
  X,
  Scale,
  Package,
  Edit3,
  Trash2,
} from 'lucide-react';
import { FitStatusBadge, ApprovalStateBadge } from '../components/StatusBadge';
import { InfoTooltip } from '../components/InfoTooltip';
import { campaignsApi } from '../api/client';

export default function CampaignResultsPage({
  campaign,
  results,
  costSummary,
  loading,
  compareIds = [],
  onChangeCompareIds,
  onUploadMore,
  onDecisionUpdated,
  onResultsDeleted,
  onCompareSelected,
  onOpenDetail,
}) {
  const [statusTab, setStatusTab] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [showCompareNudge, setShowCompareNudge] = useState(false);
  const [productInfo, setProductInfo] = useState({
    product_name: campaign.product_name || '',
    product_url: campaign.product_url || '',
    product_image_url: campaign.product_image_url || '',
  });
  const [editingProduct, setEditingProduct] = useState(null);
  const [savingProduct, setSavingProduct] = useState(false);

  useEffect(() => {
    setProductInfo({
      product_name: campaign.product_name || '',
      product_url: campaign.product_url || '',
      product_image_url: campaign.product_image_url || '',
    });
  }, [campaign.id, campaign.product_name, campaign.product_url, campaign.product_image_url]);

  const handleSaveProduct = async (e) => {
    e.preventDefault();
    if (!editingProduct) return;
    setSavingProduct(true);
    try {
      const updated = await campaignsApi.update(campaign.id, {
        product_name: editingProduct.product_name.trim() || null,
        product_url: editingProduct.product_url.trim() || null,
      });
      setProductInfo({
        product_name: updated.product_name || '',
        product_url: updated.product_url || '',
        product_image_url: updated.product_image_url || '',
      });
      setEditingProduct(null);
    } catch (err) {
      alert(err.response?.data?.detail || '제품 정보 저장 중 오류가 발생했습니다.');
    } finally {
      setSavingProduct(false);
    }
  };

  useEffect(() => {
    if (loading || results.length < 2 || compareIds.length > 0) return;
    if (localStorage.getItem('influenceops_compare_nudge_seen')) return;

    const showTimer = setTimeout(() => setShowCompareNudge(true), 800);
    const hideTimer = setTimeout(() => setShowCompareNudge(false), 8800);
    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [loading, results.length, compareIds.length]);

  const dismissCompareNudge = () => {
    setShowCompareNudge(false);
    localStorage.setItem('influenceops_compare_nudge_seen', '1');
  };

  // 후보자 목록 정렬 우선순위 산정 함수:
  // 0: 협찬 가능 후보(적합/예외추천) -> 매칭률 높은 순 최상단 노출
  // 1: 일반 부적합 후보 -> 중간 노출
  // 2: 비공개/계정오류/협찬불가 후보 -> 최하단 고정 및 흐리게(dimmed) 처리
  const getPriorityRank = (r) => {
    const isPrivateOrUnidentifiable =
      r.fit_status === 'DATA_INSUFFICIENT' ||
      r.fit_status === 'UNANALYZABLE' ||
      r.recommended_fee === '진행 불가' ||
      r.recommended_fee === '협찬 불가 (비공개)' ||
      r.recommended_fee === '산정 불가' ||
      r.recommended_fee === '확인 필요 (계정 오류)' ||
      !r.followers_count ||
      r.followers_count <= 0;

    if (isPrivateOrUnidentifiable) return 2;
    if (r.fit_status === 'REJECT') return 1;
    return 0;
  };

  const sortedResults = [...results].sort((a, b) => {
    const rankDiff = getPriorityRank(a) - getPriorityRank(b);
    if (rankDiff !== 0) return rankDiff;
    return (b.overall_match_percentage || 0) - (a.overall_match_percentage || 0);
  });

  const totalCount = sortedResults.length;
  const rejectedCount = sortedResults.filter((r) => r.fit_status === 'REJECT').length;
  const approvedCount = sortedResults.filter((r) => r.approval_state === 'APPROVED').length;
  const deepAnalyzedCount = sortedResults.filter((r) => r.fit_status !== 'REJECT').length;

  const filtered = sortedResults.filter((r) => {
    const matchText =
      !searchTerm ||
      r.instagram_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (r.full_name || '').toLowerCase().includes(searchTerm.toLowerCase());
    if (!matchText) return false;

    if (statusTab === 'APPROVE') return r.fit_status === 'APPROVE';
    if (statusTab === 'CREATIVE_EXCEPTION') return r.fit_status === 'CREATIVE_EXCEPTION';
    if (statusTab === 'ISSUES')
      return (
        r.fit_status === 'REJECT' ||
        r.fit_status === 'DATA_INSUFFICIENT' ||
        r.fit_status === 'UNANALYZABLE'
      );
    if (statusTab === 'APPROVED') return r.approval_state === 'APPROVED';
    return true;
  });

  const filteredIds = filtered.map((r) => r.id);
  const isAllFilteredSelected =
    filteredIds.length > 0 && filteredIds.every((id) => selectedIds.includes(id));

  const toggleSelect = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (isAllFilteredSelected) {
      setSelectedIds((prev) => prev.filter((id) => !filteredIds.includes(id)));
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...filteredIds])));
    }
  };

  const toggleCompareId = (id) => {
    dismissCompareNudge();
    if (!onChangeCompareIds) return;
    if (compareIds.includes(id)) {
      onChangeCompareIds(compareIds.filter((x) => x !== id));
    } else {
      if (compareIds.length >= 3) {
        alert('후보 비교에는 최대 3명까지만 선택할 수 있습니다.');
        return;
      }
      onChangeCompareIds([...compareIds, id]);
    }
  };

  const compareCandidates = compareIds
    .map((id) => results.find((r) => r.id === id))
    .filter(Boolean);

  const selectedPendingIds = selectedIds.filter(
    (id) => results.find((r) => r.id === id)?.approval_state !== 'APPROVED'
  );
  const selectedApprovedIds = selectedIds.filter(
    (id) => results.find((r) => r.id === id)?.approval_state === 'APPROVED'
  );

  const handleBulkDecision = async (targetIds, decision) => {
    if (targetIds.length === 0 || bulkProcessing) return;
    const label = decision === 'APPROVED' ? '승인' : '승인 취소';
    if (!window.confirm(`해당 ${targetIds.length}명의 후보를 일괄 ${label} 처리하시겠습니까?`)) {
      return;
    }
    setBulkProcessing(true);
    try {
      await Promise.all(targetIds.map((id) => campaignsApi.decide(id, decision)));
      targetIds.forEach((id) => onDecisionUpdated && onDecisionUpdated(id, decision));
      setSelectedIds([]);
    } catch (err) {
      alert('일괄 처리 중 오류가 발생했습니다.');
    } finally {
      setBulkProcessing(false);
    }
  };

  const handleDeleteSingle = async (e, item) => {
    e.stopPropagation();
    if (!window.confirm(`@${item.instagram_id} 후보자를 이 캠페인 목록에서 삭제하시겠습니까?`)) {
      return;
    }
    try {
      await campaignsApi.deleteResult(item.id);
      setSelectedIds((prev) => prev.filter((id) => id !== item.id));
      if (onResultsDeleted) onResultsDeleted([item.id]);
    } catch {
      alert('후보 삭제 중 오류가 발생했습니다.');
    }
  };

  const handleBulkDelete = async (targetIds) => {
    if (targetIds.length === 0 || bulkProcessing) return;
    if (!window.confirm(`선택한 ${targetIds.length}명의 후보자를 이 캠페인 목록에서 삭제하시겠습니까?`)) {
      return;
    }
    setBulkProcessing(true);
    try {
      await Promise.all(targetIds.map((id) => campaignsApi.deleteResult(id)));
      setSelectedIds([]);
      if (onResultsDeleted) onResultsDeleted(targetIds);
    } catch {
      alert('일괄 삭제 중 오류가 발생했습니다.');
    } finally {
      setBulkProcessing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await campaignsApi.exportExcel(campaign.id);
    } finally {
      setExporting(false);
    }
  };

  const formatFollowers = (n) => {
    if (!n || n <= 0) return '파악 불가';
    if (n >= 10000) return `${(n / 10000).toFixed(1)}만`;
    return `${n.toLocaleString()}명`;
  };

  const authLabel = (val) => {
    if (val === 'HIGH') return '높음';
    if (val === 'MEDIUM') return '보통';
    if (val === 'LOW') return '낮음';
    return '파악 불가';
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-bold text-brand-navy">{campaign.title} · 분석 결과</h1>
            <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-100 text-brand-navy border border-slate-200">
              {campaign.preferred_format === 'REELS'
                ? '🎬 릴스(숏폼) 협찬'
                : campaign.preferred_format === 'FEED'
                ? '📷 이미지 피드 협찬'
                : '✨ 자유/혼합'}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            브랜드 DNA와 캠페인 가이드라인을 바탕으로 매칭률이 높은 순서로 정렬했습니다.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={onUploadMore}
            className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-brand-navy hover:bg-slate-50 flex items-center gap-1.5"
          >
            <Upload className="w-3.5 h-3.5" /> 후보 추가 업로드
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="px-4 py-2 rounded-xl bg-brand-mint hover:bg-emerald-600 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm transition disabled:opacity-60"
          >
            <Download className="w-3.5 h-3.5" /> {exporting ? '생성 중...' : '확정자 엑셀 내보내기 ↓'}
          </button>
        </div>
      </div>

      {/* Target Product Context Bar */}
      <div className="bg-white rounded-2xl border border-slate-200/80 px-5 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-12 h-12 rounded-xl border border-slate-200 bg-slate-50 shrink-0 overflow-hidden flex items-center justify-center">
            {productInfo.product_image_url ? (
              <img
                src={productInfo.product_image_url}
                alt={productInfo.product_name || campaign.title}
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
                className="w-full h-full object-cover"
              />
            ) : (
              <Package className="w-5 h-5 text-slate-400" />
            )}
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-semibold text-slate-400">협찬 대상 제품</div>
            <div className="text-sm font-bold text-brand-navy truncate mt-0.5">
              {productInfo.product_name || '제품명 미지정'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {productInfo.product_url && (
            <a
              href={productInfo.product_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50/70 hover:border-brand-sky hover:text-brand-sky text-xs font-semibold text-brand-navy inline-flex items-center gap-1.5 whitespace-nowrap transition"
            >
              제품 보러가기 <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          <button
            type="button"
            onClick={() => setEditingProduct({ ...productInfo })}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-600 inline-flex items-center gap-1 whitespace-nowrap transition"
            title="제품명 및 제품 링크 수정"
          >
            <Edit3 className="w-3.5 h-3.5 text-slate-400" />
            {productInfo.product_url ? '제품 정보 수정' : '제품 링크 연결'}
          </button>
        </div>
      </div>

      {/* Cost Optimization Summary Banner (if just uploaded) */}
      {costSummary && (
        <div className="bg-white rounded-2xl border border-sky-200 bg-sky-50/40 px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 text-xs font-semibold text-brand-navy">
            <Sparkles className="w-4 h-4 text-brand-sky" />
            <span>
              효율적 2단계 분석 완료: 1차 선별({costSummary.track1_gemini_calls}명 중 {costSummary.track1_rejected_count}명 제외) ➔ 정밀 분석({costSummary.track2_gpt4o_calls}명)
            </span>
          </div>
          <div className="text-xs font-bold text-brand-sky">
            소모 비용 {costSummary.total_cost_krw}원 (단일 정밀 분석 대비 {costSummary.cost_saving_percentage}% 절감)
          </div>
        </div>
      )}

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">업로드 후보</div>
          <div className="text-3xl font-extrabold text-brand-navy mt-2">{totalCount}명</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">1차 통과 (정밀 분석)</div>
          <div className="text-3xl font-extrabold text-brand-navy mt-2">{deepAnalyzedCount}명</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">1차 제외 (부적합)</div>
          <div className="text-3xl font-extrabold text-brand-orange mt-2">{rejectedCount}명</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">최종 승인 완료</div>
          <div className="text-3xl font-extrabold text-brand-mint mt-2">{approvedCount}명</div>
        </div>
      </div>

      {/* Main List View Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden">
        {/* Filter Bar */}
        <div className="p-5 border-b border-slate-100 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {[
              { id: 'ALL', label: `전체 (${totalCount})` },
              { id: 'APPROVE', label: '적합' },
              { id: 'CREATIVE_EXCEPTION', label: '예외 추천' },
              { id: 'ISSUES', label: '부적합·판독불가' },
              { id: 'APPROVED', label: `승인 완료 (${approvedCount})` },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setStatusTab(t.id)}
                className={`px-3 py-1.5 rounded-lg font-semibold transition ${
                  statusTab === t.id
                    ? 'bg-brand-navy text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200/70'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="relative w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="사용자명 검색"
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
            />
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">분석 결과를 불러오는 중...</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-400">해당 조건에 맞는 후보가 없습니다.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] font-bold text-slate-400 bg-slate-50/60">
                  <th className="py-3 px-4 w-12 text-center">
                    <button
                      type="button"
                      onClick={toggleSelectAll}
                      title={isAllFilteredSelected ? '현재 목록 전체 해제' : '현재 목록 전체 선택'}
                      className="text-slate-400 hover:text-brand-navy inline-flex items-center justify-center"
                    >
                      {isAllFilteredSelected ? (
                        <CheckSquare className="w-4 h-4 text-brand-sky" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  </th>
                  <th className="py-3 px-4">인플루언서 (클릭 시 상세 분석)</th>
                  <th className="py-3 px-3">
                    <span className="inline-flex items-center">
                      주력 포맷
                      <InfoTooltip title="인플루언서 주력 콘텐츠 포맷">
                        <p>최근 피드 구성을 분석해 강점을 가진 포맷을 분류합니다.</p>
                        <p className="text-purple-300">• 🎬 릴스 특화: 숏폼 영상 비중 높음</p>
                        <p className="text-sky-300">• 📷 이미지 특화: 사진·그리드 연출 강점</p>
                        <p className="text-teal-300">• 🎬+📷 올라운더: 영상·사진 모두 균형</p>
                      </InfoTooltip>
                    </span>
                  </th>
                  <th className="py-3 px-3">팔로워</th>
                  <th className="py-3 px-3">예상 원고료</th>
                  <th className="py-3 px-3">
                    <span className="inline-flex items-center">
                      매칭률 ↓
                      <InfoTooltip title="매칭률 (브랜드 적합도 점수)">
                        <p>브랜드 DNA와 캠페인 가이드라인을 기준으로 피드 이미지·캡션을 AI가 종합 평가한 점수입니다.</p>
                        <p className="text-emerald-300">• 80% 이상: 적합 (즉시 섭외 추천)</p>
                        <p className="text-amber-300">• 60~79%: 예외 추천 (가이드 조율 권장)</p>
                        <p className="text-slate-300">• 59% 이하: 부적합 또는 판독 불가</p>
                      </InfoTooltip>
                    </span>
                  </th>
                  <th className="py-3 px-4">핵심 판정 이유</th>
                  <th className="py-3 px-3">AI 판정</th>
                  <th className="py-3 px-4">상태</th>
                  <th className="py-3 px-3 text-center">삭제</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {filtered.map((r) => {
                  const isSelected = selectedIds.includes(r.id);
                  const thumb = r.thumbnails && r.thumbnails.length > 0 ? r.thumbnails[0] : null;
                  const igUrl = `https://www.instagram.com/${r.instagram_id}/`;

                  const thumbCount = r.thumbnails ? r.thumbnails.length : 0;
                  const mediaTypeLabel =
                    thumbCount > 1 ? '멀티 피드' : thumbCount === 1 ? '이미지' : '텍스트/미수집';
                  const isNonViable = getPriorityRank(r) === 2;

                  return (
                    <tr
                      key={r.id}
                      onClick={() => onOpenDetail && onOpenDetail(r)}
                      className={`transition cursor-pointer ${
                        isSelected
                          ? 'bg-sky-50/40'
                          : isNonViable
                          ? 'bg-slate-50/70 opacity-55 hover:opacity-90'
                          : 'hover:bg-slate-50/80'
                      }`}
                    >
                      <td className="py-4 px-4 text-center" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => toggleSelect(r.id)}
                          className="text-slate-400 hover:text-brand-navy"
                        >
                          {isSelected ? (
                            <CheckSquare className="w-4 h-4 text-brand-sky" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      </td>

                      {/* Influencer + Thumbnail -> Open Detail */}
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl overflow-hidden bg-slate-100 border border-slate-200 shrink-0 flex items-center justify-center">
                            {thumb ? (
                              <img
                                src={thumb}
                                alt={r.instagram_id}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  e.currentTarget.style.display = 'none';
                                }}
                              />
                            ) : (
                              <span className="text-xs font-bold text-slate-500">
                                {r.instagram_id.slice(0, 2).toUpperCase()}
                              </span>
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="font-bold text-brand-navy group-hover:text-brand-sky">
                              @{r.instagram_id}
                            </div>
                            <div className="text-[11px] text-slate-400 truncate max-w-[160px]">
                              {r.full_name || r.instagram_tier}
                            </div>
                            <div
                              className="mt-1.5 inline-flex items-center gap-1.5 flex-nowrap shrink-0"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <button
                                type="button"
                                onClick={() => onOpenDetail && onOpenDetail(r)}
                                className="px-2 py-0.5 rounded-md bg-sky-50 text-brand-sky hover:bg-brand-sky hover:text-white text-[10px] font-bold shrink-0 whitespace-nowrap transition"
                              >
                                후보 분석
                              </button>
                              <button
                                type="button"
                                onClick={() => toggleCompareId(r.id)}
                                title={compareIds.includes(r.id) ? '비교함에서 빼기' : '비교함에 담기 (최대 3명)'}
                                className={`px-2 py-0.5 rounded-md text-[10px] font-bold inline-flex items-center gap-0.5 shrink-0 whitespace-nowrap transition border ${
                                  compareIds.includes(r.id)
                                    ? 'bg-brand-navy text-white border-brand-navy'
                                    : 'bg-white text-slate-600 border-slate-200 hover:border-brand-navy hover:text-brand-navy'
                                }`}
                              >
                                <Scale className="w-2.5 h-2.5 shrink-0" />
                                {compareIds.includes(r.id) ? '비교중' : '비교'}
                              </button>
                              <a
                                href={igUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                title={`@${r.instagram_id} 인스타그램 새 탭에서 열기`}
                                className="px-2 py-0.5 rounded-md border border-slate-200 bg-white text-slate-600 hover:border-brand-navy hover:text-brand-navy text-[10px] font-semibold inline-flex items-center gap-0.5 shrink-0 whitespace-nowrap transition"
                              >
                                인스타 <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                              </a>
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="py-4 px-3">
                        {isNonViable || r.primary_format === 'UNKNOWN' ? (
                          <span className="text-slate-400 text-[11px]">—</span>
                        ) : r.primary_format === 'REELS' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-purple-50 text-purple-700 border border-purple-200 text-[11px] font-bold whitespace-nowrap">
                            🎬 릴스 특화
                          </span>
                        ) : r.primary_format === 'HYBRID' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-teal-50 text-teal-700 border border-teal-200 text-[11px] font-bold whitespace-nowrap">
                            🎬+📷 올라운더
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-sky-50 text-sky-700 border border-sky-200 text-[11px] font-bold whitespace-nowrap">
                            📷 이미지 특화
                          </span>
                        )}
                      </td>

                      <td className="py-4 px-3 font-semibold text-slate-700">
                        {formatFollowers(r.followers_count)}
                      </td>
                      <td className="py-4 px-3">
                        {r.recommended_fee === '진행 불가' || r.recommended_fee === '협찬 불가 (비공개)' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-slate-100 text-slate-500 border border-slate-200 whitespace-nowrap">
                            협찬 불가 (비공개)
                          </span>
                        ) : r.recommended_fee === '산정 불가' ||
                          r.recommended_fee === '확인 필요 (계정 오류)' ||
                          !r.recommended_fee ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap">
                            확인 필요 (계정 오류)
                          </span>
                        ) : (
                          <span className="font-semibold text-brand-navy whitespace-nowrap">
                            {r.recommended_fee}
                          </span>
                        )}
                      </td>

                      <td className="py-4 px-3">
                        <span
                          className={`text-sm font-extrabold ${
                            r.overall_match_percentage >= 80
                              ? 'text-brand-mint'
                              : r.overall_match_percentage >= 60
                              ? 'text-brand-orange'
                              : 'text-brand-slate'
                          }`}
                        >
                          {r.overall_match_percentage > 0 ? `${r.overall_match_percentage}%` : '—'}
                        </span>
                      </td>

                      <td
                        onClick={() => onOpenDetail && onOpenDetail(r)}
                        className="py-4 px-4 text-slate-600 max-w-[260px] cursor-pointer hover:text-brand-navy"
                      >
                        <div className="line-clamp-2 leading-relaxed">{r.one_line_verdict}</div>
                      </td>

                      <td className="py-4 px-3 whitespace-nowrap shrink-0">
                        <FitStatusBadge status={r.fit_status} tooltipText={r.one_line_verdict} />
                      </td>

                      <td className="py-4 px-4 whitespace-nowrap shrink-0">
                        <ApprovalStateBadge state={r.approval_state} />
                      </td>

                      <td className="py-4 px-3 text-center whitespace-nowrap shrink-0" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSingle(e, r)}
                          title="이 후보 목록에서 삭제"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="px-5 py-3.5 border-t border-slate-100 bg-slate-50/40 flex flex-wrap items-center justify-between text-[11px] text-slate-400">
          <span>
            — / 파악 불가 = UNKNOWN · AI가 임의로 추정하지 않으며, 0원(무상 시딩)과 구분합니다.
          </span>
          <span>총 {filtered.length}명 표시</span>
        </div>
      </div>

      {/* Pure Batch Approval Floating Bar (Bottom-Center) */}
      {selectedIds.length > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 bg-brand-navy text-white px-5 py-3 rounded-2xl shadow-2xl flex flex-wrap items-center gap-3 border border-slate-700">
          <div className="flex items-center gap-2 pr-2 border-r border-slate-700">
            <span className="text-xs font-semibold">
              <strong className="text-brand-sky">{selectedIds.length}명</strong> 선택됨
            </span>
            <button
              type="button"
              onClick={() => setSelectedIds([])}
              title="선택 해제"
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            {selectedPendingIds.length > 0 && (
              <button
                type="button"
                onClick={() => handleBulkDecision(selectedPendingIds, 'APPROVED')}
                disabled={bulkProcessing}
                className="px-4 py-2 rounded-xl bg-brand-mint hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-50"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {selectedApprovedIds.length > 0
                  ? `대기 ${selectedPendingIds.length}명 승인`
                  : `${selectedPendingIds.length}명 일괄 승인`}
              </button>
            )}
            {selectedApprovedIds.length > 0 && (
              <button
                type="button"
                onClick={() => handleBulkDecision(selectedApprovedIds, 'PENDING')}
                disabled={bulkProcessing}
                className="px-4 py-2 rounded-xl bg-slate-700 hover:bg-rose-600 text-white text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-50"
              >
                <X className="w-3.5 h-3.5" />
                {selectedPendingIds.length > 0
                  ? `승인완료 ${selectedApprovedIds.length}명 취소`
                  : `${selectedApprovedIds.length}명 일괄 승인 취소`}
              </button>
            )}
            <button
              type="button"
              onClick={() => handleBulkDelete(selectedIds)}
              disabled={bulkProcessing}
              className="px-3.5 py-2 rounded-xl bg-rose-600/90 hover:bg-rose-600 text-white text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              선택 삭제
            </button>
          </div>
        </div>
      )}

      {/* Feature Discovery Coaching Nudge (Bottom-Right) */}
      {showCompareNudge && compareCandidates.length === 0 && (
        <div className="fixed bottom-6 right-6 z-40 w-80 bg-brand-navy text-white rounded-2xl shadow-2xl border border-sky-400/30 p-4 flex items-start gap-3 animate-fade-in">
          <div className="w-8 h-8 rounded-xl bg-brand-sky/20 border border-brand-sky/30 flex items-center justify-center shrink-0 mt-0.5">
            <Scale className="w-4 h-4 text-brand-sky" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-white leading-snug">
              비교해보고 싶은 인플루언서가 있나요?
            </div>
            <p className="text-[11px] text-slate-300 mt-1 leading-relaxed">
              각 후보의 <strong className="text-brand-sky">[⚖ 비교]</strong> 버튼을 눌러 최대 3명까지 한눈에 비교 분석해 보세요!
            </p>
          </div>
          <button
            type="button"
            onClick={dismissCompareNudge}
            title="닫기"
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition shrink-0"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Dedicated Floating Compare Dock (Bottom-Right) */}
      {compareCandidates.length > 0 && (
        <div className="fixed bottom-6 right-6 z-40 w-72 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
          <div className="bg-brand-navy text-white px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-bold">
              <Scale className="w-3.5 h-3.5 text-brand-sky" />
              <span>후보 비교 ({compareCandidates.length}/3)</span>
            </div>
            <button
              type="button"
              onClick={() => onChangeCompareIds && onChangeCompareIds([])}
              className="text-[11px] text-slate-300 hover:text-white transition"
            >
              초기화
            </button>
          </div>
          <div className="p-3 space-y-2 max-h-48 overflow-y-auto">
            {compareCandidates.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl bg-slate-50 border border-slate-100"
              >
                <div className="min-w-0">
                  <div className="text-xs font-bold text-brand-navy truncate">@{c.instagram_id}</div>
                  <div className="text-[10px] text-slate-400">
                    매칭률 {c.overall_match_percentage > 0 ? `${c.overall_match_percentage}%` : '—'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleCompareId(c.id)}
                  title="비교 대상에서 빼기"
                  className="p-1 text-slate-400 hover:text-rose-500 transition"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
          <div className="p-3 pt-0">
            {compareCandidates.length >= 2 ? (
              <button
                type="button"
                onClick={() => onCompareSelected(compareCandidates.map((c) => c.id))}
                className="w-full py-2.5 rounded-xl bg-brand-sky hover:bg-sky-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition"
              >
                선택한 {compareCandidates.length}명 비교하기 <ArrowRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="w-full py-2.5 rounded-xl bg-slate-100 text-slate-400 text-xs font-semibold cursor-not-allowed"
              >
                1명 더 선택해 주세요 (2~3명)
              </button>
            )}
          </div>
        </div>
      )}

      {/* Product Info Edit Modal */}
      {editingProduct && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={() => setEditingProduct(null)}
        >
          <form
            onSubmit={handleSaveProduct}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md p-6 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-brand-navy">협찬 대상 제품 정보 설정</h3>
              <button
                type="button"
                onClick={() => setEditingProduct(null)}
                className="p-1 text-slate-400 hover:text-brand-navy"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">제품명 *</label>
                <input
                  type="text"
                  required
                  value={editingProduct.product_name}
                  onChange={(e) =>
                    setEditingProduct({ ...editingProduct, product_name: e.target.value })
                  }
                  placeholder="예: 저자극 시카 수분 앰플 30ml"
                  className="w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  제품 링크 URL (선택)
                </label>
                <input
                  type="url"
                  value={editingProduct.product_url}
                  onChange={(e) =>
                    setEditingProduct({ ...editingProduct, product_url: e.target.value })
                  }
                  placeholder="https://brand.com/products/cica-ampoule"
                  className="w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
                <p className="text-[11px] text-slate-400 mt-1.5">
                  제품 링크를 입력하고 저장하면 썸네일 이미지가 자동으로 추출됩니다.
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditingProduct(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                취소
              </button>
              <button
                type="submit"
                disabled={savingProduct}
                className="px-4 py-2 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-xs font-semibold disabled:opacity-50"
              >
                {savingProduct ? '저장 중...' : '저장하기'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
