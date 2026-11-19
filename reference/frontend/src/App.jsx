import React, { useState, useEffect } from 'react';

const API_BASE = window.location.origin.includes('8002') ? '' : 'http://127.0.0.1:8002';

const SAMPLE_PRESETS = [
  {
    label: '💻 IT과학 기사 + 부정 리뷰',
    news_text: '엔비디아 차세대 AI 슈퍼칩 블랙웰(Blackwell) 정식 출하 시작... 글로벌 클라우드 4사 역대 최대 규모 주문 쇄도.',
    review_text: '성능은 진짜 압도적인데 가격이 너무 비싸서 중소 스타트업들은 엄두도 못 내겠네요. 빅테크 독점만 더 심화될까 봐 걱정스럽습니다.',
    photo_id: 'PHOTO_NV_2026_01',
    memo: 'AI 반도체 출하 기사 분석',
  },
  {
    label: '💰 경제 기사 + 긍정 리뷰',
    news_text: '한국은행, 기준금리 0.25%p 전격 인하... 주택담보대출 이자 부담 줄어드나',
    review_text: '드디어 대출 이자 부담이 좀 줄어들겠네요! 자영업자들과 직장인들에게 정말 반가운 소식입니다.',
    photo_id: 'PHOTO_ECON_02',
    memo: '기준금리 인하 기사',
  },
  {
    label: '⚽ 스포츠 기사 단독 (리뷰 생략)',
    news_text: '손흥민, 멀티골 폭발하며 팀 역전승 견인... 현지 언론 평점 9점 최고 활약 극찬',
    review_text: '',
    photo_id: 'PHOTO_SON_07',
    memo: '뉴스 단독 입력 테스트',
  },
  {
    label: '🎬 독자 리뷰 단독 (뉴스 생략)',
    news_text: '',
    review_text: '이 영화는 올해 최고의 명작입니다! 배우들의 연기력과 연출이 정말 감동적이었어요.',
    photo_id: '',
    memo: '리뷰 단독 감성분석 테스트',
  },
  {
    label: '⚠️ 모호한 단문 (70% 미만 테스트)',
    news_text: '오늘 오후 관계자 긴급 회의 개최 및 향후 일정 논의',
    review_text: '무슨 내용인지 아직 잘 모르겠네요. 지켜봐야 할 듯합니다.',
    photo_id: '',
    memo: '신뢰도 70% 임계값 테스트',
  },
];

const CATEGORIES = ['전체', 'IT과학', '경제', '사회', '생활문화', '세계', '스포츠', '정치'];

