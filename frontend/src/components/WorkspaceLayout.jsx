import React from 'react';
import {
  LayoutGrid,
  Users,
  Dna,
  Settings,
  Bell,
  LogOut,
  ArrowUpRight,
  HelpCircle,
} from 'lucide-react';
import { BrandLogo } from './BrandLogo';

export default function WorkspaceLayout({
  user,
  activeMenu,
  onNavigate,
  campaignCount = 0,
  breadcrumb = '캠페인 대시보드',
  onLogout,
  children,
}) {
  const navItems = [
    { id: 'campaigns', label: '캠페인', icon: LayoutGrid, badge: campaignCount },
    { id: 'approved', label: '선정 후보', icon: Users },
    { id: 'dna', label: '브랜드 DNA', icon: Dna },
    { id: 'settings', label: '설정', icon: Settings },
  ];

  return (
    <div className="min-h-screen flex bg-brand-bg">
      {/* Left Dark Sidebar */}
      <aside className="w-[240px] shrink-0 bg-[#0F172A] text-slate-300 flex flex-col justify-between sticky top-0 h-screen">
        <div className="p-5">
          {/* Logo */}
          <div className="mb-6 cursor-pointer" onClick={() => onNavigate('campaigns')}>
            <BrandLogo dark showSubtext />
          </div>

          {/* Workspace Box */}
          <div className="p-3 rounded-xl bg-white/5 border border-white/10 mb-6">
            <div className="text-[10px] text-slate-400 font-medium">워크스페이스</div>
            <div className="text-sm font-bold text-white mt-0.5 truncate">
              {user?.company_name || '클린뷰티 랩'}
            </div>
          </div>

          {/* Navigation */}
          <div className="text-[10px] font-bold tracking-widest text-slate-500 uppercase px-2 mb-2">
            WORKSPACE
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeMenu === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition ${
                    isActive
                      ? 'bg-white text-brand-navy font-bold shadow-sm'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <Icon className={`w-4 h-4 ${isActive ? 'text-brand-sky' : 'text-slate-400'}`} />
                    {item.label}
                  </span>
                  {item.badge !== undefined && (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-md font-bold ${
                        isActive ? 'bg-slate-100 text-brand-navy' : 'text-slate-400'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom Area */}
        <div className="p-4 space-y-3">
          {/* Brand AI Card */}
          <div className="p-3.5 rounded-xl bg-white/5 border border-white/10">
            <div className="text-xs font-bold text-white mb-1">브랜드를 기억하는 AI</div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              저장된 브랜드 DNA를 기준으로 모든 후보를 일관되게 분석합니다.
            </p>
            <button
              onClick={() => onNavigate('dna')}
              className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-200 hover:text-brand-sky transition"
            >
              브랜드 DNA 확인 <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>

          <div className="flex items-center gap-2 px-2 py-1 text-xs text-slate-400">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>도움말</span>
          </div>

          {/* User Profile & Logout */}
          <div className="pt-3 border-t border-white/10 flex items-center justify-between px-1">
            <div className="min-w-0">
              <div className="text-xs font-bold text-white truncate">{user?.company_name || '마케터'}</div>
              <div className="text-[11px] text-slate-400 truncate">{user?.email || 'marketer@influenceops.ai'}</div>
            </div>
            <button
              onClick={onLogout}
              title="로그아웃"
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <header className="h-14 bg-white border-b border-slate-200/80 px-8 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>워크스페이스</span>
            <span>/</span>
            <span className="text-brand-navy font-semibold">{breadcrumb}</span>
          </div>

          <div className="flex items-center gap-5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
              <span className="w-2 h-2 rounded-full bg-brand-mint" />
              브랜드 DNA 연결됨
            </div>
            <button className="p-1.5 rounded-lg text-slate-400 hover:text-brand-navy hover:bg-slate-100 transition">
              <Bell className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Page Body */}
        <main className="flex-1 p-8 max-w-[1400px] w-full mx-auto">{children}</main>

        {/* Footer */}
        <footer className="px-8 py-4 border-t border-slate-200/60 text-[11px] text-slate-400 flex items-center justify-between">
          <span>InfluenceOps · 브랜드 인플루언서 섭외 의사결정 파트너</span>
          <span>InfluenceOps / 브랜드에 맞는 선택의 기준</span>
        </footer>
      </div>
    </div>
  );
}
