import React, { useState, useEffect } from 'react';
import { Download, Search, ExternalLink, RotateCcw } from 'lucide-react';
import { campaignsApi } from '../api/client';

export default function ApprovedCandidatesPage({ user, campaigns, onSelectDetail, onDecisionUpdated }) {
  const [selectedCampId, setSelectedCampId] = useState('ALL');
  const [approvedList, setApprovedList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [exporting, setExporting] = useState(false);
  const [cancelingId, setCancelingId] = useState(null);

  useEffect(() => {
    const loadAllApproved = async () => {
      setLoading(true);
      try {
        const allItems = [];
        for (const c of campaigns) {
          const rows = await campaignsApi.getResults(c.id);
          rows
            .filter((r) => r.approval_state === 'APPROVED')
            .forEach((r) => {
              allItems.push({ ...r, campaign_title: c.title, campaign_obj: c });
            });
        }
        setApprovedList(allItems);
      } catch {
        setApprovedList([]);
      } finally {
        setLoading(false);
      }
    };

    if (campaigns.length > 0) {
      loadAllApproved();
    } else {
      setLoading(false);
    }
  }, [campaigns]);

  const filtered = approvedList.filter((item) => {
    const matchCamp = selectedCampId === 'ALL' || String(item.campaign_id) === String(selectedCampId);
    const matchText =
      !searchTerm ||
      item.instagram_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.full_name || '').toLowerCase().includes(searchTerm.toLowerCase());
    return matchCamp && matchText;
  });

  const uniqueCampCount = new Set(approvedList.map((i) => i.campaign_id)).size;

  const handleExport = async () => {
    const targetId =
      selectedCampId !== 'ALL'
        ? Number(selectedCampId)
        : approvedList[0]?.campaign_id || campaigns[0]?.id;
    if (!targetId) return;
    setExporting(true);
    try {
      await campaignsApi.exportExcel(targetId);
    } finally {
      setExporting(false);
    }
  };

  const handleCancelApproval = async (e, item) => {
    e.stopPropagation();
    setCancelingId(item.id);
    try {
      await campaignsApi.decide(item.id, 'PENDING');
      setApprovedList((prev) => prev.filter((x) => x.id !== item.id));
      if (onDecisionUpdated) onDecisionUpdated(item.id, 'PENDING');
    } catch {
      // ignore
    } finally {
      setCancelingId(null);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">승인 후보 관리</h1>
          <p className="text-sm text-slate-500 mt-1">
            최종 승인한 크리에이터를 캠페인별로 모아보고 관리하세요.
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting || approvedList.length === 0}
          className="px-5 py-2.5 rounded-xl bg-brand-mint hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition disabled:opacity-50"
        >
          <Download className="w-4 h-4" /> {exporting ? '생성 중...' : '승인 목록 내보내기 ↓'}
        </button>
      </div>

      {/* 3 KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">전체 승인 후보</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-navy">{approvedList.length}명</span>
            <span className="text-xs text-slate-400">워크스페이스 전체</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">승인 캠페인</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-navy">{uniqueCampCount}개</span>
            <span className="text-xs text-slate-400">승인 후보가 있는 캠페인</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
          <div className="text-xs font-semibold text-slate-500">선택 필터 승인</div>
          <div className="flex items-baseline gap-2.5 mt-3">
            <span className="text-3xl font-extrabold text-brand-mint">{filtered.length}명</span>
            <span className="text-xs text-slate-400">엑셀 내보내기 대상</span>
          </div>
        </div>
      </div>

      {/* Main Mint-Accented Approved List Card */}
      <div className="rounded-2xl overflow-hidden border border-emerald-200 bg-white shadow-sm">
        <div className="bg-brand-mint px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <select
            value={selectedCampId}
            onChange={(e) => setSelectedCampId(e.target.value)}
            className="px-3.5 py-2 rounded-xl bg-white/15 text-white text-xs font-bold border border-white/25 focus:outline-none"
          >
            <option value="ALL" className="text-brand-navy">
              전체 캠페인 보기
            </option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id} className="text-brand-navy">
                {c.title}
              </option>
            ))}
          </select>

          <div className="relative w-64">
            <Search className="w-4 h-4 text-emerald-100 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="승인 후보 검색"
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-white/15 text-white placeholder-emerald-100 border border-white/25 focus:outline-none"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">승인 후보 목록을 불러오는 중...</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-400">
            아직 최종 승인된 인플루언서가 없습니다. 비교 뷰에서 후보를 승인해 주세요.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] font-bold text-slate-400 bg-slate-50/60">
                  <th className="py-3 px-6">인플루언서</th>
                  <th className="py-3 px-4">매칭률</th>
                  <th className="py-3 px-4">예상 원고료</th>
                  <th className="py-3 px-4">캠페인</th>
                  <th className="py-3 px-4">승인자</th>
                  <th className="py-3 px-6">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {filtered.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => onSelectDetail && onSelectDetail(item.campaign_obj, item)}
                    className="hover:bg-emerald-50/30 transition cursor-pointer"
                  >
                    <td className="py-4 px-6">
                      <div className="font-bold text-brand-navy flex items-center gap-1.5">
                        @{item.instagram_id}
                        <a
                          href={`https://www.instagram.com/${item.instagram_id}/`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-slate-400 hover:text-brand-sky"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {item.full_name || item.influencer_tier}
                      </div>
                    </td>
                    <td className="py-4 px-4 font-extrabold text-brand-mint text-sm">
                      {item.overall_match_percentage}%
                    </td>
                    <td className="py-4 px-4 font-semibold text-brand-navy">
                      {item.recommended_fee}
                    </td>
                    <td className="py-4 px-4 text-slate-600">{item.campaign_title}</td>
                    <td className="py-4 px-4 text-slate-600" title={user?.email || ''}>
                      {user?.email ? user.email.split('@')[0] : '마케터'}
                    </td>
                    <td className="py-4 px-6">
                      <div className="inline-flex items-center gap-2">
                        <span className="inline-flex px-2.5 py-1 rounded-md bg-emerald-50 text-brand-mint font-bold border border-emerald-200">
                          승인 완료
                        </span>
                        <button
                          type="button"
                          disabled={cancelingId === item.id}
                          onClick={(e) => handleCancelApproval(e, item)}
                          title="승인을 취소하고 검토 대기 상태로 되돌립니다"
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-slate-200 bg-white text-slate-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 font-semibold transition disabled:opacity-50"
                        >
                          <RotateCcw className="w-3 h-3" />
                          {cancelingId === item.id ? '취소 중' : '승인 취소'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
