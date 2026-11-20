import React, { useState, useEffect, useMemo } from 'react';
import { Upload, Check, FileText, Download, ArrowRight, ArrowLeft, AlertCircle, Edit3, X, Sparkles } from 'lucide-react';
import { campaignsApi } from '../api/client';

const HEADER_TOKENS = new Set(['instagram_id', 'id', 'username', 'handle', '인스타아이디', '아이디', '계정']);

// 경과 시간(초)별 동적 로딩 안내 큐 (3초 -> 8초(+5) -> 13초(+5) -> 18초(+5) -> 23초(+5))
const LOADING_STEPS = [
  { afterSec: 0, emoji: '🚀', title: '피드 수집 시작', desc: '후보자들의 최근 프로필과 릴스 콘텐츠를 불러오고 있어요.' },
  { afterSec: 3, emoji: '⚡', title: '서두르고 있어요!', desc: '게시물의 이미지 감도와 톤앤매너를 꼼꼼히 살피는 중입니다.' },
  { afterSec: 8, emoji: '🔍', title: '브랜드 DNA 정밀 대조 중', desc: '우리 브랜드 추구미와 캠페인 가이드라인을 AI가 한 땀 한 땀 검증하고 있어요.' },
  { afterSec: 13, emoji: '💡', title: '추천 원고료 & 매칭률 계산', desc: '조금만 기다려주세요! 팔로워 대비 적정 협찬 단가를 산정하고 있어요.' },
  { afterSec: 18, emoji: '🎯', title: '마무리 정리 중!', desc: '거의 다 끝났습니다! 분석 결과를 보기 쉽게 정리하고 있어요.' },
  { afterSec: 23, emoji: '☕', title: '전수 정밀 분석 마무리 중', desc: '후보 수가 많거나 심층 비전 분석 중이라 시간이 조금 더 소요되고 있어요. 안전하게 완료할게요!' },
];

function parseCandidateHandles(rawText) {
  if (!rawText) return { clean: [], dups: 0 };
  const tokens = rawText.split(/[\r\n,;\s]+/).map((l) => l.trim()).filter(Boolean);
  const seen = new Set();
  const clean = [];
  let dups = 0;

  for (const raw of tokens) {
    let cand = raw.replace(/^@+/, '').trim();
    if (!cand || HEADER_TOKENS.has(cand.toLowerCase())) continue;
    if (cand.toLowerCase().includes('instagram.com/')) {
      cand = cand.replace(/\/+$/, '').split('/').pop().split('?')[0];
    }
    cand = cand.replace(/^@+/, '').trim();
    if (!cand) continue;
    const lowerCand = cand.toLowerCase();
    if (seen.has(lowerCand)) {
      dups += 1;
    } else if (clean.length < 50) {
      seen.add(lowerCand);
      clean.push(cand);
    }
  }
  return { clean, dups };
}