export default function App() {
  const [activeMenu, setActiveMenu] = useState('analyze'); // 'analyze' | 'history'

  // 입력 폼 상태 (규칙 3: 뉴스 원문 칸 + 독자 리뷰 칸 2개 분리)
  const [newsText, setNewsText] = useState(SAMPLE_PRESETS[0].news_text);
  const [reviewText, setReviewText] = useState(SAMPLE_PRESETS[0].review_text);
  const [photoId, setPhotoId] = useState(SAMPLE_PRESETS[0].photo_id);
  const [memo, setMemo] = useState(SAMPLE_PRESETS[0].memo);
  const [useGptAgent, setUseGptAgent] = useState(false);

  // 분석 결과 & 로딩 상태
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [latestResult, setLatestResult] = useState(null);

  // MySQL 히스토리 & 통계 상태
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [filterCategory, setFilterCategory] = useState('전체');
  const [filterSentiment, setFilterSentiment] = useState('전체');
  const [filterConfidence, setFilterConfidence] = useState('all'); // 'all' | 'high' | 'hold'

  const fetchLogsAndStats = async () => {
    try {
      const params = new URLSearchParams();
      if (filterCategory && filterCategory !== '전체') params.set('category', filterCategory);
      if (filterSentiment && filterSentiment !== '전체') params.set('sentiment', filterSentiment);
      if (filterConfidence) params.set('confidence_mode', filterConfidence);

      const [logsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/logs?${params.toString()}`),
        fetch(`${API_BASE}/api/stats`),
      ]);
      if (logsRes.ok) {
        const logsData = await logsRes.json();
        setLogs(logsData);
        if (!latestResult && logsData.length > 0) {
          setLatestResult(logsData[0]);
        }
      }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error('데이터 조회 오류:', err);
    }
  };

  useEffect(() => {
    fetchLogsAndStats();
  }, [filterCategory, filterSentiment, filterConfidence]);

  const handlePresetClick = (preset) => {
    setNewsText(preset.news_text);
    setReviewText(preset.review_text);
    setPhotoId(preset.photo_id);
    setMemo(preset.memo);
    setErrorMsg('');
  };

  const handleAnalyzeSubmit = async (e) => {
    e.preventDefault();
    if (!newsText.trim() && !reviewText.trim()) {
      setErrorMsg('뉴스 기사 원문 또는 독자 리뷰/댓글 중 최소 한 칸은 입력해주세요.');
      return;
    }

    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          news_text: newsText,
          review_text: reviewText,
          photo_id: photoId,
          use_gpt_agent: useGptAgent,
          memo: memo,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || 'AI 분석 중 오류가 발생했습니다.');
      } else {
        setLatestResult(data.result);
        fetchLogsAndStats();
      }
    } catch (err) {
      setErrorMsg('백엔드 서버(127.0.0.1:8002)에 연결할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleEditMemo = async (log) => {
    const newMemo = window.prompt(`기록(#${log.id}) 메모 수정:`, log.memo || '');
    if (newMemo === null) return;
    await fetch(`${API_BASE}/api/logs/${log.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memo: newMemo }),
    });
    fetchLogsAndStats();
  };

  const handleConfirmCategory = async (log, newCategory) => {
    await fetch(`${API_BASE}/api/logs/${log.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        predicted_category: newCategory,
        is_high_confidence: 1,
        memo: `${log.memo ? log.memo + ' ' : ''}[수동확정: ${newCategory}]`,
      }),
    });
    fetchLogsAndStats();
  };

  const handleDeleteLog = async (id) => {
    if (!window.confirm(`분석 기록(#${id})을 MySQL DB에서 삭제하시겠습니까?`)) return;
    await fetch(`${API_BASE}/api/logs/${id}`, { method: 'DELETE' });
    fetchLogsAndStats();
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0f172a', color: '#f8fafc' }}>
      {/* ================= 좌측 고정 사이드바 ================= */}
      <aside
        style={{
          width: '265px',
          background: '#1e293b',
          borderRight: '1px solid rgba(148,163,184,0.2)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          height: '100vh',
        }}
      >
        <div
          style={{
            padding: '1.35rem 1.25rem',
            borderBottom: '1px solid rgba(148,163,184,0.2)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '9px',
              background: 'linear-gradient(135deg, #6366f1, #a855f7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.1rem',
            }}
          >
            🤖
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '0.96rem', color: '#fff' }}>뉴스 & 리뷰 AI 에이전트</div>
            <div style={{ fontSize: '0.72rem', color: '#818cf8', fontWeight: 700 }}>
              React + FastAPI + MySQL
            </div>
          </div>
        </div>

        {/* 연동된 AI 모델 안내 */}
        <div
          style={{
            padding: '0.95rem 1.2rem',
            background: 'rgba(15,23,42,0.45)',
            borderBottom: '1px solid rgba(148,163,184,0.2)',
            fontSize: '0.76rem',
            lineHeight: 1.55,
          }}
        >
          <div style={{ color: '#94a3b8', fontWeight: 700, marginBottom: '4px' }}>탑재된 로컬 AI 모델 (2종)</div>
          <div style={{ color: '#e2e8f0' }}>• 뉴스 7분류: <code>1021/best_news_model</code></div>
          <div style={{ color: '#e2e8f0' }}>• 감성 분석: <code>KoELECTRA-NSMC</code></div>
          <div style={{ color: '#6ee7b7', marginTop: '4px', fontWeight: 700 }}>
            • 임계값 규칙: 신뢰도 70% 기준
          </div>
        </div>

        {/* 사이드바 메뉴 네비게이션 */}
        <nav style={{ padding: '1rem 0.75rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94a3b8', padding: '0.4rem 0.75rem' }}>
            AI 에이전트 워크스페이스
          </div>
          <button
            onClick={() => setActiveMenu('analyze')}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.8rem 0.95rem',
              borderRadius: '10px',
              border: activeMenu === 'analyze' ? '1px solid #818cf8' : '1px solid transparent',
              background: activeMenu === 'analyze' ? '#6366f1' : 'transparent',
              color: activeMenu === 'analyze' ? '#fff' : '#94a3b8',
              fontWeight: 700,
              fontSize: '0.9rem',
              cursor: 'pointer',
            }}
          >
            <span>🧠 AI 뉴스·리뷰 분석</span>
            <span style={{ fontSize: '0.7rem', background: 'rgba(255,255,255,0.16)', padding: '2px 7px', borderRadius: '999px' }}>
              실행
            </span>
          </button>

          <button
            onClick={() => setActiveMenu('history')}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.8rem 0.95rem',
              borderRadius: '10px',
              border: activeMenu === 'history' ? '1px solid #818cf8' : '1px solid transparent',
              background: activeMenu === 'history' ? '#6366f1' : 'transparent',
              color: activeMenu === 'history' ? '#fff' : '#94a3b8',
              fontWeight: 700,
              fontSize: '0.9rem',
              cursor: 'pointer',
            }}
          >
            <span>🗄️ MySQL 저장 기록 관리</span>
            <span style={{ fontSize: '0.7rem', background: 'rgba(255,255,255,0.16)', padding: '2px 7px', borderRadius: '999px' }}>
              {stats ? stats.total_count : logs.length}건
            </span>
          </button>
        </nav>

        {/* 하단 PooledDB 커넥션 풀 상태 */}
        <div style={{ padding: '1rem 1.2rem', borderTop: '1px solid rgba(148,163,184,0.2)', fontSize: '0.76rem' }}>
          <div
            style={{
              padding: '0.65rem',
              borderRadius: '8px',
              background: 'rgba(16,185,129,0.12)',
              border: '1px solid rgba(16,185,129,0.3)',
            }}
          >
            <div style={{ color: '#6ee7b7', fontWeight: 800 }}>⚡ PooledDB 커넥션 풀 활성</div>
            <div style={{ color: '#cbd5e1', marginTop: '3px', fontSize: '0.72rem' }}>
              DB 엔진: <strong>{stats?.db_engine || 'mysql'}</strong>
            </div>
            {stats?.pool_status && (
              <div style={{ color: '#94a3b8', marginTop: '2px', fontSize: '0.7rem' }}>
                대기 {stats.pool_status.idle_cached}개 · 누적 재사용 {stats.pool_status.total_borrowed}회
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ================= 우측 메인 콘텐츠 영역 ================= */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* 상단 헤더 */}
        <header
          style={{
            background: 'rgba(30,41,59,0.88)',
            borderBottom: '1px solid rgba(148,163,184,0.2)',
            padding: '1rem 1.75rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800 }}>
              {activeMenu === 'analyze'
                ? '🧠 KoELECTRA 뉴스 7분류 & 감성 분석 AI 에이전트'
                : '🗄️ MySQL 분석 히스토리 및 분류보류(70% 미만) 관리'}
            </h2>
            <p style={{ fontSize: '0.82rem', color: '#94a3b8', marginTop: '2px' }}>
              1023 Gradio 감성분석 UI와 1026 뉴스/리뷰 AI 에이전트를 React + FastAPI + MySQL(PooledDB)로 통합한 프로젝트
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <a
              href="http://127.0.0.1:8002/docs"
              target="_blank"
              rel="noreferrer"
              style={{
                padding: '0.5rem 0.9rem',
                borderRadius: '8px',
                background: '#0f172a',
                border: '1px solid rgba(148,163,184,0.25)',
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.82rem',
                fontWeight: 700,
              }}
            >
              📘 FastAPI Swagger (/docs)
            </a>
            <button
              onClick={fetchLogsAndStats}
              style={{
                padding: '0.5rem 0.9rem',
                borderRadius: '8px',
                background: '#6366f1',
                border: 'none',
                color: '#fff',
                fontSize: '0.82rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              🔄 DB 새로고침
            </button>
          </div>
        </header>

        <main style={{ padding: '1.6rem', maxWidth: '1340px', width: '100%' }}>
          {/* 상단 요약 통계 카드 4개 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
              gap: '1rem',
              marginBottom: '1.25rem',
            }}
          >
            <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderTop: '3px solid #6366f1', borderRadius: '14px', padding: '1.15rem' }}>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600 }}>MySQL 누적 AI 분석 건수</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '0.25rem' }}>{stats ? stats.total_count : logs.length}건</div>
              <div style={{ fontSize: '0.74rem', color: '#818cf8', marginTop: '0.2rem' }}>분석 즉시 자동 INSERT 저장</div>
            </div>

            <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderTop: '3px solid #10b981', borderRadius: '14px', padding: '1.15rem' }}>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600 }}>신뢰도 70% 이상 (정상 분류)</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '0.25rem', color: '#6ee7b7' }}>
                {stats ? stats.high_confidence_count : 0}건
              </div>
              <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: '0.2rem' }}>상용 노출 기준 통과 기사</div>
            </div>

            <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderTop: '3px solid #f59e0b', borderRadius: '14px', padding: '1.15rem' }}>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600 }}>신뢰도 70% 미만 (분류보류/모호)</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '0.25rem', color: '#fcd34d' }}>
                {stats ? stats.hold_confidence_count : 0}건
              </div>
              <div style={{ fontSize: '0.74rem', color: '#fcd34d', marginTop: '0.2rem' }}>히스토리 탭에서 수동 확정 가능</div>
            </div>

            <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderTop: '3px solid #ec4899', borderRadius: '14px', padding: '1.15rem' }}>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600 }}>독자 리뷰 감성 비율 (긍정 / 부정)</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '0.25rem' }}>
                😊 {stats ? stats.positive_review_count : 0} / 😢 {stats ? stats.negative_review_count : 0}
              </div>
              <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: '0.2rem' }}>KoELECTRA-NSMC 감성 판정</div>
            </div>
          </div>

          {/* ================= 탭 1: AI 분석 실행 화면 (Gradio 스타일 입출력) ================= */}
          {activeMenu === 'analyze' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1.05fr 1fr', gap: '1.25rem' }}>
              {/* 좌측: 2칸 분리 입력 폼 */}
              <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '14px', padding: '1.35rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 800 }}>📝 1) 뉴스 원문 & 독자 리뷰 입력 (2칸 분리)</h3>
                  <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>비워둔 칸은 자동 생략됩니다</span>
                </div>

                {/* 원클릭 예제 프리셋 버튼 (Gradio examples 역할) */}
                <div style={{ marginBottom: '1rem' }}>
                  <div style={{ fontSize: '0.76rem', color: '#94a3b8', marginBottom: '0.4rem', fontWeight: 600 }}>
                    ⚡ 원클릭 샘플 예제 입력 (Gradio Examples):
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {SAMPLE_PRESETS.map((p, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handlePresetClick(p)}
                        style={{
                          padding: '0.35rem 0.65rem',
                          borderRadius: '8px',
                          border: '1px solid rgba(99,102,241,0.35)',
                          background: 'rgba(99,102,241,0.12)',
                          color: '#c7d2fe',
                          fontSize: '0.76rem',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                {errorMsg && (
                  <div
                    style={{
                      padding: '0.75rem',
                      borderRadius: '8px',
                      background: 'rgba(244,63,94,0.15)',
                      border: '1px solid rgba(244,63,94,0.35)',
                      color: '#fda4af',
                      fontSize: '0.84rem',
                      fontWeight: 600,
                      marginBottom: '0.9rem',
                    }}
                  >
                    {errorMsg}
                  </div>
                )}

                <form onSubmit={handleAnalyzeSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.95rem' }}>
                  {/* 칸 1: 뉴스 기사 원문 */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#e2e8f0', marginBottom: '0.35rem' }}>
                      📰 칸 1: 뉴스 기사 제목 / 본문 원문 <span style={{ color: '#818cf8', fontWeight: 500 }}>(KoELECTRA 7대 카테고리 분류)</span>
                    </label>
                    <textarea
                      rows={3}
                      value={newsText}
                      onChange={(e) => setNewsText(e.target.value)}
                      placeholder="분석할 뉴스 기사 제목이나 본문을 입력하세요... (비워두면 뉴스 분류는 생략됩니다)"
                      style={{
                        width: '100%',
                        padding: '0.7rem',
                        borderRadius: '8px',
                        border: '1px solid rgba(148,163,184,0.25)',
                        background: '#0f172a',
                        color: '#f8fafc',
                        fontSize: '0.88rem',
                        resize: 'vertical',
                      }}
                    />
                  </div>

                  {/* 칸 2: 독자 리뷰/댓글 */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#e2e8f0', marginBottom: '0.35rem' }}>
                      💬 칸 2: 독자 리뷰 / 댓글 반응 <span style={{ color: '#6ee7b7', fontWeight: 500 }}>(KoELECTRA 긍정/부정 감성 분석)</span>
                    </label>
                    <textarea
                      rows={3}
                      value={reviewText}
                      onChange={(e) => setReviewText(e.target.value)}
                      placeholder="독자 댓글이나 리뷰 문장을 입력하세요... (비워두면 감성 분석은 생략됩니다)"
                      style={{
                        width: '100%',
                        padding: '0.7rem',
                        borderRadius: '8px',
                        border: '1px solid rgba(148,163,184,0.25)',
                        background: '#0f172a',
                        color: '#f8fafc',
                        fontSize: '0.88rem',
                        resize: 'vertical',
                      }}
                    />
                  </div>

                  {/* 부가 정보: 사진 ID & 한줄 메모 */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.76rem', color: '#94a3b8', marginBottom: '0.25rem' }}>
                        📷 첨부 사진 ID (선택, 1026 Agent 호환)
                      </label>
                      <input
                        type="text"
                        value={photoId}
                        onChange={(e) => setPhotoId(e.target.value)}
                        placeholder="예: PHOTO_NV_2026_01"
                        style={{
                          width: '100%',
                          padding: '0.55rem 0.75rem',
                          borderRadius: '8px',
                          border: '1px solid rgba(148,163,184,0.25)',
                          background: '#0f172a',
                          color: '#f8fafc',
                          fontSize: '0.84rem',
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.76rem', color: '#94a3b8', marginBottom: '0.25rem' }}>
                        🏷️ MySQL 저장 메모 (선택)
                      </label>
                      <input
                        type="text"
                        value={memo}
                        onChange={(e) => setMemo(e.target.value)}
                        placeholder="분석 기록에 남길 메모"
                        style={{
                          width: '100%',
                          padding: '0.55rem 0.75rem',
                          borderRadius: '8px',
                          border: '1px solid rgba(148,163,184,0.25)',
                          background: '#0f172a',
                          color: '#f8fafc',
                          fontSize: '0.84rem',
                        }}
                      />
                    </div>
                  </div>

                  {/* 규칙 2: GPT 에이전트 요약 토글 */}
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.6rem',
                      padding: '0.65rem 0.85rem',
                      borderRadius: '8px',
                      background: 'rgba(99,102,241,0.1)',
                      border: '1px solid rgba(99,102,241,0.3)',
                      cursor: 'pointer',
                      fontSize: '0.84rem',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={useGptAgent}
                      onChange={(e) => setUseGptAgent(e.target.checked)}
                    />
                    <span>
                      🤖 <strong>OpenAI GPT 에이전트 종합 요약 함께 실행</strong>{' '}
                      <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                        (해제 시 로컬 KoELECTRA 2종만 초고속 실행)
                      </span>
                    </span>
                  </label>

                  <button
                    type="submit"
                    disabled={loading}
                    style={{
                      padding: '0.85rem',
                      borderRadius: '10px',
                      border: 'none',
                      background: loading ? '#475569' : 'linear-gradient(135deg, #6366f1, #4f46e5)',
                      color: '#fff',
                      fontWeight: 800,
                      fontSize: '0.95rem',
                      cursor: loading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {loading
                      ? '⏳ KoELECTRA 모델 추론 및 MySQL 저장 중...'
                      : '🚀 AI 분석 실행 및 MySQL 자동 저장 (POST /api/analyze)'}
                  </button>
                </form>
              </div>

              {/* 우측: Gradio gr.Label 스타일 확률 분포 & 리포트 출력 */}
              <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '14px', padding: '1.35rem' }}>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 800, marginBottom: '0.9rem' }}>
                  📊 2) 실시간 AI 분석 결과 시각화 (Gradio <code>gr.Label</code> & 리포트)
                </h3>

                {!latestResult ? (
                  <div style={{ color: '#94a3b8', fontSize: '0.88rem', padding: '2rem 0', textAlign: 'center' }}>
                    좌측에서 텍스트를 입력하고 [AI 분석 실행] 버튼을 눌러주세요.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
                    {/* 1. 뉴스 7대 카테고리 분류 확률 바 (Top-3) */}
                    <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '10px', border: '1px solid rgba(148,163,184,0.2)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
                        <span style={{ fontSize: '0.84rem', fontWeight: 700, color: '#cbd5e1' }}>
                          📰 뉴스 카테고리 분류 결과 (Top-3 확률 분포)
                        </span>
                        {latestResult.predicted_category === '미입력' ? (
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>뉴스 원문 미입력 (생략됨)</span>
                        ) : latestResult.is_high_confidence ? (
                          <span
                            style={{
                              padding: '0.2rem 0.65rem',
                              borderRadius: '999px',
                              background: 'rgba(16,185,129,0.18)',
                              color: '#6ee7b7',
                              border: '1px solid rgba(16,185,129,0.4)',
                              fontSize: '0.75rem',
                              fontWeight: 800,
                            }}
                          >
                            ✅ {latestResult.predicted_category} ({latestResult.category_confidence}% · 정상분류)
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '0.2rem 0.65rem',
                              borderRadius: '999px',
                              background: 'rgba(245,158,11,0.2)',
                              color: '#fcd34d',
                              border: '1px solid rgba(245,158,11,0.45)',
                              fontSize: '0.75rem',
                              fontWeight: 800,
                            }}
                          >
                            ⚠️ 분류보류/모호 ({latestResult.predicted_category}? {latestResult.category_confidence}% &lt; 70%)
                          </span>
                        )}
                      </div>

                      {latestResult.top3_categories && latestResult.top3_categories.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {latestResult.top3_categories.map((item, idx) => (
                            <div key={idx}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '3px' }}>
                                <span style={{ fontWeight: idx === 0 ? 800 : 500, color: idx === 0 ? '#fff' : '#94a3b8' }}>
                                  {idx + 1}위. {item.category}
                                </span>
                                <span style={{ fontWeight: 700 }}>{item.probability_percent}%</span>
                              </div>
                              <div style={{ height: '9px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
                                <div
                                  style={{
                                    width: `${Math.min(100, item.probability_percent)}%`,
                                    height: '100%',
                                    background: idx === 0 ? (latestResult.is_high_confidence ? '#6366f1' : '#f59e0b') : '#475569',
                                  }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.8rem', color: '#64748b' }}>뉴스 원문이 비어 있어 카테고리 분류를 생략했습니다.</div>
                      )}
                    </div>

                    {/* 2. 독자 리뷰 감성 분석 확률 바 (긍정 vs 부정) */}
                    <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '10px', border: '1px solid rgba(148,163,184,0.2)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
                        <span style={{ fontSize: '0.84rem', fontWeight: 700, color: '#cbd5e1' }}>
                          💬 독자 리뷰 감성 분석 (KoELECTRA-NSMC)
                        </span>
                        <span
                          style={{
                            padding: '0.2rem 0.65rem',
                            borderRadius: '999px',
                            background:
                              latestResult.sentiment_label === '미입력'
                                ? 'rgba(148,163,184,0.15)'
                                : latestResult.sentiment_label?.includes('긍정')
                                ? 'rgba(16,185,129,0.18)'
                                : 'rgba(244,63,94,0.18)',
                            color:
                              latestResult.sentiment_label === '미입력'
                                ? '#94a3b8'
                                : latestResult.sentiment_label?.includes('긍정')
                                ? '#6ee7b7'
                                : '#fda4af',
                            fontSize: '0.75rem',
                            fontWeight: 800,
                          }}
                        >
                          {latestResult.sentiment_label || '미입력'}
                        </span>
                      </div>

                      {latestResult.sentiment_label !== '미입력' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '3px' }}>
                              <span style={{ color: '#6ee7b7', fontWeight: 700 }}>😊 긍정 (Positive)</span>
                              <span style={{ fontWeight: 700 }}>{latestResult.positive_percent}%</span>
                            </div>
                            <div style={{ height: '9px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
                              <div style={{ width: `${latestResult.positive_percent}%`, height: '100%', background: '#10b981' }} />
                            </div>
                          </div>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '3px' }}>
                              <span style={{ color: '#fda4af', fontWeight: 700 }}>😢 부정 (Negative)</span>
                              <span style={{ fontWeight: 700 }}>{latestResult.negative_percent}%</span>
                            </div>
                            <div style={{ height: '9px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
                              <div style={{ width: `${latestResult.negative_percent}%`, height: '100%', background: '#f43f5e' }} />
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.8rem', color: '#64748b' }}>독자 리뷰 칸이 비어 있어 감성 분석을 생략했습니다.</div>
                      )}
                    </div>

                    {/* 3. 상세 리포트 출력 (Gradio gr.Textbox 역할) */}
                    <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '10px', border: '1px solid rgba(148,163,184,0.2)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.45rem' }}>
                        <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#a5b4fc' }}>
                          📋 AI 에이전트 종합 분석 리포트 (MySQL ID #{latestResult.id} 자동 저장됨)
                        </span>
                        <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>{latestResult.created_at}</span>
                      </div>
                      <pre
                        style={{
                          whiteSpace: 'pre-wrap',
                          fontFamily: 'inherit',
                          fontSize: '0.84rem',
                          lineHeight: 1.6,
                          color: '#e2e8f0',
                        }}
                      >
                        {latestResult.ai_report}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ================= 탭 2: MySQL 저장 기록 조회 · 필터 · 수정 · 삭제 (CRUD) ================= */}
          {activeMenu === 'history' && (
            <div style={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '14px', padding: '1.35rem' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                  marginBottom: '1rem',
                }}
              >
                <div>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 800 }}>
                    🗄️ MySQL <code>news_analysis_logs</code> 테이블 실시간 목록
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
                    신뢰도 70% 미만인 <strong>⚠️ 분류보류(모호)</strong> 기사는 드롭다운에서 카테고리를 수동 확정(<code>PUT</code>)할 수 있습니다.
                  </p>
                </div>

                {/* 필터 바 */}
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <select
                    value={filterCategory}
                    onChange={(e) => setFilterCategory(e.target.value)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '8px',
                      background: '#0f172a',
                      color: '#f8fafc',
                      border: '1px solid rgba(148,163,184,0.25)',
                      fontSize: '0.82rem',
                    }}
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        분야: {c}
                      </option>
                    ))}
                  </select>

                  <select
                    value={filterSentiment}
                    onChange={(e) => setFilterSentiment(e.target.value)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '8px',
                      background: '#0f172a',
                      color: '#f8fafc',
                      border: '1px solid rgba(148,163,184,0.25)',
                      fontSize: '0.82rem',
                    }}
                  >
                    <option value="전체">감성: 전체</option>
                    <option value="긍정">😊 긍정 리뷰만</option>
                    <option value="부정">😢 부정 리뷰만</option>
                  </select>

                  <select
                    value={filterConfidence}
                    onChange={(e) => setFilterConfidence(e.target.value)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '8px',
                      background: '#0f172a',
                      color: '#f8fafc',
                      border: '1px solid rgba(148,163,184,0.25)',
                      fontSize: '0.82rem',
                    }}
                  >
                    <option value="all">신뢰도: 전체 보기</option>
                    <option value="high">✅ 70% 이상 (정상분류만)</option>
                    <option value="hold">⚠️ 70% 미만 (분류보류만)</option>
                  </select>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.25)', color: '#94a3b8', textAlign: 'left' }}>
                      <th style={{ padding: '0.7rem' }}>ID</th>
                      <th style={{ padding: '0.7rem' }}>뉴스 기사 원문 / 독자 리뷰</th>
                      <th style={{ padding: '0.7rem' }}>뉴스 분류 (70% 기준)</th>
                      <th style={{ padding: '0.7rem' }}>리뷰 감성</th>
                      <th style={{ padding: '0.7rem' }}>메모</th>
                      <th style={{ padding: '0.7rem' }}>관리 (PUT / DELETE)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((row) => (
                      <tr key={row.id} style={{ borderBottom: '1px solid rgba(148,163,184,0.14)' }}>
                        <td style={{ padding: '0.75rem', fontWeight: 700, color: '#a5b4fc' }}>#{row.id}</td>
                        <td style={{ padding: '0.75rem', maxWidth: '420px' }}>
                          {row.news_text && (
                            <div style={{ fontWeight: 700, color: '#f8fafc', marginBottom: '3px' }}>
                              📰 {row.news_text}
                            </div>
                          )}
                          {row.review_text && (
                            <div style={{ color: '#cbd5e1', fontSize: '0.8rem' }}>💬 {row.review_text}</div>
                          )}
                          <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '3px' }}>
                            {row.created_at} {row.photo_id ? `· 📷 ${row.photo_id}` : ''}
                          </div>
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          {row.predicted_category === '미입력' ? (
                            <span style={{ color: '#64748b' }}>미입력</span>
                          ) : row.is_high_confidence ? (
                            <span
                              style={{
                                padding: '0.2rem 0.6rem',
                                borderRadius: '999px',
                                background: 'rgba(16,185,129,0.16)',
                                color: '#6ee7b7',
                                fontWeight: 700,
                                fontSize: '0.76rem',
                              }}
                            >
                              ✅ {row.predicted_category} ({row.category_confidence}%)
                            </span>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                              <span
                                style={{
                                  padding: '0.2rem 0.6rem',
                                  borderRadius: '999px',
                                  background: 'rgba(245,158,11,0.2)',
                                  color: '#fcd34d',
                                  fontWeight: 700,
                                  fontSize: '0.75rem',
                                }}
                              >
                                ⚠️ 분류보류 ({row.predicted_category}? {row.category_confidence}%)
                              </span>
                              <select
                                defaultValue=""
                                onChange={(e) => e.target.value && handleConfirmCategory(row, e.target.value)}
                                style={{
                                  padding: '0.25rem',
                                  borderRadius: '6px',
                                  background: '#0f172a',
                                  color: '#fcd34d',
                                  border: '1px solid rgba(245,158,11,0.4)',
                                  fontSize: '0.74rem',
                                }}
                              >
                                <option value="" disabled>
                                  수동 카테고리 확정...
                                </option>
                                {CATEGORIES.filter((c) => c !== '전체').map((c) => (
                                  <option key={c} value={c}>
                                    {c}으로 확정
                                  </option>
                                ))}
                              </select>
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          {row.sentiment_label === '미입력' ? (
                            <span style={{ color: '#64748b' }}>미입력</span>
                          ) : (
                            <span
                              style={{
                                padding: '0.2rem 0.6rem',
                                borderRadius: '999px',
                                background: row.sentiment_label?.includes('긍정')
                                  ? 'rgba(16,185,129,0.16)'
                                  : 'rgba(244,63,94,0.16)',
                                color: row.sentiment_label?.includes('긍정') ? '#6ee7b7' : '#fda4af',
                                fontWeight: 700,
                                fontSize: '0.76rem',
                              }}
                            >
                              {row.sentiment_label} ({Math.max(row.positive_percent, row.negative_percent)}%)
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem', color: '#cbd5e1', fontSize: '0.8rem' }}>
                          {row.memo || '-'}
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          <div style={{ display: 'flex', gap: '0.4rem' }}>
                            <button
                              onClick={() => handleEditMemo(row)}
                              style={{
                                padding: '0.3rem 0.6rem',
                                borderRadius: '6px',
                                border: '1px solid rgba(148,163,184,0.3)',
                                background: '#0f172a',
                                color: '#e2e8f0',
                                fontSize: '0.76rem',
                                cursor: 'pointer',
                              }}
                            >
                              ✏️ 메모
                            </button>
                            <button
                              onClick={() => handleDeleteLog(row.id)}
                              style={{
                                padding: '0.3rem 0.6rem',
                                borderRadius: '6px',
                                border: '1px solid rgba(244,63,94,0.35)',
                                background: 'rgba(244,63,94,0.18)',
                                color: '#fda4af',
                                fontSize: '0.76rem',
                                cursor: 'pointer',
                              }}
                            >
                              🗑️ 삭제
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

