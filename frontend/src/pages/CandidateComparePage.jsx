/**
 * [InfluenceOps] CandidateComparePage.jsx
 * ==============================================================================
 * 인플루언서 후보 1:1 및 다자(최대 3인) 좌우 비교 화면
 *
 * 주요 기능:
 *   1. 좌우 나란히 배치된 비교 뷰 (팔로워, 예상 원고료, 매칭률, 주력 포맷, 피부 타입, 진정성)
 *   2. 최근 피드 썸네일 및 감도 점수 비교
 *   3. 비교 화면 이탈 없이 바로 3번째 후보를 추가할 수 있는 [+ 후보 추가] 다이얼로그
 *   4. 후보별 최종 승인 / 승인 취소 독립 제어
 * ==============================================================================
 */

import React, { useState, useEffect } from 'react';
import { ArrowLeft, Check, X, ExternalLink, AlertCircle, Loader2, Plus, Scale } from 'lucide-react';
import { campaignsApi } from '../api/client';
import { ApprovalStateBadge, FitStatusBadge } from '../components/StatusBadge';
import { InfoTooltip } from '../components/InfoTooltip';

const SKIN_MAP = {
  DRY: '건성',
  OILY: '지성',
  COMBINATION: '복합성',
  SENSITIVE: '민감성',
  ACNE_PRONE: '트러블성',
  UNKNOWN: '확인되지 않음',
};

const FAMILY_PET_MAP = {
  BABY_KIDS: '영유아·자녀 노출',
  PET_COMPANION: '반려동물 노출',
  BOTH: '가족·반려동물 동반',
  NONE_VISIBLE: '노출 없음',
  UNKNOWN: '확인되지 않음',
};

const AUTH_MAP = {
  HIGH: '높음 (소통·리뷰 진정성 우수)',
  MEDIUM: '보통',
  LOW: '낮음 (광고·전단지 위주)',
  UNKNOWN: '확인되지 않음',
};

function UnknownBadge({ value, mapObj }) {
  if (!value || value === 'UNKNOWN') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded bg-slate-100 text-brand-slate text-[11px] font-semibold">
        확인되지 않음
      </span>
    );
  }
  return <span className="text-xs font-bold text-brand-navy">{(mapObj && mapObj[value]) || value}</span>;
}

