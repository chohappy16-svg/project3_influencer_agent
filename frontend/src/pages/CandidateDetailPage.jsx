/**
 * [InfluenceOps] CandidateDetailPage.jsx
 * ==============================================================================
 * 개별 인플루언서 후보 상세 분석 화면
 *
 * 주요 기능:
 *   1. 인플루언서 프로필 요약 (계정명, 팔로워, 티어, 주력 포맷, 최종 승인/취소 토글)
 *   2. 뷰티·라이프스타일 프로필 (피부 타입, 가족/반려동물 노출, 소통 진정성 수준)
 *      - 게시물에서 근거가 없을 경우 임의 추측을 차단하고 '확인되지 않음'으로 안전 렌더링
 *   3. 시장 기준 예상 원고료 및 참여율(ER%), 티어 안내 카드
 *   4. 콘텐츠 근거 (최근 피드/릴스 3건 이미지 및 감도 점수 시각화)
 *   5. AI 종합 적합도 판정 결과 (매칭률 %, 핵심 판정 이유, 충돌 가능성 분석)
 *   6. [⚖ 다른 후보와 비교] 클릭 시 다른 후보를 즉시 선택할 수 있는 다이얼로그 모달
 * ==============================================================================
 */

import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  ExternalLink,
  Check,
  X,
  AlertTriangle,
  Sparkles,
  Loader2,
  Scale,
  CheckSquare,
  Square,
  ArrowRight,
} from 'lucide-react';
import { FitStatusBadge, ApprovalStateBadge } from '../components/StatusBadge';
import { InfoTooltip } from '../components/InfoTooltip';
import { campaignsApi } from '../api/client';

const SKIN_MAP = {
  DRY: '건성',
  OILY: '지성',
  COMBINATION: '복합성 / 수부지',
  SENSITIVE: '민감성',
  ACNE_PRONE: '트러블 / 여드름성',
  UNKNOWN: '확인되지 않음',
};

const FAMILY_PET_MAP = {
  BABY_KIDS: '영유아·자녀 노출',
  PET_COMPANION: '반려동물 노출',
  BOTH: '가족·반려동물 동반',
  NONE_VISIBLE: '노출 없음 확인',
  UNKNOWN: '확인되지 않음',
};

const AUTH_MAP = {
  HIGH: '높음 (소통·리뷰 진정성 우수)',
  MEDIUM: '보통',
  LOW: '낮음 (광고성/전단지 위주)',
  UNKNOWN: '확인되지 않음',
};

const TEXTURE_MAP = {
  NATURAL_GLOW: '자연스러운 윤광',
  MODERATE_EDIT: '적정 보정',
  HEAVY_FILTER: '과도한 필터/보정',
  UNANALYZABLE: '판독 불가',
};

const LIFESTYLE_MAP = {
  BEAUTY_HIGH_INVOLVEMENT: '뷰티 고관여 일상',
  DAILY_CASUAL: '자연스러운 일상',
  IRRELEVANT: '뷰티 무관 콘텐츠',
  UNANALYZABLE: '판독 불가',
};

function UnknownOrValue({ raw, mapObj }) {
  const isUnknown = !raw || raw === 'UNKNOWN';
  if (isUnknown) {
    return (
      <span className="inline-flex px-2.5 py-1 rounded-md bg-slate-100 text-brand-slate text-xs font-semibold border border-slate-200">
        확인되지 않음
      </span>
    );
  }
  return <span className="text-sm font-bold text-brand-navy">{mapObj[raw] || raw}</span>;
}

