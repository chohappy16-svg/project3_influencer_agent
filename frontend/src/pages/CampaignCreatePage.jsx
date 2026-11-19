/**
 * [InfluenceOps] CampaignCreatePage.jsx
 * ==============================================================================
 * 신규 협찬 캠페인 생성 화면
 *
 * 주요 기능:
 *   1. 캠페인 기본 정보: 캠페인명, 홍보 대상 제품명, 단일 제품 링크 URL, 기간(시작/종료일)
 *   2. 희망 콘텐츠 포맷 선택: ✨ 자유/혼합 | 📷 이미지 피드 협찬 | 🎬 릴스(숏폼) 협찬
 *   3. 5대 핵심 가이드라인 설정: 타깃 고객, 콘텐츠 무드, 핵심 메시지, 필수 조건, 제외 조건
 *   4. 협찬 컨셉 복사(template) 연동: 기존 캠페인의 제품 및 5대 가이드라인 사전 채우기
 * ==============================================================================
 */

import React, { useState, useEffect } from 'react';
import { Check, ArrowRight, Loader2, AlertCircle, Copy } from 'lucide-react';
import { campaignsApi } from '../api/client';

function formatDateInput(dateObj) {
  return dateObj.toISOString().split('T')[0];
}

function parseAppealLines(appealText) {
  const lines = (appealText || '').split('\n');
  const extract = (idx, prefix, fallback) => {
    const found = lines[idx];
    if (!found) return fallback;
    return found.replace(new RegExp(`^\\d+\\.\\s*${prefix}:?\\s*`), '').trim() || fallback;
  };
  return {
    g1: extract(0, '타깃 고객', '20~35세 · 건조하고 민감한 피부'),
    g2: extract(1, '콘텐츠 무드', '자연광, 깨끗한 배경, 피부 본연의 질감'),
    g3: extract(2, '핵심 메시지', '수분 장벽 케어와 순한 성분 중심의 실제 사용 후기'),
    g4: extract(3, '필수 조건', '제품 패키지 정면 노출 및 제형 컷 포함 · 공개 계정'),
    g5: extract(4, '제외 조건', '과도한 필터 보정, 자극적 광고 전단지, 경쟁 제품 동시 협찬 제외'),
  };
}