export default function CandidateComparePage({
  campaign,
  selectedIds,
  allCandidates = [],
  onUpdateCompareIds,
  onBack,
  onDecisionUpdated,
}) {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [decidingId, setDecidingId] = useState(null);
  const [toast, setToast] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);

  const remainingCandidates = [...allCandidates]
    .filter((c) => !selectedIds.includes(c.id))
    .sort((a, b) => (b.overall_match_percentage || 0) - (a.overall_match_percentage || 0));

  useEffect(() => {
    setLoading(true);
    campaignsApi
      .compare(campaign.id, selectedIds)
      .then((res) => setCandidates(res.candidates || []))
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [campaign.id, selectedIds]);

  const handleDecision = async (resultId, decision) => {
    setDecidingId(resultId);
    setToast('');
    try {
      const res = await campaignsApi.decide(resultId, decision);
      setCandidates((prev) =>
        prev.map((c) => (c.id === resultId ? { ...c, approval_state: res.approval_state } : c))
      );
      setToast(
        `${res.message} (캠페인 누적 AI 비용: ${res.campaign_cumulative_cost_krw}원)`
      );
      if (onDecisionUpdated) onDecisionUpdated(resultId, res.approval_state);
    } catch (err) {
      setToast(err.response?.data?.detail || '승인 처리 중 오류가 발생했습니다.');
    } finally {
      setDecidingId(null);
    }
  };

  const avgAestheticScore = (c) => {
    const arr = c.media_analysis || [];
    if (arr.length === 0) return 0;
    const sum = arr.reduce((acc, m) => acc + (m.aesthetic_score || 0), 0);
    return Math.round((sum / arr.length) * 10);
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">후보 {candidates.length || selectedIds.length}인 비교</h1>
          <p className="text-sm text-slate-500 mt-1">
            {campaign.title} / 같은 기준으로 후보들의 적합성을 좌우 비교하세요.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          {selectedIds.length < 3 && remainingCandidates.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 rounded-xl bg-brand-sky hover:bg-sky-500 text-white text-xs font-bold flex items-center gap-1.5 whitespace-nowrap transition"
            >
              <Plus className="w-3.5 h-3.5" /> 후보 추가 ({selectedIds.length}/3)
            </button>
          )}
          <button
            onClick={onBack}
            className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-brand-navy hover:bg-slate-50 flex items-center gap-1.5 whitespace-nowrap"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> 분석 결과
          </button>
        </div>
      </div>

      {toast && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800 flex items-center justify-between">
          <span>{toast}</span>
          <button onClick={() => setToast('')} className="text-emerald-600 font-bold ml-4">
            닫기
          </button>
        </div>
      )}

      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 py-20 text-center text-sm text-slate-400">
          비교 데이터를 불러오는 중...
        </div>
      ) : candidates.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 py-20 text-center text-sm text-slate-400">
          비교할 후보 데이터를 찾지 못했습니다.
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden">
          <div
            className="grid divide-x divide-slate-100"
            style={{
              gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))`,
            }}
          >
            {/* Row 1: Header Profiles */}
            <div className="p-6 bg-slate-50/50">
              <div className="text-xs font-bold text-brand-navy">비교 기준</div>
              <div className="text-[11px] text-slate-400 mt-1">브랜드 DNA + 캠페인 가이드라인</div>
            </div>
            {candidates.map((c) => (
              <div key={c.id} className="p-6 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <a
                    href={`https://www.instagram.com/${c.instagram_id}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-lg font-extrabold text-brand-navy hover:text-brand-sky inline-flex items-center gap-1 truncate"
                  >
                    @{c.instagram_id}
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  </a>
                  <ApprovalStateBadge state={c.approval_state} />
                </div>
                <div className="text-xs text-slate-400">
                  팔로워 {c.followers_count?.toLocaleString()}명 · {c.influencer_tier}
                </div>
                <div className="flex items-baseline gap-2 pt-1">
                  <span className="text-3xl font-extrabold text-brand-mint">
                    {c.overall_match_percentage}%
                  </span>
                  <span className="text-xs text-slate-400">브랜드 매칭률</span>
                  <div className="ml-auto">
                    <FitStatusBadge status={c.fit_status} tooltipText={c.one_line_verdict} />
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Row 2: Visual Score Bar */}
          <div
            className="grid divide-x divide-slate-100 border-t border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-4 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600 flex items-center">
              <span>비주얼 감도 점수</span>
              <InfoTooltip title="비주얼 감도 점수 (Visual Aesthetic)" align="left">
                <p>최근 피드 이미지·릴스의 조명, 구도, 색감, 피부 표현 완성도를 AI 비전이 100점 만점으로 환산한 평균 점수입니다.</p>
                <p className="text-emerald-300">• 80점 이상: 브랜드 화보급 고감도 무드</p>
                <p className="text-sky-300">• 60~79점: 자연스러운 데일리 연출</p>
              </InfoTooltip>
            </div>
            {candidates.map((c) => {
              const score = avgAestheticScore(c) || c.overall_match_percentage;
              return (
                <div key={c.id} className="p-4 px-6 flex items-center gap-3">
                  <span className="text-xs font-extrabold text-brand-navy w-8">{score}</span>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-mint rounded-full" style={{ width: `${score}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Row 3: Recent Media Thumbnails Gallery */}
          <div
            className="grid divide-x divide-slate-100 border-t border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-5 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">
              최근 콘텐츠 미리보기
              <div className="text-[11px] font-normal text-slate-400 mt-1">클릭 시 인스타 원문 이동</div>
            </div>
            {candidates.map((c) => {
              const thumbs = c.thumbnails || [];
              const mediaList = c.media_analysis || [];
              const igUrl = `https://www.instagram.com/${c.instagram_id}/`;
              return (
                <div key={c.id} className="p-4 px-6">
                  {thumbs.length === 0 ? (
                    <div className="h-24 rounded-xl bg-slate-50 border border-dashed border-slate-200 flex items-center justify-center text-[11px] text-slate-400">
                      수집된 피드 이미지가 없습니다
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2.5">
                      {thumbs.slice(0, 3).map((tUrl, idx) => {
                        const mInfo = mediaList[idx] || {};
                        return (
                          <a
                            key={idx}
                            href={igUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="group relative aspect-square rounded-xl overflow-hidden bg-slate-100 border border-slate-200/80 block"
                            title={mInfo.scene_type_kr || `피드 ${idx + 1}`}
                          >
                            <img
                              src={tUrl}
                              alt={`@${c.instagram_id} 피드 ${idx + 1}`}
                              className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                            />
                            {mInfo.aesthetic_score && (
                              <span className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded bg-brand-navy/80 backdrop-blur-sm text-white text-[10px] font-bold">
                                {mInfo.aesthetic_score}/10
                              </span>
                            )}
                            {mInfo.scene_type_kr && (
                              <div className="absolute inset-x-0 bottom-0 p-1.5 bg-gradient-to-t from-black/75 via-black/40 to-transparent">
                                <div className="text-[10px] font-semibold text-white truncate">
                                  {mInfo.scene_type_kr}
                                </div>
                              </div>
                            )}
                          </a>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Section Banner: UNKNOWN Notice */}
          <div className="px-6 py-2.5 bg-sky-50/70 border-y border-sky-100 flex items-center gap-6 text-xs">
            <span className="font-bold text-brand-navy">뷰티·라이프스타일 프로필</span>
            <span className="text-slate-500">
              미확인 정보는 UNKNOWN으로 표시하며, &lsquo;없음&rsquo;이나 &lsquo;0원 시딩&rsquo;으로 간주하지 않습니다.
            </span>
          </div>

          {/* Row: Skin Type */}
          <div
            className="grid divide-x divide-slate-100 border-b border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-4 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">피부 타입</div>
            {candidates.map((c) => (
              <div key={c.id} className="p-4 px-6">
                <UnknownBadge value={c.skin_type} mapObj={SKIN_MAP} />
              </div>
            ))}
          </div>

          {/* Row: Family/Pet */}
          <div
            className="grid divide-x divide-slate-100 border-b border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-4 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">가족·반려동물 노출</div>
            {candidates.map((c) => (
              <div key={c.id} className="p-4 px-6">
                <UnknownBadge value={c.family_pet_exposure} mapObj={FAMILY_PET_MAP} />
              </div>
            ))}
          </div>

          {/* Row: Fee */}
          <div
            className="grid divide-x divide-slate-100 border-b border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-4 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">예상 원고료</div>
            {candidates.map((c) => (
              <div key={c.id} className="p-4 px-6">
                <div className="text-base font-extrabold text-brand-navy">{c.recommended_fee}</div>
              </div>
            ))}
          </div>

          {/* Row: ER% & Auth */}
          <div
            className="grid divide-x divide-slate-100 border-b border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-4 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">평균 반응률 / 진정성</div>
            {candidates.map((c) => (
              <div key={c.id} className="p-4 px-6 text-xs font-bold text-brand-navy flex items-center gap-2">
                <span>ER {c.engagement_rate > 0 ? `${c.engagement_rate}%` : '—'}</span>
                <span className="text-slate-300">·</span>
                <span>소통 {AUTH_MAP[c.communication_authenticity] || '파악 불가'}</span>
              </div>
            ))}
          </div>

          {/* Row: Strengths & Rationale */}
          <div
            className="grid divide-x divide-slate-100 border-b border-slate-100"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-5 px-6 bg-slate-50/50 text-xs font-semibold text-slate-600">AI 판정 & 강점</div>
            {candidates.map((c) => (
              <div key={c.id} className="p-5 px-6 space-y-2 text-xs text-slate-600">
                <div className="font-bold text-brand-navy">{c.one_line_verdict}</div>
                <ul className="space-y-1 list-disc pl-4">
                  {(c.rationale_bullets || []).slice(0, 3).map((b, idx) => (
                    <li key={idx}>{b}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Row: Final Decision Buttons */}
          <div
            className="grid divide-x divide-slate-100 bg-slate-50/30"
            style={{ gridTemplateColumns: `200px repeat(${candidates.length}, minmax(240px, 1fr))` }}
          >
            <div className="p-5 px-6 bg-slate-50/50 text-xs font-bold text-brand-navy flex items-center">
              최종 결정
            </div>
            {candidates.map((c) => {
              const isApproved = c.approval_state === 'APPROVED';
              return (
                <div key={c.id} className="p-5 px-6 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={decidingId === c.id}
                    onClick={() => handleDecision(c.id, isApproved ? 'PENDING' : 'APPROVED')}
                    title={isApproved ? '클릭 시 선정을 취소하고 대기 상태로 되돌립니다' : '내부 섭외 대상으로 선정 확정'}
                    className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                      isApproved
                        ? 'bg-emerald-50 text-brand-mint border border-emerald-300 hover:bg-red-50 hover:text-red-600 hover:border-red-200'
                        : 'bg-brand-mint hover:bg-emerald-600 text-white shadow-sm'
                    }`}
                  >
                    {decidingId === c.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Check className="w-3.5 h-3.5" />
                    )}
                    {isApproved ? '선정 취소' : '선정 확정'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200/80 px-6 py-4 flex items-center gap-3 text-xs text-slate-500">
        <AlertCircle className="w-4 h-4 text-brand-sky shrink-0" />
        <span>
          <strong>매칭률만으로 결정하지 마세요.</strong> 콘텐츠 근거와 예상 원고료를 함께 확인한 뒤 적합한 후보를 선정 확정하세요.
        </span>
      </div>

      {/* Add Candidate to Compare Modal */}
      {showAddModal && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4"
          onClick={() => setShowAddModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-brand-navy text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-brand-sky" />
                <h3 className="text-sm font-bold">비교 후보 추가 ({selectedIds.length}/3)</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 max-h-80 overflow-y-auto divide-y divide-slate-100">
              {remainingCandidates.map((c) => (
                <div
                  key={c.id}
                  onClick={() => {
                    const next = [...selectedIds, c.id].slice(0, 3);
                    onUpdateCompareIds && onUpdateCompareIds(next);
                    setShowAddModal(false);
                  }}
                  className="py-3 px-3 rounded-xl hover:bg-sky-50/60 cursor-pointer flex items-center justify-between gap-3 transition"
                >
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-brand-navy truncate">@{c.instagram_id}</div>
                    <div className="text-[11px] text-slate-400 truncate">
                      {c.influencer_tier || '인플루언서'} · {c.recommended_fee || '—'}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-extrabold text-brand-mint">
                      {c.overall_match_percentage > 0 ? `${c.overall_match_percentage}%` : '—'}
                    </span>
                    <span className="px-2 py-1 rounded-lg bg-sky-50 text-brand-sky text-[11px] font-bold">
                      + 추가
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