export default function CandidateDetailPage({
  campaign,
  candidate,
  allCandidates = [],
  compareIds = [],
  onBack,
  onStartCompare,
  onDecisionUpdated,
}) {
  const [detail, setDetail] = useState(candidate);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState(false);
  const [toast, setToast] = useState('');
  const [showComparePicker, setShowComparePicker] = useState(false);
  const [pickerIds, setPickerIds] = useState([]);

  const handleOpenCompare = () => {
    const otherIds = compareIds.filter((id) => id !== detail.id);
    if (otherIds.length >= 1) {
      const nextIds = [...otherIds, detail.id].slice(0, 3);
      onStartCompare && onStartCompare(nextIds);
      return;
    }
    setPickerIds([]);
    setShowComparePicker(true);
  };

  const togglePickerId = (id) => {
    setPickerIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [...prev.slice(1), id]; // 기준 후보 포함 최대 3명
      return [...prev, id];
    });
  };

  const comparableOthers = [...allCandidates]
    .filter((c) => c.id !== detail.id)
    .sort((a, b) => (b.overall_match_percentage || 0) - (a.overall_match_percentage || 0));

  // 상세 media_analysis 확보를 위해 compare API 1건 조회
  useEffect(() => {
    setLoading(true);
    campaignsApi
      .compare(campaign.id, [candidate.id])
      .then((res) => {
        if (res.candidates && res.candidates.length > 0) {
          setDetail(res.candidates[0]);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [campaign.id, candidate.id]);

  const handleDecision = async (decision) => {
    setDeciding(true);
    setToast('');
    try {
      const res = await campaignsApi.decide(detail.id, decision);
      setDetail((prev) => ({ ...prev, approval_state: res.approval_state }));
      setToast(
        `${res.message} (캠페인 누적 AI 비용: ${res.campaign_cumulative_cost_krw}원)`
      );
      if (onDecisionUpdated) onDecisionUpdated(detail.id, res.approval_state);
    } catch (err) {
      setToast(err.response?.data?.detail || '상태 업데이트 중 오류가 발생했습니다.');
    } finally {
      setDeciding(false);
    }
  };

  const igUrl = `https://www.instagram.com/${detail.instagram_id}/`;
  const mediaList = detail.media_analysis || [];
  const thumbs = detail.thumbnails || [];

  return (
    <div className="space-y-6 pb-12">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">후보 상세 분석</h1>
          <p className="text-sm text-slate-500 mt-1">{campaign.title} / @{detail.instagram_id}</p>
        </div>
        <button
          onClick={onBack}
          className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-brand-navy hover:bg-slate-50 flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> 분석 결과
        </button>
      </div>

      {toast && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800 flex items-center justify-between">
          <span>{toast}</span>
          <button onClick={() => setToast('')} className="text-emerald-600 font-bold ml-4">
            닫기
          </button>
        </div>
      )}

      {/* Profile Header Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-7 flex flex-wrap items-center justify-between gap-6">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5">
            <a
              href={igUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-2xl font-extrabold text-brand-navy hover:text-brand-sky inline-flex items-center gap-1.5"
            >
              @{detail.instagram_id}
              <ExternalLink className="w-4 h-4 text-slate-400" />
            </a>
            <FitStatusBadge status={detail.fit_status} tooltipText={detail.one_line_verdict} />
            <ApprovalStateBadge state={detail.approval_state} />
          </div>
          <div className="text-sm text-slate-600 font-medium">{detail.full_name || detail.influencer_tier}</div>
          <div className="text-xs text-slate-400">
            인스타그램 / 팔로워 {detail.followers_count?.toLocaleString() || 0}명 / 게시물{' '}
            {detail.posts_count?.toLocaleString() || 0}개 / {detail.influencer_tier}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <div className="text-right">
            <div className="text-xs text-slate-400 font-medium">브랜드 매칭률</div>
            <div className="text-4xl font-extrabold text-brand-mint mt-0.5">
              {detail.overall_match_percentage}%
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleOpenCompare}
              className="px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-bold text-brand-navy hover:bg-slate-50 flex items-center gap-1.5 whitespace-nowrap shrink-0"
            >
              <Scale className="w-3.5 h-3.5 text-brand-sky" /> 다른 후보와 비교
            </button>
            {detail.approval_state === 'APPROVED' ? (
              <button
                type="button"
                disabled={deciding}
                onClick={() => handleDecision('PENDING')}
                className="px-5 py-2.5 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-brand-mint text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-60"
                title="클릭 시 선정을 취소하고 검토 대기 상태로 되돌립니다"
              >
                {deciding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-4 h-4" />}
                선정 취소
              </button>
            ) : (
              <button
                type="button"
                disabled={deciding}
                onClick={() => handleDecision('APPROVED')}
                className="px-5 py-2.5 rounded-xl bg-brand-mint hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition disabled:opacity-60"
              >
                {deciding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-4 h-4" />}
                선정 확정
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Middle Row: Beauty/Lifestyle Profile (8) + Fee/ER Card (4) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-7">
          <div className="mb-5">
            <h2 className="text-base font-bold text-brand-navy">뷰티·라이프스타일 프로필</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              게시물에서 근거가 확인되지 않은 항목은 추측하지 않고 &lsquo;확인되지 않음&rsquo;으로 표기합니다.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1.5">피부 타입</div>
              <UnknownOrValue raw={detail.skin_type} mapObj={SKIN_MAP} />
            </div>
            <div>
              <div className="text-xs text-slate-400 mb-1.5">가족·반려동물 노출</div>
              <UnknownOrValue raw={detail.family_pet_exposure} mapObj={FAMILY_PET_MAP} />
            </div>
            <div className="sm:col-span-2 pt-3 border-t border-slate-100">
              <div className="text-xs text-slate-400 mb-1.5 inline-flex items-center">
                소통 진정성
                <InfoTooltip title="소통 진정성 (AI 질적 평가)" position="top">
                  <p>최근 피드 캡션과 소통 패턴을 AI가 분석해 진성 소통 여부를 판별합니다.</p>
                  <p className="text-emerald-300">• 높음: 솔직한 후기·찐팬 소통 중심</p>
                  <p className="text-amber-300">• 낮음: 복붙 광고·품앗이 봇 의심</p>
                </InfoTooltip>
              </div>
              <UnknownOrValue raw={detail.communication_authenticity} mapObj={AUTH_MAP} />
            </div>
          </div>
        </div>

        <div className="lg:col-span-4 bg-white rounded-2xl border border-slate-200/80 p-7 flex flex-col justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">예상 원고료</div>
            <div className="text-2xl font-extrabold text-brand-navy mt-1">
              {detail.recommended_fee || '산정 불가'}
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              팔로워 규모({detail.followers_count?.toLocaleString() || 0}명) 기반 자동 산정
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 pt-5 mt-5 border-t border-slate-100">
            <div>
              <div className="text-xs text-slate-400 inline-flex items-center">
                평균 반응률 (ER)
                <InfoTooltip title="ER% (Engagement Rate, 참여율)" position="top">
                  <p>팔로워 중 실제로 좋아요·댓글을 남기는 진성 팬의 비율입니다.</p>
                  <p className="text-slate-300">• 공식: 평균 (좋아요+댓글) ÷ 팔로워 × 100</p>
                  <p className="text-emerald-300">• 3.0% 이상: 초우수 / 1.5~3%: 양호</p>
                </InfoTooltip>
              </div>
              <div className="text-lg font-extrabold text-brand-navy mt-0.5">
                {detail.engagement_rate > 0 ? `${detail.engagement_rate}%` : '—'}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">인플루언서 티어</div>
              <div className="text-xs font-bold text-brand-navy mt-1.5">{detail.influencer_tier}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row: Media Evidence (7) + AI Verdict (5) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200/80 p-7">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-brand-navy">콘텐츠 근거 (최근 피드 3건)</h2>
          </div>

          {loading ? (
            <div className="py-8 text-center text-xs text-slate-400">미디어 분석 데이터를 불러오는 중...</div>
          ) : mediaList.length === 0 && thumbs.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              수집된 피드 이미지가 없습니다. (비공개 계정이거나 이미지 분석이 제한된 계정입니다)
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {(mediaList.length > 0 ? mediaList : thumbs.map((_, i) => ({ scene_type_kr: `피드 콘텐츠 ${i + 1}`, aesthetic_score: '-' }))).map(
                (m, idx) => (
                  <a
                    key={idx}
                    href={igUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group rounded-2xl border border-slate-200/80 bg-slate-50/40 overflow-hidden flex flex-col hover:border-brand-sky/50 hover:shadow-md transition"
                  >
                    <div className="relative aspect-square w-full bg-slate-200 overflow-hidden">
                      {thumbs[idx] ? (
                        <img
                          src={thumbs[idx]}
                          alt={`피드 ${idx + 1}`}
                          className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-sm font-bold text-slate-400">
                          피드 0{idx + 1}
                        </div>
                      )}
                      <span className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-brand-navy/80 backdrop-blur-sm text-white text-[11px] font-bold">
                        0{idx + 1}
                      </span>
                      {m.aesthetic_score !== undefined && m.aesthetic_score !== '-' && (
                        <span className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-md bg-brand-mint/90 backdrop-blur-sm text-white text-[11px] font-bold">
                          감도 {m.aesthetic_score}/10
                        </span>
                      )}
                    </div>
                    <div className="p-3.5 space-y-1.5 flex-1 flex flex-col justify-between bg-white">
                      <div className="text-xs font-bold text-brand-navy line-clamp-2">
                        {m.scene_type_kr || '피드 연출'}
                      </div>
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {m.texture_rendering && (
                          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-semibold">
                            {TEXTURE_MAP[m.texture_rendering] || m.texture_rendering}
                          </span>
                        )}
                        {m.lifestyle_context && (
                          <span className="px-2 py-0.5 rounded bg-sky-50 text-brand-sky text-[10px] font-semibold">
                            {LIFESTYLE_MAP[m.lifestyle_context] || m.lifestyle_context}
                          </span>
                        )}
                      </div>
                    </div>
                  </a>
                )
              )}
            </div>
          )}
        </div>

        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200/80 p-7 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-base font-bold text-brand-navy mb-3">
              <Sparkles className="w-4 h-4 text-brand-sky" /> AI 종합 판정
            </div>
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/70 text-sm font-bold text-brand-navy leading-relaxed mb-4">
              {detail.one_line_verdict}
            </div>
            <ul className="space-y-2.5 text-xs text-slate-600 leading-relaxed">
              {(detail.rationale_bullets || []).map((b, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-sky mt-1.5 shrink-0" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100 flex items-start gap-2 text-[11px] text-slate-400">
            <AlertTriangle className="w-3.5 h-3.5 text-brand-orange shrink-0 mt-0.5" />
            <span>
              AI 판정은 최종 의사결정을 보조합니다. 최근 경쟁 브랜드 협찬 여부는 승인 전 직접 확인해 주세요.
            </span>
          </div>
        </div>
      </div>

      {/* Compare Partner Picker Modal */}
      {showComparePicker && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4"
          onClick={() => setShowComparePicker(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-brand-navy text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-brand-sky" />
                <h3 className="text-sm font-bold">누구와 비교할까요?</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowComparePicker(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-3 bg-sky-50/70 border-b border-sky-100 text-xs text-brand-navy flex items-center justify-between">
              <span>
                기준 후보: <strong>@{detail.instagram_id}</strong> ({detail.overall_match_percentage}%)
              </span>
              <span className="text-[11px] text-slate-500">비교 대상 1~2명 선택</span>
            </div>

            <div className="p-4 max-h-80 overflow-y-auto divide-y divide-slate-100">
              {comparableOthers.length === 0 ? (
                <div className="py-10 text-center text-xs text-slate-400">
                  현재 캠페인에 비교할 수 있는 다른 후보가 없습니다.
                </div>
              ) : (
                comparableOthers.map((c) => {
                  const checked = pickerIds.includes(c.id);
                  return (
                    <div
                      key={c.id}
                      onClick={() => togglePickerId(c.id)}
                      className={`py-3 px-3 rounded-xl cursor-pointer flex items-center justify-between gap-3 transition ${
                        checked ? 'bg-sky-50/70' : 'hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {checked ? (
                          <CheckSquare className="w-4 h-4 text-brand-sky shrink-0" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-300 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-brand-navy truncate">
                            @{c.instagram_id}
                          </div>
                          <div className="text-[11px] text-slate-400 truncate">
                            {c.influencer_tier || '인플루언서'} · {c.recommended_fee || '—'}
                          </div>
                        </div>
                      </div>
                      <span className="text-xs font-extrabold text-brand-mint shrink-0">
                        {c.overall_match_percentage > 0 ? `${c.overall_match_percentage}%` : '—'}
                      </span>
                    </div>
                  );
                })
              )}
            </div>

            <div className="px-5 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowComparePicker(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                취소
              </button>
              <button
                type="button"
                disabled={pickerIds.length === 0}
                onClick={() => {
                  setShowComparePicker(false);
                  onStartCompare && onStartCompare([detail.id, ...pickerIds]);
                }}
                className="px-5 py-2 rounded-xl bg-brand-sky hover:bg-sky-500 text-white text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {pickerIds.length > 0
                  ? `선택한 ${pickerIds.length + 1}명 비교하기`
                  : '비교할 후보를 선택하세요'}{' '}
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
