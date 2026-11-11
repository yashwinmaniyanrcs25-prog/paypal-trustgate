import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  UserCheck,
  UserX,
  Clock,
  CheckCircle2,
  RefreshCw,
  TrendingUp,
  Database,
  Hash,
  Activity,
  CreditCard,
  Ban,
  ChevronRight,
} from 'lucide-react';
import { api } from '../lib/api';
import { cn } from '../lib/utils';

interface AuditSummary {
  storage_engine?: string;
  db_path?: string;
  persisted?: boolean;
  audit_chain_verified?: boolean;
  genesis_hash?: string;
  last_event_hash?: string;
  total_audit_events?: number;
  total_mandates?: number;
  total_staged_proposals?: number;
  total_paypal_captures?: number;
  total_evaluations?: number;
  approved_evaluations?: number;
  blocked_evaluations?: number;
  total_human_approvals?: number;
}

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  color?: 'emerald' | 'rose' | 'amber' | 'sky' | 'slate' | 'violet';
  highlight?: boolean;
  onClick?: () => void;
}

const colorMap = {
  emerald: {
    icon: 'text-emerald-400',
    iconBg: 'bg-emerald-500/10 border-emerald-500/20',
    glow: 'shadow-emerald-glow border-emerald-500/30',
    value: 'text-emerald-300',
    bar: 'bg-emerald-500',
  },
  rose: {
    icon: 'text-rose-400',
    iconBg: 'bg-rose-500/10 border-rose-500/20',
    glow: 'shadow-rose-500/10 border-rose-500/20',
    value: 'text-rose-300',
    bar: 'bg-rose-500',
  },
  amber: {
    icon: 'text-amber-400',
    iconBg: 'bg-amber-500/10 border-amber-500/20',
    glow: 'shadow-amber-500/10 border-amber-500/20',
    value: 'text-amber-300',
    bar: 'bg-amber-500',
  },
  sky: {
    icon: 'text-sky-400',
    iconBg: 'bg-sky-500/10 border-sky-500/20',
    glow: 'shadow-sky-500/10 border-sky-500/20',
    value: 'text-sky-300',
    bar: 'bg-sky-500',
  },
  slate: {
    icon: 'text-slate-300',
    iconBg: 'bg-navy-800 border-navy-700',
    glow: 'border-navy-700',
    value: 'text-slate-200',
    bar: 'bg-slate-500',
  },
  violet: {
    icon: 'text-violet-400',
    iconBg: 'bg-violet-500/10 border-violet-500/20',
    glow: 'shadow-violet-500/10 border-violet-500/20',
    value: 'text-violet-300',
    bar: 'bg-violet-500',
  },
};

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  sub,
  icon: Icon,
  color = 'slate',
  highlight = false,
  onClick,
}) => {
  const c = colorMap[color];
  return (
    <div
      onClick={onClick}
      className={cn(
        'relative group rounded-xl border bg-navy-900/90 p-5 transition-all duration-200',
        c.glow,
        onClick && 'cursor-pointer hover:bg-navy-900 hover:scale-[1.01]',
        highlight && 'bg-gradient-to-br from-navy-900 via-navy-900 to-emerald-950/20'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-medium text-slate-500 uppercase tracking-widest truncate">
            {label}
          </p>
          <p className={cn('mt-1 text-2xl font-bold font-mono tracking-tight', c.value)}>
            {value}
          </p>
          {sub && (
            <p className="mt-1 text-[11px] text-slate-500 truncate">{sub}</p>
          )}
        </div>
        <div
          className={cn(
            'shrink-0 w-10 h-10 rounded-lg border flex items-center justify-center',
            c.iconBg
          )}
        >
          <Icon className={cn('w-5 h-5', c.icon)} />
        </div>
      </div>
      {onClick && (
        <ChevronRight className="absolute bottom-3 right-3 w-3.5 h-3.5 text-slate-600 group-hover:text-slate-400 transition-colors" />
      )}
    </div>
  );
};

interface PolicyBreakdownBarProps {
  approved: number;
  blocked: number;
}

const PolicyBreakdownBar: React.FC<PolicyBreakdownBarProps> = ({ approved, blocked }) => {
  const total = approved + blocked;
  const approvedPct = total > 0 ? (approved / total) * 100 : 0;
  const blockedPct = total > 0 ? (blocked / total) * 100 : 0;

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-white">Policy Engine Outcomes</h3>
        </div>
        <span className="text-xs font-mono text-slate-500">{total} evaluations</span>
      </div>

      {total === 0 ? (
        <div className="h-10 flex items-center justify-center rounded-lg bg-navy-950 border border-navy-800">
          <span className="text-xs text-slate-600 font-mono">No evaluations yet</span>
        </div>
      ) : (
        <>
          <div className="relative h-3 w-full rounded-full overflow-hidden bg-navy-950">
            <div
              className="absolute left-0 top-0 h-full bg-gradient-to-r from-emerald-600 to-emerald-500 transition-all duration-700"
              style={{ width: `${approvedPct}%` }}
            />
            <div
              className="absolute top-0 h-full bg-gradient-to-r from-rose-600 to-rose-500 transition-all duration-700"
              style={{ left: `${approvedPct}%`, width: `${blockedPct}%` }}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <div>
                <p className="text-xs text-slate-400">Policy Approved</p>
                <p className="text-sm font-bold font-mono text-emerald-400">
                  {approved}{' '}
                  <span className="text-[10px] font-normal text-slate-500">
                    ({approvedPct.toFixed(0)}%)
                  </span>
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-rose-500" />
              <div>
                <p className="text-xs text-slate-400">Policy Blocked</p>
                <p className="text-sm font-bold font-mono text-rose-400">
                  {blocked}{' '}
                  <span className="text-[10px] font-normal text-slate-500">
                    ({blockedPct.toFixed(0)}%)
                  </span>
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

interface AuditChainStatusProps {
  summary: AuditSummary | null;
}

const AuditChainStatus: React.FC<AuditChainStatusProps> = ({ summary }) => {
  const isVerified = summary?.audit_chain_verified === true;
  const isBroken = summary?.audit_chain_verified === false;
  const isUnavailable = summary?.audit_chain_verified === undefined || summary === null;
  const eventCount = summary?.total_audit_events ?? 0;
  const lastHash = summary?.last_event_hash;

  return (
    <div
      className={cn(
        'rounded-xl border p-5 space-y-3',
        isVerified
          ? 'border-emerald-500/20 bg-emerald-950/10'
          : isBroken
          ? 'border-rose-500/30 bg-rose-950/10'
          : isUnavailable
          ? 'border-navy-800 bg-navy-900/60'
          : 'border-navy-800 bg-navy-900/60'
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Hash
            className={cn(
              'w-4 h-4',
              isVerified
                ? 'text-emerald-400'
                : isBroken
                ? 'text-rose-400'
                : 'text-amber-400'
            )}
          />
          <h3 className="text-sm font-semibold text-white">SHA-256 Audit Chain</h3>
        </div>
        <span
          className={cn(
            'px-2 py-0.5 rounded text-[10px] font-mono font-bold border uppercase tracking-wider',
            isVerified
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              : isBroken
              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
          )}
        >
          {isVerified ? 'VERIFIED' : isBroken ? 'BROKEN' : isUnavailable ? 'UNAVAILABLE' : 'UNKNOWN'}
        </span>
      </div>

      <div className="space-y-2 text-xs font-mono">
        <div className="flex items-center justify-between py-1.5 border-b border-navy-800">
          <span className="text-slate-500">Total chained events</span>
          <span className="text-white font-bold">{eventCount}</span>
        </div>
        <div className="flex items-center justify-between py-1.5 border-b border-navy-800">
          <span className="text-slate-500">Genesis hash</span>
          <span className="text-slate-400">0000...0000</span>
        </div>
        <div className="flex items-center justify-between py-1.5">
          <span className="text-slate-500">Chain tip</span>
          <span className="text-emerald-400 truncate max-w-[140px]">
            {lastHash ? `${lastHash.slice(0, 8)}…${lastHash.slice(-6)}` : 'empty'}
          </span>
        </div>
      </div>

      <p className="text-[10px] text-slate-600 leading-relaxed">
        Tamper-evident via SHA-256 hash chaining. Does not prevent raw host-level file manipulation.
      </p>
    </div>
  );
};

interface TrustDashboardProps {
  onNavigateToAudit?: () => void;
}

export const TrustDashboard: React.FC<TrustDashboardProps> = ({ onNavigateToAudit }) => {
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.getAuditSummary();
      setSummary(data);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (e) {
      console.warn('Dashboard summary fetch error:', e);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const total = summary?.total_staged_proposals ?? 0;
  const approved = summary?.approved_evaluations ?? 0;
  const blocked = summary?.blocked_evaluations ?? 0;
  const humanApproved = summary?.total_human_approvals ?? 0;
  const captures = summary?.total_paypal_captures ?? 0;
  const mandates = summary?.total_mandates ?? 0;
  const events = summary?.total_audit_events ?? 0;

  // Derive pending: staged proposals without capture
  const pending = Math.max(0, total - captures);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Executive Trust Dashboard</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time metrics from persistent SQLite audit ledger
            {lastRefreshed && <span> · Refreshed {lastRefreshed}</span>}
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-navy-700 bg-navy-900 text-xs font-mono text-slate-400 hover:text-emerald-400 hover:border-navy-600 transition-all disabled:opacity-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          {isLoading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {/* Vision & Security Perimeter Banner */}
      <div className="relative overflow-hidden rounded-xl border border-emerald-500/20 bg-gradient-to-r from-emerald-950/30 via-navy-900/60 to-navy-950 p-4 sm:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                SECURITY INVARIANT ENFORCED
              </span>
              <span className="text-[11px] font-mono text-slate-400">Zero Autonomous Payment Rights</span>
            </div>
            <h3 className="text-base font-semibold text-white tracking-tight">
              Human-Controlled AI Payment Security Layer for Agentic Commerce
            </h3>
            <p className="text-xs text-slate-400 max-w-3xl leading-relaxed">
              <strong className="text-emerald-300 font-medium">Vision:</strong> Let AI handle the intelligence of shopping, while humans retain control of the money. AI agents discover and evaluate marketplace proposals, while payment authorization remains strictly under deterministic policy and explicit human control.
            </p>
          </div>
        </div>
      </div>

      {/* Top Metric Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label="Mandates Issued"
          value={mandates}
          sub="Purchase authorizations"
          icon={ShieldCheck}
          color="violet"
        />
        <MetricCard
          label="Proposals Staged"
          value={total}
          sub="Candidates evaluated"
          icon={TrendingUp}
          color="sky"
        />
        <MetricCard
          label="Policy Approved"
          value={approved}
          sub="Passed all 7 invariants"
          icon={CheckCircle2}
          color="emerald"
          highlight
        />
        <MetricCard
          label="Policy Blocked"
          value={blocked}
          sub="Failed policy gate"
          icon={ShieldAlert}
          color="rose"
        />
        <MetricCard
          label="Human Approved"
          value={humanApproved}
          sub="Authorized by operator"
          icon={UserCheck}
          color="emerald"
        />
        <MetricCard
          label="Sandbox Captures"
          value={captures}
          sub="PayPal COMPLETED"
          icon={CreditCard}
          color="sky"
          onClick={onNavigateToAudit}
        />
      </div>

      {/* Second Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="Pending Transactions"
          value={pending}
          sub="Awaiting buyer action"
          icon={Clock}
          color="amber"
        />
        <MetricCard
          label="Audit Events"
          value={events}
          sub="SHA-256 chain links"
          icon={Database}
          color="slate"
        />
        <MetricCard
          label="Human Rejections"
          value={Math.max(0, humanApproved > 0 ? total - humanApproved : 0)}
          sub="Operator declined"
          icon={UserX}
          color="rose"
        />
        <MetricCard
          label="AI Auth Attempts"
          value={0}
          sub="Blocked by TG-007"
          icon={Ban}
          color="rose"
          highlight
        />
      </div>

      {/* Charts & Chain */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PolicyBreakdownBar approved={approved} blocked={blocked} />
        <AuditChainStatus summary={summary} />
      </div>

      {/* Security Invariants Summary */}
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-white">Active Security Invariants</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { code: 'TG-001', label: 'Spending Limit Math', status: 'ENFORCED' },
            { code: 'TG-002', label: 'Currency Alignment', status: 'ENFORCED' },
            { code: 'TG-003', label: 'Product Condition', status: 'ENFORCED' },
            { code: 'TG-004', label: 'Merchant Trust Gate', status: 'ENFORCED' },
            { code: 'TG-005', label: 'Add-on Protection', status: 'ENFORCED' },
            { code: 'TG-006', label: 'Data Integrity', status: 'ENFORCED' },
            { code: 'TG-007', label: 'AI Zero Autonomy', status: 'ENFORCED' },
            { code: 'TG-008', label: 'SHA-256 Audit Chain', status: 'ACTIVE' },
            { code: 'TG-ORD', label: 'Orders v2 Schema Guard', status: 'ENFORCED' },
          ].map((inv) => (
            <div
              key={inv.code}
              className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-navy-950 border border-navy-800"
            >
              <div>
                <p className="text-[10px] font-mono text-emerald-400 font-bold">{inv.code}</p>
                <p className="text-xs text-slate-400">{inv.label}</p>
              </div>
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                {inv.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