export default function CandidateUploadPage({ campaign, onBack, onBackToForm, onAnalysisComplete }) {
  const [inputMode, setInputMode] = useState('file'); // 'file' | 'manual'
  const [file, setFile] = useState(null);
  const [previewIds, setPreviewIds] = useState([]);
  const [dupCount, setDupCount] = useState(0);
  const [manualText, setManualText] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(18);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  const currentTip = useMemo(() => {
    const matched = LOADING_STEPS.filter((s) => elapsedSec >= s.afterSec);
    return matched[matched.length - 1] || LOADING_STEPS[0];
  }, [elapsedSec]);

  const { clean: manualIds, dups: manualDupCount } = useMemo(
    () => parseCandidateHandles(manualText),
    [manualText]
  );

  const activeIds = inputMode === 'file' ? previewIds : manualIds;
  const canStartAnalysis = inputMode === 'file' ? Boolean(file && previewIds.length > 0) : manualIds.length > 0;

  // 비동기 분석 프로그레스 및 경과 시간 타이머(1초 단위)
  useEffect(() => {
    if (!analyzing) {
      setElapsedSec(0);
      return;
    }
    setProgress(22);
    setElapsedSec(0);
    const t1 = setTimeout(() => setProgress(54), 1200);
    const t2 = setTimeout(() => setProgress(78), 3200);
    const t3 = setTimeout(() => setProgress(91), 6500);
    const timer = setInterval(() => {
      setElapsedSec((prev) => prev + 1);
    }, 1000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearInterval(timer);
    };
  }, [analyzing]);

  const handleFileSelect = async (selected) => {
    if (!selected) return;
    setErrorMsg('');
    setFile(selected);
    const text = await selected.text();
    const { clean, dups } = parseCandidateHandles(text);
    setPreviewIds(clean);
    setDupCount(dups);
  };

  const handleRemoveManualId = (targetId) => {
    const remaining = manualIds.filter((id) => id !== targetId);
    setManualText(remaining.join('\n'));
  };

  const handleFillSampleManual = () => {
    setErrorMsg('');
    setManualText('mew_demure\nchai._.beauty');
  };

  const handleDownloadSample = () => {
    const sample = 'instagram_id\nmew_demure\nchai._.beauty\ninminsrm\nclairedailymakeup\nonzlove99\n';
    const blob = new Blob([sample], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample_candidates.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleStartAnalysis = async () => {
    if (!canStartAnalysis) return;
    setErrorMsg('');
    setAnalyzing(true);
    try {
      let uploadTarget = file;
      if (inputMode === 'manual') {
        const csvContent = 'instagram_id\n' + manualIds.join('\n') + '\n';
        uploadTarget = new File([csvContent], 'manual_candidates.csv', { type: 'text/csv' });
      }
      const res = await campaignsApi.upload(campaign.id, uploadTarget);
      setProgress(100);
      setTimeout(() => {
        onAnalysisComplete(res);
      }, 350);
    } catch (err) {
      setAnalyzing(false);
      const detail =
        err.response?.data?.detail ||
        (err.message === 'Network Error'
          ? '백엔드 서버와 통신할 수 없습니다. 서버 연결 상태를 확인해 주세요.'
          : '후보 업로드 분석 중 오류가 발생했습니다.');
      setErrorMsg(detail);
    }
  };

  // [화면 1] 분석 진행 중 화면 (진행률 바 및 단계별 상태)
  if (analyzing) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-brand-navy">후보를 꼼꼼하게 분석하고 있어요</h1>
            <p className="text-sm text-slate-500 mt-1">
              {campaign.title} / 인스타그램 후보 {activeIds.length}명
            </p>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/80 p-7">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-bold text-brand-navy">전체 분석 진행률</span>
            <span className="text-xs text-slate-400">후보 프로필 및 콘텐츠 정밀 분석 중...</span>
          </div>
          <div className="flex items-baseline gap-3 mb-3">
            <span className="text-3xl font-extrabold text-brand-navy">{progress}%</span>
            <span className="text-xs text-slate-500">
              {activeIds.length}명의 프로필과 최근 게시물을 분석하고 있습니다
            </span>
          </div>
          <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-sky rounded-full transition-all duration-700"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* 경과 시간에 따라 동적으로 변하는 로딩 안내 배너 (3초 -> +5초 간격 전환) */}
          <div
            key={currentTip.afterSec}
            className="mt-5 p-4 rounded-xl bg-sky-50/70 border border-sky-100 flex items-start gap-3 transition-all duration-300"
          >
            <span className="text-xl leading-none mt-0.5">{currentTip.emoji}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-brand-navy">{currentTip.title}</span>
                <span className="text-[11px] font-medium text-sky-600/80 tabular-nums">
                  {elapsedSec}초 경과
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">{currentTip.desc}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/80 p-7 space-y-5">
          <h2 className="text-sm font-bold text-brand-navy">분석 단계</h2>
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-3.5">
              <span className="w-7 h-7 rounded-full bg-emerald-50 text-brand-mint text-xs font-bold flex items-center justify-center">
                01
              </span>
              <div>
                <div className="text-sm font-bold text-brand-navy">1단계 · 기본 적합성 확인</div>
                <div className="text-xs text-slate-500">비공개·광고성 봇 계정 등 부적합 후보 즉시 제외</div>
              </div>
            </div>
            <span className="text-xs font-semibold text-brand-mint">
              {progress >= 50 ? `${activeIds.length}명 · 완료` : '진행 중'}
            </span>
          </div>

          <div className="flex items-center justify-between py-2 border-t border-slate-100">
            <div className="flex items-center gap-3.5">
              <span className="w-7 h-7 rounded-full bg-sky-50 text-brand-sky text-xs font-bold flex items-center justify-center">
                02
              </span>
              <div>
                <div className="text-sm font-bold text-brand-navy">2단계 · 최근 피드 콘텐츠 수집</div>
                <div className="text-xs text-slate-500">최근 이미지·릴스 게시물의 분위기와 구성을 확인합니다</div>
              </div>
            </div>
            <span className="text-xs font-semibold text-brand-sky">
              {progress >= 75 ? '완료' : progress >= 50 ? '수집 중' : '대기'}
            </span>
          </div>

          <div className="flex items-center justify-between py-2 border-t border-slate-100">
            <div className="flex items-center gap-3.5">
              <span className="w-7 h-7 rounded-full bg-brand-sky text-white text-xs font-bold flex items-center justify-center">
                03
              </span>
              <div>
                <div className="text-sm font-bold text-brand-navy">3단계 · 브랜드 매칭 및 원고료 산정</div>
                <div className="text-xs text-slate-500">브랜드 적합도와 예상 적정 원고료를 계산합니다</div>
              </div>
            </div>
            <span className="text-xs font-semibold text-brand-sky">분석 중</span>
          </div>
        </div>
      </div>
    );
  }

  // [화면 2] 후보 목록 등록 화면 (파일 업로드 또는 직접 수기 입력)
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">후보 업로드</h1>
          <p className="text-sm text-slate-500 mt-1">
            분석할 인플루언서 목록을 등록해 주세요. 최대 50명까지 한 번에 분석합니다.
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
        <span className="flex items-center gap-1.5 text-brand-navy">
          <Check className="w-4 h-4 text-brand-mint" /> 캠페인 정보
        </span>
        <span className="text-slate-300">→</span>
        <span className="text-brand-sky font-bold">02 후보 업로드</span>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 flex items-center gap-2 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Tabs + Dropzone / Manual Input (8 cols) */}
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-7 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <h2 className="text-base font-bold text-brand-navy">후보 목록 등록</h2>

            {/* 2-Tab Switcher */}
            <div className="inline-flex p-1 rounded-xl bg-slate-100 border border-slate-200/70 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => {
                  setInputMode('file');
                  setErrorMsg('');
                }}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 whitespace-nowrap transition ${
                  inputMode === 'file'
                    ? 'bg-white text-brand-navy shadow-sm'
                    : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                <Upload className="w-3.5 h-3.5" /> 파일 업로드
              </button>
              <button
                type="button"
                onClick={() => {
                  setInputMode('manual');
                  setErrorMsg('');
                }}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 whitespace-nowrap transition ${
                  inputMode === 'manual'
                    ? 'bg-white text-brand-navy shadow-sm'
                    : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                <Edit3 className="w-3.5 h-3.5" /> 직접 입력 (수기)
              </button>
            </div>
          </div>

          {inputMode === 'file' ? (
            <>
              <label
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
                }}
                className="flex flex-col items-center justify-center border-2 border-dashed border-slate-200 hover:border-brand-sky rounded-2xl py-10 px-6 cursor-pointer bg-slate-50/40 transition"
              >
                <Upload className="w-7 h-7 text-slate-400 mb-3" />
                <div className="text-sm font-bold text-brand-navy">CSV 또는 TXT 파일을 여기에 놓아주세요</div>
                <div className="text-xs text-slate-400 mt-1 mb-4">
                  인스타그램 프로필 URL 또는 사용자명 · 최대 50명
                </div>
                <span className="px-5 py-2 rounded-xl bg-brand-sky text-white text-xs font-semibold whitespace-nowrap">
                  파일 선택
                </span>
                <input
                  type="file"
                  accept=".csv,.txt"
                  className="hidden"
                  onChange={(e) => handleFileSelect(e.target.files?.[0])}
                />
              </label>

              {file && (
                <>
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <FileText className="w-5 h-5 text-brand-sky" />
                      <div>
                        <div className="text-sm font-bold text-brand-navy">{file.name}</div>
                        <div className="text-xs text-slate-400">
                          후보 {previewIds.length}명 · {(file.size / 1024).toFixed(1)} KB
                        </div>
                      </div>
                    </div>
                    <span className="text-xs font-semibold text-brand-mint flex items-center gap-1 whitespace-nowrap">
                      업로드 완료 <Check className="w-3.5 h-3.5" />
                    </span>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-brand-navy">미리보기</span>
                      <span className="text-xs text-slate-400">
                        총 {previewIds.length + dupCount}명 · 유효 {previewIds.length}명 · 중복 {dupCount}명
                      </span>
                    </div>
                    <div className="border border-slate-200 rounded-xl overflow-hidden divide-y divide-slate-100">
                      {previewIds.slice(0, 5).map((id) => (
                        <div key={id} className="px-4 py-2.5 flex items-center justify-between text-xs">
                          <span className="font-bold text-brand-navy w-44 truncate">@{id}</span>
                          <span className="text-slate-400 flex-1 truncate">instagram.com/{id}</span>
                          <span className="text-brand-mint font-semibold whitespace-nowrap">유효</span>
                        </div>
                      ))}
                      {previewIds.length > 5 && (
                        <div className="px-4 py-2 text-xs text-slate-400 bg-slate-50">
                          외 {previewIds.length - 5}명
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-bold text-brand-navy">
                    인스타그램 아이디 또는 프로필 URL 입력
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleFillSampleManual}
                      className="text-xs font-semibold text-brand-sky hover:text-sky-600 flex items-center gap-1 whitespace-nowrap"
                    >
                      <Sparkles className="w-3.5 h-3.5" /> 추천 후보 2명 채우기
                    </button>
                    {manualText && (
                      <button
                        type="button"
                        onClick={() => setManualText('')}
                        className="text-xs font-semibold text-slate-400 hover:text-slate-600 whitespace-nowrap"
                      >
                        초기화
                      </button>
                    )}
                  </div>
                </div>

                <textarea
                  rows={5}
                  value={manualText}
                  onChange={(e) => {
                    setManualText(e.target.value);
                    setErrorMsg('');
                  }}
                  placeholder={'예시:\n@mew_demure\nchai._.beauty, inminsrm\nhttps://instagram.com/clairedailymakeup'}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/40 px-4 py-3 text-sm text-brand-navy placeholder:text-slate-400 focus:bg-white focus:border-brand-sky focus:outline-none focus:ring-2 focus:ring-brand-sky/15 transition"
                />
                <p className="text-[11px] text-slate-400 mt-1.5">
                  💡 줄바꿈, 쉼표(,), 띄어쓰기로 여러 명을 구분할 수 있으며, @ 기호나 프로필 링크도 자동으로 정리됩니다.
                </p>
              </div>

              {/* 실시간 태그 칩 프리뷰 */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-brand-navy">
                    등록된 후보 ({manualIds.length}명 / 최대 50명)
                  </span>
                  {manualDupCount > 0 && (
                    <span className="text-slate-400">중복 {manualDupCount}건 자동 제외됨</span>
                  )}
                </div>

                {manualIds.length === 0 ? (
                  <div className="text-xs text-slate-400 py-2">
                    위 입력창에 인스타그램 아이디를 입력하면 분석 대상이 여기에 표시됩니다.
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {manualIds.map((id) => (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-slate-200 text-xs font-semibold text-brand-navy shadow-sm"
                      >
                        <span>@{id}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveManualId(id)}
                          className="text-slate-400 hover:text-red-500 transition"
                          title="제거"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="pt-2 flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={onBackToForm}
              className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 flex items-center gap-1.5 whitespace-nowrap"
            >
              <ArrowLeft className="w-4 h-4" /> 캠페인 정보
            </button>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={onBack}
                className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-500 hover:text-brand-navy transition whitespace-nowrap"
                title="후보 등록 없이 캠페인만 저장하고 대시보드로 이동합니다"
              >
                나중에 등록 (건너뛰기)
              </button>
              <button
                type="button"
                disabled={!canStartAnalysis}
                onClick={handleStartAnalysis}
                className="px-6 py-2.5 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-sm font-semibold flex items-center gap-2 transition disabled:opacity-40 whitespace-nowrap"
              >
                후보 {activeIds.length || ''}명 분석 시작 <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Right: Checklist & Sample CSV (4 cols) */}
        <div className="lg:col-span-4 space-y-5">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <h3 className="text-sm font-bold text-brand-navy mb-3">
              {inputMode === 'file' ? '업로드 체크리스트' : '직접 입력 가이드'}
            </h3>
            {inputMode === 'file' ? (
              <>
                <ul className="space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> CSV 또는 TXT 형식
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 한 줄에 한 명의 사용자명 또는 URL
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 최대 50명, 중복 계정 자동 제외
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 공개 계정만 콘텐츠 정밀 분석 가능
                  </li>
                </ul>

                <div className="mt-5 pt-4 border-t border-slate-100">
                  <div className="text-xs text-slate-400 mb-2">양식이 필요하신가요?</div>
                  <button
                    type="button"
                    onClick={handleDownloadSample}
                    className="text-xs font-bold text-brand-navy hover:text-brand-sky flex items-center gap-1.5"
                  >
                    샘플 CSV 다운로드 <Download className="w-3.5 h-3.5" />
                  </button>
                </div>
              </>
            ) : (
              <ul className="space-y-2 text-xs text-slate-600">
                <li className="flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 파일 없이 1~2명도 바로 분석 가능
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 줄바꿈, 쉼표(,), 공백 모두 자동 인식
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> @아이디·프로필 URL 자동 추출
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 text-brand-mint shrink-0" /> 최대 50명, 중복 입력 자동 제외
                </li>
              </ul>
            )}
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <div className="text-sm font-bold text-brand-navy mb-2">분석 시작 전 확인해 주세요</div>
            <p className="text-xs text-slate-500 leading-relaxed">
              부적합한 계정은 1차로 걸러내고, 적합한 후보만 집중 분석해 효율을 높입니다. 분석된 결과는 캠페인 대시보드에서 언제든 다시 확인할 수 있습니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