export default function CampaignCreatePage({ user, template, onBack, onCreated }) {
  const today = new Date();
  const defaultEnd = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000);

  const [title, setTitle] = useState(
    template ? `[복사] ${template.title}` : '11월 저자극 시카 수분 앰플 캠페인'
  );
  const [productName, setProductName] = useState(
    template?.product_name || '저자극 시카 수분 앰플 30ml'
  );
  const [productUrl, setProductUrl] = useState(template?.product_url || '');
  const [channel, setChannel] = useState('인스타그램');
  const [preferredFormat, setPreferredFormat] = useState(template?.preferred_format || 'MIXED');
  const [startDate, setStartDate] = useState(formatDateInput(today));
  const [endDate, setEndDate] = useState(formatDateInput(defaultEnd));

  const parsed = parseAppealLines(template?.campaign_appeal);
  const [g1, setG1] = useState(template ? parsed.g1 : '20~35세 · 건조하고 민감한 피부');
  const [g2, setG2] = useState(template ? parsed.g2 : '자연광, 깨끗한 배경, 피부 본연의 질감');
  const [g3, setG3] = useState(
    template ? parsed.g3 : '수분 장벽 케어와 순한 성분 중심의 실제 사용 후기'
  );
  const [g4, setG4] = useState(
    template ? parsed.g4 : '제품 패키지 정면 노출 및 제형 컷 포함 · 공개 계정'
  );
  const [g5, setG5] = useState(
    template ? parsed.g5 : '과도한 필터 보정, 자극적 광고 전단지, 경쟁 제품 동시 협찬 제외'
  );

  useEffect(() => {
    if (template) {
      setTitle(`[복사] ${template.title}`);
      setProductName(template.product_name || '');
      setProductUrl(template.product_url || '');
      setPreferredFormat(template.preferred_format || 'MIXED');
      const p = parseAppealLines(template.campaign_appeal);
      setG1(p.g1);
      setG2(p.g2);
      setG3(p.g3);
      setG4(p.g4);
      setG5(p.g5);
    }
  }, [template]);

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setLoading(true);

    const combinedAppeal = [
      `1. 타깃 고객: ${g1}`,
      `2. 콘텐츠 무드: ${g2}`,
      `3. 핵심 메시지: ${g3}`,
      `4. 필수 조건: ${g4}`,
      `5. 제외 조건: ${g5}`,
    ].join('\n');

    try {
      const created = await campaignsApi.create({
        title,
        product_name: productName,
        product_url: productUrl.trim() || null,
        preferred_format: preferredFormat,
        status: 'READY',
        start_date: startDate,
        end_date: endDate,
        campaign_appeal: combinedAppeal,
      });
      onCreated(created);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || '캠페인 생성 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">새 캠페인 만들기</h1>
          <p className="text-sm text-slate-500 mt-1">
            제품과 5대 가이드라인으로 이번 캠페인의 분석 기준을 설정하세요.
          </p>
        </div>
        <button onClick={onBack} className="text-xs font-semibold text-slate-500 hover:text-brand-navy">
          캠페인 목록으로 돌아가기
        </button>
      </div>

      {/* Stepper */}
      <div className="bg-white rounded-2xl border border-slate-200/80 px-6 py-4 flex items-center justify-between text-xs font-semibold">
        <span className="flex items-center gap-1.5 text-brand-navy">
          <Check className="w-4 h-4 text-brand-mint" /> 브랜드 DNA 연결
        </span>
        <span className="text-slate-300">→</span>
        <span className="text-brand-sky font-bold">01 캠페인 정보</span>
        <span className="text-slate-300">→</span>
        <span className="text-slate-400">02 후보 업로드</span>
      </div>

      {template && (
        <div className="p-3.5 rounded-xl bg-sky-50 border border-sky-200 flex items-center gap-2.5 text-xs text-brand-navy">
          <Copy className="w-4 h-4 text-brand-sky shrink-0" />
          <span>
            <strong>&lsquo;{template.title}&rsquo;</strong>의 협찬 컨셉(제품·포맷·5대 가이드라인)이 복사되었습니다. 캠페인명과 기간만 확인 후 바로 생성하세요!
          </span>
        </div>
      )}

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 flex items-center gap-2 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Form (8 cols) */}
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-7 space-y-6">
          <div>
            <h2 className="text-base font-bold text-brand-navy mb-4">캠페인 기본 정보</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">캠페인명 *</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">홍보 제품 *</label>
                  <input
                    type="text"
                    required
                    value={productName}
                    onChange={(e) => setProductName(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">채널</label>
                  <select
                    value={channel}
                    onChange={(e) => setChannel(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 bg-white focus:outline-none focus:border-brand-sky"
                  >
                    <option value="인스타그램">인스타그램</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  제품 링크 URL (선택)
                </label>
                <input
                  type="url"
                  value={productUrl}
                  onChange={(e) => setProductUrl(e.target.value)}
                  placeholder="https://brand.com/products/cica-ampoule"
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  링크만 입력하면 제품 썸네일이 자동으로 추출되며, 대시보드에서 바로 제품을 보러갈 수 있습니다.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    캠페인 시작일
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    캠페인 종료일
                  </label>
                  <input
                    type="date"
                    value={endDate}
                    min={startDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-2">
                  희망 협찬 포맷 *
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    {
                      id: 'MIXED',
                      emoji: '✨',
                      label: '자유/혼합',
                      desc: '피드·릴스 구분 없이 최적 후보 탐색',
                    },
                    {
                      id: 'FEED',
                      emoji: '📷',
                      label: '이미지 피드 협찬',
                      desc: '사진 무드·디테일 컷 중심 (표준 단가)',
                    },
                    {
                      id: 'REELS',
                      emoji: '🎬',
                      label: '릴스(숏폼) 협찬',
                      desc: '릴스 특화 크리에이터 우대 & 릴스 단가 적용',
                    },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setPreferredFormat(opt.id)}
                      className={`text-left p-3.5 rounded-xl border transition ${
                        preferredFormat === opt.id
                          ? 'border-brand-sky bg-sky-50/70 ring-1 ring-brand-sky'
                          : 'border-slate-200 bg-white hover:bg-slate-50'
                      }`}
                    >
                      <div className="text-xs font-bold text-brand-navy flex items-center gap-1.5">
                        <span>{opt.emoji}</span>
                        <span>{opt.label}</span>
                      </div>
                      <div className="text-[11px] text-slate-500 mt-1 leading-snug">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100">
            <h2 className="text-base font-bold text-brand-navy">5대 가이드라인</h2>
            <p className="text-xs text-slate-400 mt-0.5 mb-4">
              브랜드 DNA에 더해 이번 캠페인에만 적용할 조건입니다.
            </p>

            <div className="space-y-3">
              {[
                { num: '01', label: '타깃 고객', val: g1, set: setG1 },
                { num: '02', label: '콘텐츠 무드', val: g2, set: setG2 },
                { num: '03', label: '핵심 메시지', val: g3, set: setG3 },
                { num: '04', label: '필수 조건', val: g4, set: setG4 },
                { num: '05', label: '제외 조건', val: g5, set: setG5 },
              ].map((item) => (
                <div
                  key={item.num}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-3 rounded-xl border border-slate-200/80 bg-slate-50/40"
                >
                  <div className="w-32 shrink-0 flex items-center gap-2 text-xs font-bold text-brand-navy">
                    <span className="text-slate-400">{item.num}</span>
                    <span>{item.label}</span>
                  </div>
                  <input
                    type="text"
                    required
                    value={item.val}
                    onChange={(e) => item.set(e.target.value)}
                    className="flex-1 px-3 py-1.5 text-sm bg-white rounded-lg border border-slate-200 focus:outline-none focus:border-brand-sky"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={onBack}
              className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2.5 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-sm font-semibold flex items-center gap-2 transition disabled:opacity-60"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              저장하고 후보 업로드 <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right: Connected DNA Info (4 cols) */}
        <div className="lg:col-span-4 space-y-5">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <div className="text-xs font-bold text-slate-400 mb-2">연결된 브랜드 DNA</div>
            <div className="text-base font-bold text-brand-navy">{user?.company_name || '클린뷰티 랩'}</div>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              {user?.brand_dna_summary ||
                '브랜드 DNA는 기본 기준으로 유지되고, 캠페인 가이드라인은 추가 조건으로 적용됩니다.'}
            </p>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <div className="text-sm font-bold text-brand-navy mb-4">분석은 이렇게 진행돼요</div>
            <div className="space-y-3 text-xs text-slate-600">
              <div className="flex items-start gap-2.5">
                <span className="font-bold text-brand-sky">01</span>
                <span>부적합 후보(광고 봇·비공개) 1차 스크리닝 (Gemini Flash)</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold text-brand-sky">02</span>
                <span>이미지·릴스·캐러셀 3장 규격화 미디어 전처리</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold text-brand-sky">03</span>
                <span>브랜드 매칭률과 UNKNOWN 환각 방어 판단 근거 생성 (GPT-4o)</span>
              </div>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
