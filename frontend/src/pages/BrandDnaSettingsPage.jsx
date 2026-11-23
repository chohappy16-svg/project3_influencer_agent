import React, { useState, useEffect } from 'react';
import { Check, Sparkles, RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import { authApi } from '../api/client';

export default function BrandDnaSettingsPage({ user, onUpdateLocalDna, onBack }) {
  const [companyName, setCompanyName] = useState(user?.company_name || '');
  const [brandUrl, setBrandUrl] = useState(user?.brand_url || '');
  const [dnaText, setDnaText] = useState(user?.brand_dna_summary || '');
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [notice, setNotice] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (user) {
      if (user.company_name) setCompanyName(user.company_name);
      if (user.brand_url) setBrandUrl(user.brand_url);
      if (user.brand_dna_summary) setDnaText(user.brand_dna_summary);
    }
  }, [user]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setNotice('');
    setErrorMsg('');
    try {
      const res = await authApi.updateBrandDna({
        company_name: companyName,
        brand_url: brandUrl,
        full_dna_text: dnaText,
        re_extract: false,
      });
      setDnaText(res.brand_dna_summary);
      if (onUpdateLocalDna) {
        onUpdateLocalDna({
          company_name: res.company_name,
          brand_url: res.brand_url,
          brand_dna_summary: res.brand_dna_summary,
        });
      }
      setNotice(res.message);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || '브랜드 DNA 저장 중 오류가 발생했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const handleReExtract = async () => {
    if (!brandUrl.trim()) {
      setErrorMsg('자사몰 URL을 입력해 주세요.');
      return;
    }
    setExtracting(true);
    setNotice('');
    setErrorMsg('');
    try {
      const res = await authApi.updateBrandDna({
        company_name: companyName,
        brand_url: brandUrl,
        re_extract: true,
      });
      setDnaText(res.brand_dna_summary);
      if (onUpdateLocalDna) {
        onUpdateLocalDna({
          company_name: res.company_name,
          brand_url: res.brand_url,
          brand_dna_summary: res.brand_dna_summary,
        });
      }
      setNotice(res.message);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'URL 재추출 중 오류가 발생했습니다.');
    } finally {
      setExtracting(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">브랜드 DNA 설정</h1>
        <p className="text-sm text-slate-500 mt-1">
          브랜드의 기준을 확인하고 수정하세요. 저장된 기준은 앞으로 진행할 모든 캠페인 분석에 일관되게 적용됩니다.
        </p>
      </div>

      {notice && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Check className="w-4 h-4 text-brand-mint" />
            {notice}
          </span>
          <button onClick={() => setNotice('')} className="text-emerald-600 font-bold ml-4">
            닫기
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs font-semibold text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Settings Form (8) */}
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-7 space-y-6">
          <div>
            <h2 className="text-base font-bold text-brand-navy mb-4">브랜드 정보</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">브랜드명</label>
                <input
                  type="text"
                  required
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">브랜드 자사몰 URL</label>
                <div className="flex gap-2.5">
                  <input
                    type="url"
                    required
                    value={brandUrl}
                    onChange={(e) => setBrandUrl(e.target.value)}
                    className="flex-1 px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky"
                  />
                  <button
                    type="button"
                    disabled={extracting || saving}
                    onClick={handleReExtract}
                    className="px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-bold text-brand-navy flex items-center gap-1.5 shrink-0 transition disabled:opacity-60"
                  >
                    {extracting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-sky" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5 text-brand-sky" />
                    )}
                    {extracting ? '추출 중...' : '다시 추출'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-base font-bold text-brand-navy">브랜드 DNA</h2>
              <span className="text-xs font-semibold text-brand-sky flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5" /> 브랜드 특징 직접 수정
              </span>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              저장된 브랜드 페르소나 설명을 직접 수정할 수 있습니다. (텍스트만 저장 시 추가 LLM 비용 없음)
            </p>
            <textarea
              rows={4}
              required
              value={dnaText}
              onChange={(e) => setDnaText(e.target.value)}
              className="w-full px-3.5 py-3 text-sm rounded-xl border border-slate-200 focus:outline-none focus:border-brand-sky leading-relaxed"
            />
          </div>

          <div className="pt-2 flex items-center justify-between">
            <button
              type="button"
              onClick={onBack}
              className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50"
            >
              대시보드로
            </button>
            <button
              type="submit"
              disabled={saving || extracting}
              className="px-6 py-2.5 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-sm font-semibold flex items-center gap-2 transition disabled:opacity-60"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              변경 사항 저장
            </button>
          </div>
        </div>

        {/* Right: Info (4) */}
        <div className="lg:col-span-4 space-y-5">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6">
            <h3 className="text-sm font-bold text-brand-navy mb-2">AI 분석의 기본 기준</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              브랜드 DNA는 PostgreSQL 계정에 영구 저장되어 모든 캠페인 분석의 기본 기준이 됩니다.
            </p>
            <ul className="space-y-1.5 text-xs text-slate-600">
              <li>• 변경 사항은 저장 후 새 분석에 즉시 적용됩니다.</li>
              <li>• 기존 분석 결과는 그대로 유지됩니다.</li>
              <li>• 캠페인 가이드라인은 추가 조건입니다.</li>
            </ul>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 space-y-3 text-xs">
            <h3 className="text-sm font-bold text-brand-navy">저장 정보</h3>
            <div className="flex justify-between text-slate-500">
              <span>저장소</span>
              <span className="font-bold text-brand-mint">PostgreSQL 연동됨</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>계정</span>
              <span className="font-bold text-brand-navy">{user?.email}</span>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
