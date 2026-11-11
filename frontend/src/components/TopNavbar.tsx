import React from 'react';
import {
  Menu,
  RefreshCw,
  Lock,
  CheckCircle2,
} from 'lucide-react';
import { SystemHealth } from '../types';
import { NavigationSection } from './Sidebar';
import { cn } from '../lib/utils';

interface TopNavbarProps {
  currentSection: NavigationSection;
  health: SystemHealth | null;
  isLoadingHealth?: boolean;
  onRefreshHealth?: () => void;
  onOpenMobileMenu?: () => void;
}

const SECTION_TITLES: Record<
  NavigationSection,
  { title: string; subtitle: string; category: string }
> = {
  dashboard: {
    title: 'Executive Trust Dashboard',
    subtitle: 'Real-time telemetry, transaction volumes & cryptographic chain health',
    category: 'Analytics & Health',
  },
  discover: {
    title: 'Product Discovery',
    subtitle: 'Channel3 Multi-Merchant Catalog & Amazon Creators search engine',
    category: 'Candidate Discovery',
  },
  proposals: {
    title: 'Purchase Proposals & Policies',
    subtitle: 'Groq natural language mandate interpreter & TG-001–TG-007 simulator',
    category: 'Policy Authoring',
  },
  approvals: {
    title: 'Human Approval Center',
    subtitle: 'Explicit operator authorization gate — AI autonomous execution prohibited',
    category: 'Security Gate',
  },
  transactions: {
    title: 'Transaction Intelligence',
    subtitle: 'Persisted lifecycle state machine, order linkages & forensic inspection',
    category: 'Ledger Records',
  },
  audit: {
    title: 'Cryptographic Audit Trail',
    subtitle: 'SHA-256 hash-chained immutable event timeline & tamper-evidence verification',
    category: 'Security Ledger',
  },
  settings: {
    title: 'Settings & API Diagnostics',
    subtitle: 'PayPal Sandbox credentials, Channel3 Universal Graph & engine configuration',
    category: 'System Config',
  },
};

export const TopNavbar: React.FC<TopNavbarProps> = ({
  currentSection,
  health,
  isLoadingHealth = false,
  onRefreshHealth,
  onOpenMobileMenu,
}) => {
  const sectionMeta = SECTION_TITLES[currentSection];
  const isHealthy = health?.status === 'healthy' || health?.status === 'ok';

  return (
    <header className="sticky top-0 z-20 w-full border-b border-navy-800 bg-navy-950/85 backdrop-blur-md">
      <div className="w-full px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Mobile Toggle & Page Title */}
        <div className="flex items-center gap-3 min-w-0">
          {onOpenMobileMenu && (
            <button
              type="button"
              onClick={onOpenMobileMenu}
              className="md:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-navy-900 border border-navy-800"
              aria-label="Open navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}

          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400 uppercase tracking-widest">
              <span>TrustGate</span>
              <span>/</span>
              <span className="text-emerald-400 font-bold">{sectionMeta.category}</span>
            </div>
            <h1 className="text-base sm:text-lg font-bold text-white tracking-tight truncate">
              {sectionMeta.title}
            </h1>
          </div>
        </div>

        {/* Right: Telemetry & Operator Profile */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Backend Connection Status Pill */}
          <div
            className={cn(
              'flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-mono transition-colors',
              isHealthy
                ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                : 'bg-amber-950/40 border-amber-500/30 text-amber-300'
            )}
            title="FastAPI Backend Health"
          >
            <span className="relative flex h-2 w-2">
              <span
                className={cn(
                  'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
                  isHealthy ? 'bg-emerald-400' : 'bg-amber-400'
                )}
              />
              <span
                className={cn(
                  'relative inline-flex rounded-full h-2 w-2',
                  isHealthy ? 'bg-emerald-500' : 'bg-amber-500'
                )}
              />
            </span>
            <span className="hidden sm:inline font-bold">
              {isHealthy ? 'BACKEND LIVE' : 'CONNECTING'}
            </span>
          </div>

          {/* Refresh Health Action */}
          {onRefreshHealth && (
            <button
              type="button"
              onClick={onRefreshHealth}
              disabled={isLoadingHealth}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-navy-900 border border-navy-800 transition-colors"
              title="Refresh backend status"
            >
              <RefreshCw
                className={cn('w-4 h-4', isLoadingHealth ? 'animate-spin text-emerald-400' : '')}
              />
            </button>
          )}

          {/* Guardrail Invariant Pill */}
          <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-navy-900 border border-navy-800 text-xs font-mono text-slate-300">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Policy:</span>
            <span className="text-emerald-400 font-semibold">TG-001–007 Active</span>
          </div>

          {/* Operator Profile Chip */}
          <div className="flex items-center gap-2.5 pl-2 sm:pl-3 border-l border-navy-800">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500/20 to-navy-800 border border-emerald-500/30 text-emerald-400 font-mono text-xs font-bold">
              OP
            </div>
            <div className="hidden sm:block text-left leading-tight">
              <div className="text-xs font-bold text-slate-200">Security Operator</div>
              <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-2.5 h-2.5" />
                <span>Human Reviewer</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
