import React from 'react';
import {
  LayoutDashboard,
  Compass,
  FileText,
  UserCheck,
  Receipt,
  ShieldCheck,
  Settings,
  Shield,
  Lock,
  X,
  CreditCard,
} from 'lucide-react';
import { cn } from '../lib/utils';

export type NavigationSection =
  | 'dashboard'
  | 'discover'
  | 'proposals'
  | 'approvals'
  | 'transactions'
  | 'audit'
  | 'settings';

interface SidebarProps {
  activeSection: NavigationSection;
  onSelectSection: (section: NavigationSection) => void;
  pendingApprovalsCount?: number;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

interface NavItem {
  id: NavigationSection;
  label: string;
  icon: React.ElementType;
  badge?: string | number;
  badgeColor?: string;
  description: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeSection,
  onSelectSection,
  pendingApprovalsCount = 0,
  isOpenMobile = false,
  onCloseMobile,
}) => {
  const navItems: NavItem[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: LayoutDashboard,
      description: 'Executive trust telemetry & health overview',
    },
    {
      id: 'discover',
      label: 'Discover Products',
      icon: Compass,
      description: 'Channel3 & Amazon product candidate search',
    },
    {
      id: 'proposals',
      label: 'Purchase Proposals',
      icon: FileText,
      description: 'AI mandate composer & policy simulator',
    },
    {
      id: 'approvals',
      label: 'Approval Center',
      icon: UserCheck,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
      badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
      description: 'Explicit human sign-off & checkout gate',
    },
    {
      id: 'transactions',
      label: 'Transactions',
      icon: Receipt,
      description: 'Persisted lifecycle states & orders grid',
    },
    {
      id: 'audit',
      label: 'Audit Trail',
      icon: ShieldCheck,
      description: 'Cryptographic SHA-256 hash-chain ledger',
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: Settings,
      description: 'API diagnostics & sandbox configuration',
    },
  ];

  const handleSelect = (section: NavigationSection) => {
    onSelectSection(section);
    if (onCloseMobile) {
      onCloseMobile();
    }
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-navy-950 border-r border-navy-800 text-slate-200">
      {/* Brand Header */}
      <div className="h-16 px-5 border-b border-navy-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500/20 to-navy-900 border border-emerald-500/40 text-emerald-400 shadow-emerald-glow">
            <Shield className="w-5 h-5 text-emerald-400" />
            <span className="absolute -top-1 -right-1 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-base tracking-tight text-white">PayPal</span>
              <span className="font-semibold text-base text-emerald-400 tracking-tight">TrustGate</span>
            </div>
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
              Fintech Guard v0.1
            </span>
          </div>
        </div>

        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-navy-900"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Security Perimeter Status Pill */}
      <div className="p-3 mx-3 my-3 rounded-xl bg-navy-900/80 border border-navy-800">
        <div className="flex items-center justify-between text-[11px] font-mono mb-1.5">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Lock className="w-3 h-3 text-emerald-400" />
            AI Guardrail
          </span>
          <span className="px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
            ZERO AUTH
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-snug">
          Autonomous AI payments barred. Human approval mandatory.
        </p>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1 overflow-y-auto" aria-label="Main Navigation">
        <div className="px-3 py-2 text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
          Platform Navigation
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeSection === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => handleSelect(item.id)}
              className={cn(
                'w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all group text-left',
                isActive
                  ? 'bg-emerald-500/15 text-white border border-emerald-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-navy-900 border border-transparent'
              )}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={cn(
                    'p-1.5 rounded-lg transition-colors',
                    isActive
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-navy-900 text-slate-400 group-hover:text-slate-200'
                  )}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="truncate">
                  <div className="font-semibold truncate">{item.label}</div>
                  <div className="text-[10px] text-slate-400 truncate hidden lg:block">
                    {item.description}
                  </div>
                </div>
              </div>

              {item.badge !== undefined && (
                <span
                  className={cn(
                    'px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ml-2 shrink-0 animate-pulse',
                    item.badgeColor || 'bg-navy-800 text-slate-300 border-navy-700'
                  )}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer / PayPal Sandbox badge */}
      <div className="p-3 border-t border-navy-800 bg-navy-900/40">
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-navy-950/70 border border-navy-800">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-paypal-blue animate-pulse"></div>
            <div>
              <div className="text-[11px] font-bold text-slate-200 flex items-center gap-1">
                PayPal Sandbox
              </div>
              <div className="text-[10px] font-mono text-slate-400">Orders v2 Safe Mode</div>
            </div>
          </div>
          <CreditCard className="w-4 h-4 text-slate-400" />
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Permanent Sidebar */}
      <aside className="hidden md:flex flex-col w-64 lg:w-72 shrink-0 h-screen sticky top-0 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Overlay */}
      {isOpenMobile && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <div
            className="fixed inset-0 bg-navy-950/80 backdrop-blur-sm"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <aside className="relative flex flex-col w-72 max-w-[85vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
};
