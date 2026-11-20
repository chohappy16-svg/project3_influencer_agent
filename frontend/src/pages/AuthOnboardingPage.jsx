import React, { useState, useEffect } from 'react';
import { Check, Sparkles, ArrowRight, Globe, AlertCircle, Loader2 } from 'lucide-react';
import { BrandLogo } from '../components/BrandLogo';
import { authApi } from '../api/client';

export default function AuthOnboardingPage({ onAuthSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [step, setStep] = useState('form'); // 'form' | 'extracting' | 'dna_confirm'

  // Form states (기본값 비움 + 플레이스홀더 가이드 노출)
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [brandUrl, setBrandUrl] = useState('');
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [keepLoggedIn, setKeepLoggedIn] = useState(true);

  // 실시간 유효성 검증
  const isEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\/~`']/.test(password);
  const isPasswordValid = password.length >= 8 && password.length <= 32 && hasSpecialChar;
  const isSignupFormValid =
    isEmailValid &&
    isPasswordValid &&
    companyName.trim().length > 0 &&
    brandUrl.trim().length > 0 &&
    agreeTerms;

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [progress, setProgress] = useState(25);
  const [signupResult, setSignupResult] = useState(null);

  // P.4 추출 프로그레스 애니메이션
  useEffect(() => {
    if (step !== 'extracting') return;
    setProgress(28);
    const t1 = setTimeout(() => setProgress(68), 500);
    const t2 = setTimeout(() => setProgress(88), 1400);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [step]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setLoading(true);
    try {
      const data = await authApi.login({ email, password });
      localStorage.setItem('influenceops_token', data.access_token);
      onAuthSuccess({
        user_id: data.user_id,
        email,
        company_name: data.company_name || '내 워크스페이스',
        brand_dna_summary: data.brand_dna_summary || '',
      });
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail[0]?.msg || '입력 정보를 확인해 주세요.'
        : typeof detail === 'string'
        ? detail
        : '로그인에 실패했습니다. 이메일과 비밀번호를 확인해 주세요.';
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    if (!isSignupFormValid) {
      return;
    }
    setStep('extracting');
    setLoading(true);
    try {
      const signupRes = await authApi.signup({
        email,
        password,
        company_name: companyName,
        brand_url: brandUrl,
      });
      // 바로 로그인하여 JWT 토큰 확보
      const loginRes = await authApi.login({ email, password });
      localStorage.setItem('influenceops_token', loginRes.access_token);

      setProgress(100);
      setSignupResult({
        signupRes,
        userInfo: {
          user_id: loginRes.user_id,
          email,
          company_name: loginRes.company_name || companyName,
          brand_url: brandUrl,
          brand_dna_summary: signupRes.brand_dna,
        },
      });
      setTimeout(() => setStep('dna_confirm'), 450);
    } catch (err) {
      setStep('form');
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail[0]?.msg || '입력 형식이 올바르지 않습니다. (비밀번호 4자 이상, 이메일 형식 확인)'
        : typeof detail === 'string'
        ? detail
        : '회원가입 중 오류가 발생했습니다.';
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDnaAndStart = () => {
    if (signupResult?.userInfo) {
      onAuthSuccess(signupResult.userInfo);
    }
  };

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col justify-between">
      {/* Top Header */}
      <header className="w-full px-8 py-5 flex items-center justify-between">
        <BrandLogo />
        <span className="text-xs text-slate-400 font-medium">
          {step === 'form' ? '브랜드와 크리에이터, 더 정확한 연결' : '브랜드 설정 / 02'}
        </span>
      </header>

      {/* Main Container */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-6">
        {/* Stepper for P.4 / P.5 */}
        {step !== 'form' && (
          <div className="flex items-center gap-4 text-xs font-medium text-slate-500 mb-8">
            <span className="flex items-center gap-1.5 text-brand-navy font-semibold">
              <Check className="w-3.5 h-3.5 text-brand-mint" /> 계정 생성
            </span>
            <span className="w-12 h-px bg-slate-300" />
            <span className="text-brand-navy font-bold">02 브랜드 DNA</span>
            <span className="w-12 h-px bg-slate-300" />
            <span className="text-slate-400">03 캠페인 시작</span>
          </div>
        )}

        {/* P.2 & P.3: Login / Signup Card */}
        {step === 'form' && (
          <div className="w-full max-w-[440px] bg-white rounded-2xl border border-slate-200/80 shadow-sm p-8">
            <div className="mb-6">
              <h1 className="text-2xl font-bold text-brand-navy">
                {mode === 'login' ? '다시 만나 반가워요' : '브랜드의 첫 기준을 만들어보세요'}
              </h1>
              <p className="text-sm text-slate-500 mt-1.5">
                {mode === 'login'
                  ? '캠페인과 크리에이터 분석을 이어가세요.'
                  : '계정을 만들고 브랜드 자사몰을 연결하세요.'}
              </p>
            </div>

            {/* Segmented Tabs */}
            <div className="grid grid-cols-2 bg-slate-100 p-1 rounded-xl mb-6">
              <button
                type="button"
                onClick={() => {
                  setMode('login');
                  setErrorMsg('');
                }}
                className={`py-2 text-sm font-semibold rounded-lg transition ${
                  mode === 'login' ? 'bg-white text-brand-navy shadow-sm' : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                로그인
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode('signup');
                  setErrorMsg('');
                }}
                className={`py-2 text-sm font-semibold rounded-lg transition ${
                  mode === 'signup' ? 'bg-white text-brand-navy shadow-sm' : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                회원가입
              </button>
            </div>

            {errorMsg && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2 text-xs text-red-700">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{errorMsg}</span>
              </div>
            )}

            {mode === 'login' ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">이메일</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@brand.com"
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-sky/30 focus:border-brand-sky"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">비밀번호</label>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-sky/30 focus:border-brand-sky"
                  />
                </div>

                <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={keepLoggedIn}
                      onChange={(e) => setKeepLoggedIn(e.target.checked)}
                      className="rounded border-slate-300 text-brand-navy focus:ring-brand-sky"
                    />
                    로그인 유지
                  </label>
                  <span className="text-slate-400">비밀번호 찾기</span>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3 rounded-xl bg-brand-sky hover:bg-sky-600 text-white font-semibold text-sm transition flex items-center justify-center gap-2 disabled:opacity-60"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  로그인
                </button>

                <div className="pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
                  처음이신가요?{' '}
                  <button
                    type="button"
                    onClick={() => setMode('signup')}
                    className="font-semibold text-brand-navy hover:text-brand-sky ml-1"
                  >
                    회원가입하고 브랜드 연결하기 →
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleSignup} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">이메일</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@brand.com"
                    className={`w-full px-3.5 py-2.5 text-sm rounded-xl border focus:outline-none focus:ring-2 transition placeholder:text-slate-400 ${
                      email.length > 0 && !isEmailValid
                        ? 'border-red-400 focus:ring-red-200 focus:border-red-500'
                        : 'border-slate-200 focus:ring-brand-sky/30 focus:border-brand-sky'
                    }`}
                  />
                  {email.length > 0 && !isEmailValid && (
                    <p className="mt-1.5 text-[11px] font-medium text-red-500 flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      올바른 이메일 형식을 입력해 주세요. (예: name@brand.com)
                    </p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">비밀번호</label>
                  <input
                    type="password"
                    required
                    minLength={8}
                    maxLength={32}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="8~32자, 특수문자(!@# 등) 1개 이상 포함"
                    className={`w-full px-3.5 py-2.5 text-sm rounded-xl border focus:outline-none focus:ring-2 transition placeholder:text-slate-400 ${
                      password.length > 0 && !isPasswordValid
                        ? 'border-red-400 focus:ring-red-200 focus:border-red-500'
                        : 'border-slate-200 focus:ring-brand-sky/30 focus:border-brand-sky'
                    }`}
                  />
                  {password.length > 0 && !isPasswordValid && (
                    <p className="mt-1.5 text-[11px] font-medium text-red-500 flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      8~32자 이내, 특수문자(!@# 등)를 최소 1개 이상 포함해 주세요.
                    </p>
                  )}
                  {password.length > 0 && isPasswordValid && (
                    <p className="mt-1.5 text-[11px] font-medium text-emerald-600 flex items-center gap-1">
                      <Check className="w-3.5 h-3.5 shrink-0" />
                      사용 가능한 안전한 비밀번호입니다.
                    </p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">브랜드명 (회사명)</label>
                  <input
                    type="text"
                    required
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="예: 글로우랩"
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-sky/30 focus:border-brand-sky placeholder:text-slate-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">브랜드 자사몰 URL</label>
                  <input
                    type="url"
                    required
                    value={brandUrl}
                    onChange={(e) => setBrandUrl(e.target.value)}
                    placeholder="https://brand.com"
                    className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-sky/30 focus:border-brand-sky placeholder:text-slate-400"
                  />
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/70">
                  <div className="text-xs font-bold text-brand-navy mb-1">브랜드 URL 하나로 시작하는 맞춤 분석</div>
                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    자사몰에서 브랜드 특성을 추출합니다. 확인한 DNA는 이후 AI 분석의 기본 기준으로 사용됩니다.
                  </p>
                </div>

                <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={agreeTerms}
                    onChange={(e) => setAgreeTerms(e.target.checked)}
                    className="rounded border-slate-300 text-brand-navy"
                  />
                  이용약관 및 개인정보 처리방침에 동의합니다.
                </label>

                <button
                  type="submit"
                  disabled={loading || !isSignupFormValid}
                  className={`w-full py-3 rounded-xl font-semibold text-sm transition flex items-center justify-center gap-2 ${
                    loading || !isSignupFormValid
                      ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-brand-sky hover:bg-sky-600 text-white shadow-sm'
                  }`}
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  가입 완료
                </button>

                <div className="text-center text-[11px] text-slate-400 pt-2">
                  01 계정 생성 — 02 DNA 확인 — 03 캠페인 시작
                </div>
              </form>
            )}
          </div>
        )}

        {/* P.4: Brand DNA Extracting Progress */}
        {step === 'extracting' && (
          <div className="w-full max-w-[600px] bg-white rounded-2xl border border-slate-200/80 shadow-sm p-9">
            <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-2">
              BRAND INTELLIGENCE
            </div>
            <h2 className="text-2xl font-bold text-brand-navy">우리 브랜드를 알아가고 있어요</h2>
            <p className="text-sm text-slate-500 mt-1.5">
              자사몰의 브랜드 소개와 제품 정보를 바탕으로 분석 기준을 추출합니다.
            </p>

            <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-200/70 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400 font-medium">연결된 자사몰</div>
                <div className="text-sm font-bold text-brand-navy mt-0.5 flex items-center gap-1.5">
                  <Globe className="w-4 h-4 text-brand-sky" />
                  {brandUrl}
                </div>
              </div>
              <span className="text-xs font-semibold text-brand-sky animate-pulse">수집 중</span>
            </div>

            <div className="mt-7">
              <div className="flex items-center justify-between text-sm font-bold text-brand-navy mb-2">
                <span>브랜드 특성 추출 중</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-sky rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            <div className="mt-7 space-y-5">
              <div className="flex items-start gap-3.5">
                <div className="w-7 h-7 rounded-full bg-emerald-50 text-brand-mint flex items-center justify-center shrink-0">
                  <Check className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-sm font-bold text-brand-navy">브랜드 소개 수집</div>
                  <div className="text-xs text-slate-500 mt-0.5">브랜드 철학과 핵심 메시지를 확인했어요.</div>
                </div>
              </div>
              <div className="flex items-start gap-3.5">
                <div className="w-7 h-7 rounded-full bg-sky-50 text-brand-sky text-xs font-bold flex items-center justify-center shrink-0">
                  02
                </div>
                <div>
                  <div className="text-sm font-bold text-brand-navy">제품·비주얼 특성 분석</div>
                  <div className="text-xs text-slate-500 mt-0.5">성분, 촬영 분위기, 콘텐츠 톤을 분석하고 있어요.</div>
                </div>
              </div>
              <div className="flex items-start gap-3.5 opacity-60">
                <div className="w-7 h-7 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center shrink-0">
                  03
                </div>
                <div>
                  <div className="text-sm font-bold text-brand-navy">브랜드 DNA 정리</div>
                  <div className="text-xs text-slate-500 mt-0.5">분석 결과를 확인할 수 있도록 정리합니다.</div>
                </div>
              </div>
            </div>

            <div className="mt-8 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
              <span>페이지를 닫지 말고 잠시만 기다려 주세요.</span>
              <span>Gemini 2.5 Flash 실시간 분석</span>
            </div>
          </div>
        )}

        {/* P.5: Brand DNA Confirm */}
        {step === 'dna_confirm' && signupResult && (
          <div className="w-full max-w-[620px] bg-white rounded-2xl border border-slate-200/80 shadow-sm p-9">
            <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-2">
              BRAND INTELLIGENCE
            </div>
            <h2 className="text-2xl font-bold text-brand-navy">우리 브랜드의 DNA를 확인해 주세요</h2>
            <p className="text-sm text-slate-500 mt-1.5">
              추출된 특성을 확인하고 저장하면 모든 AI 분석에 기본으로 적용됩니다.
            </p>

            <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-200/70 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400 font-medium">연결된 자사몰</div>
                <div className="text-sm font-bold text-brand-navy mt-0.5">{brandUrl}</div>
              </div>
              <span className="text-xs font-semibold text-brand-mint flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> 수집 완료
              </span>
            </div>

            <div className="mt-5 space-y-3">
              <div className="p-4 rounded-xl border border-slate-200 bg-white">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>추출된 브랜드 페르소나 DNA</span>
                  <span className="text-brand-sky font-semibold flex items-center gap-1">
                    <Sparkles className="w-3 h-3" /> AI 요약
                  </span>
                </div>
                <p className="text-sm font-medium text-brand-navy leading-relaxed mt-1">
                  {signupResult.signupRes.brand_dna}
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/50">
                  <div className="text-[11px] text-slate-400">비주얼 무드</div>
                  <div className="text-xs font-bold text-brand-navy mt-1">자연광 · 여백의 미</div>
                </div>
                <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/50">
                  <div className="text-[11px] text-slate-400">제품 가치</div>
                  <div className="text-xs font-bold text-brand-navy mt-1">순한 성분 · 클린 뷰티</div>
                </div>
                <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/50">
                  <div className="text-[11px] text-slate-400">커뮤니케이션 톤</div>
                  <div className="text-xs font-bold text-brand-navy mt-1">솔직한 일상 후기</div>
                </div>
              </div>
            </div>

            <div className="mt-8 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setStep('form')}
                className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                URL 다시 연결
              </button>
              <button
                type="button"
                onClick={handleConfirmDnaAndStart}
                className="px-6 py-2.5 rounded-xl bg-brand-sky hover:bg-sky-600 text-white text-sm font-semibold flex items-center gap-2 transition"
              >
                DNA 저장하고 시작하기 <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="w-full px-8 py-5 flex items-center justify-between text-xs text-slate-400">
        <span>© 2026 InfluenceOps</span>
        <div className="flex items-center gap-4">
          <span>이용약관</span>
          <span>개인정보 처리방침</span>
          <span>문의하기</span>
        </div>
      </footer>
    </div>
  );
}
