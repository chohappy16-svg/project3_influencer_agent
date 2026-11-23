import React, { useState, useEffect, useCallback } from 'react';
import { authApi, campaignsApi } from './api/client';
import AuthOnboardingPage from './pages/AuthOnboardingPage';
import WorkspaceLayout from './components/WorkspaceLayout';
import CampaignDashboardPage from './pages/CampaignDashboardPage';
import CampaignCreatePage from './pages/CampaignCreatePage';
import CandidateUploadPage from './pages/CandidateUploadPage';
import CampaignResultsPage from './pages/CampaignResultsPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import CandidateComparePage from './pages/CandidateComparePage';
import ApprovedCandidatesPage from './pages/ApprovedCandidatesPage';
import BrandDnaSettingsPage from './pages/BrandDnaSettingsPage';
import AccountSettingsPage from './pages/AccountSettingsPage';

export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);

  const [view, setView] = useState('dashboard'); // 'dashboard' | 'create' | 'upload' | 'results' | 'detail' | 'compare' | 'approved' | 'dna' | 'settings'
  const [campaigns, setCampaigns] = useState([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(false);

  const [activeCampaign, setActiveCampaign] = useState(null);
  const [campaignResults, setCampaignResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [lastCostSummary, setLastCostSummary] = useState(null);

  const [activeCandidate, setActiveCandidate] = useState(null);
  const [compareIds, setCompareIds] = useState([]);
  const [cloneTemplate, setCloneTemplate] = useState(null);

  const fetchCampaigns = useCallback(async () => {
    setLoadingCampaigns(true);
    try {
      const list = await campaignsApi.list();
      setCampaigns(list);
    } catch {
      // ignore
    } finally {
      setLoadingCampaigns(false);
    }
  }, []);

  // F5 새로고침 시 JWT 토큰 검증 및 사용자·브랜드 DNA 자동 복원
  useEffect(() => {
    const token = localStorage.getItem('influenceops_token');
    if (!token) {
      setBooting(false);
      return;
    }
    authApi
      .getMe()
      .then((me) => {
        setUser(me);
        fetchCampaigns();
      })
      .catch(() => {
        localStorage.removeItem('influenceops_token');
      })
      .finally(() => {
        setBooting(false);
      });
  }, [fetchCampaigns]);

  const handleAuthSuccess = (userInfo) => {
    setUser(userInfo);
    setView('dashboard');
    fetchCampaigns();
  };

  const handleLogout = () => {
    localStorage.removeItem('influenceops_token');
    setUser(null);
    setCampaigns([]);
    setActiveCampaign(null);
    setCampaignResults([]);
    setView('dashboard');
  };

  const handleSelectCampaign = async (campaign, targetView = 'results') => {
    setActiveCampaign(campaign);
    setLastCostSummary(null);
    setCompareIds([]);
    if (targetView === 'upload') {
      setView('upload');
      return;
    }
    setView('results');
    setLoadingResults(true);
    try {
      const rows = await campaignsApi.getResults(campaign.id);
      setCampaignResults(rows);
    } catch {
      setCampaignResults([]);
    } finally {
      setLoadingResults(false);
    }
  };

  const handleCampaignCreated = (created) => {
    setCampaigns((prev) => [created, ...prev]);
    setActiveCampaign(created);
    setView('upload');
  };

  const handleAnalysisComplete = async (uploadRes) => {
    setView('results');
    setLoadingResults(true);
    setLastCostSummary(uploadRes?.cost_summary || null);
    const targetCampaignId = uploadRes?.campaign_id || activeCampaign?.id;
    try {
      if (targetCampaignId) {
        const fullRows = await campaignsApi.getResults(targetCampaignId);
        setCampaignResults(fullRows);
      } else {
        setCampaignResults(uploadRes?.results || []);
      }
    } catch {
      setCampaignResults(uploadRes?.results || []);
    } finally {
      setLoadingResults(false);
    }
    fetchCampaigns();
  };

  const handleDecisionUpdated = (resultId, newApprovalState) => {
    setCampaignResults((prev) =>
      prev.map((r) => (r.id === resultId ? { ...r, approval_state: newApprovalState } : r))
    );
    if (activeCandidate && activeCandidate.id === resultId) {
      setActiveCandidate((prev) => ({ ...prev, approval_state: newApprovalState }));
    }
  };

  const handleResultsDeleted = (deletedIds) => {
    const idSet = new Set(deletedIds);
    setCampaignResults((prev) => prev.filter((r) => !idSet.has(r.id)));
    setCompareIds((prev) => prev.filter((id) => !idSet.has(id)));
    fetchCampaigns();
  };

  if (booting) {
    return (
      <div className="min-h-screen bg-brand-bg flex items-center justify-center text-sm text-slate-500">
        세션을 복원하고 있습니다...
      </div>
    );
  }

  if (!user) {
    return <AuthOnboardingPage onAuthSuccess={handleAuthSuccess} />;
  }

  const activeMenuMap = {
    dashboard: 'campaigns',
    create: 'campaigns',
    upload: 'campaigns',
    results: 'campaigns',
    detail: 'campaigns',
    compare: 'campaigns',
    approved: 'approved',
    dna: 'dna',
    settings: 'settings',
  };

  const breadcrumbMap = {
    dashboard: '캠페인 대시보드',
    create: '새 캠페인 만들기',
    upload: '후보 업로드',
    results: activeCampaign ? `${activeCampaign.title} / 분석 결과` : '분석 결과',
    detail: activeCandidate ? `후보 상세 / @${activeCandidate.instagram_id}` : '후보 상세',
    compare: '후보 2인 비교',
    approved: '선정 후보 관리',
    dna: '브랜드 DNA',
    settings: '계정 및 워크스페이스 설정',
  };

  return (
    <WorkspaceLayout
      user={user}
      activeMenu={activeMenuMap[view] || 'campaigns'}
      campaignCount={campaigns.length}
      breadcrumb={breadcrumbMap[view] || '캠페인'}
      onLogout={handleLogout}
      onNavigate={(menuId) => {
        if (menuId === 'campaigns') {
          setView('dashboard');
          fetchCampaigns();
        } else {
          setView(menuId);
        }
      }}
    >
      {view === 'dashboard' && (
        <CampaignDashboardPage
          user={user}
          campaigns={campaigns}
          loading={loadingCampaigns}
          onCreateClick={() => {
            setCloneTemplate(null);
            setView('create');
          }}
          onCloneCampaign={(camp) => {
            setCloneTemplate(camp);
            setView('create');
          }}
          onRefreshCampaigns={fetchCampaigns}
          onSelectCampaign={handleSelectCampaign}
          onGoToDna={() => setView('dna')}
        />
      )}

      {view === 'create' && (
        <CampaignCreatePage
          user={user}
          template={cloneTemplate}
          onBack={() => {
            setCloneTemplate(null);
            setView('dashboard');
          }}
          onCreated={(created) => {
            setCloneTemplate(null);
            handleCampaignCreated(created);
          }}
        />
      )}

      {view === 'upload' && activeCampaign && (
        <CandidateUploadPage
          campaign={activeCampaign}
          onBack={() => setView('dashboard')}
          onBackToForm={() => setView('create')}
          onAnalysisComplete={handleAnalysisComplete}
        />
      )}

      {view === 'results' && activeCampaign && (
        <CampaignResultsPage
          campaign={activeCampaign}
          results={campaignResults}
          costSummary={lastCostSummary}
          loading={loadingResults}
          compareIds={compareIds}
          onChangeCompareIds={setCompareIds}
          onUploadMore={() => setView('upload')}
          onDecisionUpdated={handleDecisionUpdated}
          onResultsDeleted={handleResultsDeleted}
          onCompareSelected={(ids) => {
            setCompareIds(ids);
            setView('compare');
          }}
          onOpenDetail={(r) => {
            setActiveCandidate(r);
            setView('detail');
          }}
        />
      )}

      {view === 'detail' && activeCampaign && activeCandidate && (
        <CandidateDetailPage
          campaign={activeCampaign}
          candidate={activeCandidate}
          allCandidates={campaignResults}
          compareIds={compareIds}
          onBack={() => setView('results')}
          onDecisionUpdated={handleDecisionUpdated}
          onStartCompare={(ids) => {
            setCompareIds(ids);
            setView('compare');
          }}
        />
      )}

      {view === 'compare' && activeCampaign && (
        <CandidateComparePage
          campaign={activeCampaign}
          selectedIds={compareIds}
          allCandidates={campaignResults}
          onUpdateCompareIds={setCompareIds}
          onBack={() => setView('results')}
          onDecisionUpdated={handleDecisionUpdated}
        />
      )}

      {view === 'approved' && (
        <ApprovedCandidatesPage
          user={user}
          campaigns={campaigns}
          onDecisionUpdated={handleDecisionUpdated}
          onSelectDetail={(campObj, cand) => {
            setActiveCampaign(campObj);
            setActiveCandidate(cand);
            setView('detail');
          }}
        />
      )}

      {view === 'dna' && (
        <BrandDnaSettingsPage
          user={user}
          onBack={() => setView('dashboard')}
          onUpdateLocalDna={(updated) => setUser((prev) => ({ ...prev, ...updated }))}
        />
      )}

      {view === 'settings' && (
        <AccountSettingsPage
          user={user}
          onGoToDna={() => setView('dna')}
          onLogout={handleLogout}
        />
      )}
    </WorkspaceLayout>
  );
}
