import React, { useEffect, useState, useCallback } from 'react';
import {
  Cpu,
  Lock,
  CreditCard,
  Sliders,
  MessageSquare,
  ArrowRight,
  CheckCircle2,
  Database,
  UserCheck,
  Compass,
  Receipt,
  ShieldCheck,
  AlertTriangle,
  Clock,
} from 'lucide-react';
import { Sidebar, NavigationSection } from '../components/Sidebar';
import { TopNavbar } from '../components/TopNavbar';
import { StatusCard } from '../components/StatusCard';
import { TrustDashboard } from '../components/TrustDashboard';
import { AgenticProposalFlow } from '../components/AgenticProposalFlow';
import { DescribeYourPurchase } from '../components/DescribeYourPurchase';
import { TrustGatePolicySimulator } from '../components/TrustGatePolicySimulator';
import { ApprovalCenter } from '../components/ApprovalCenter';
import { IntelligenceTable } from '../components/IntelligenceTable';
import { ForensicDetail } from '../components/ForensicDetail';
import { TransactionTimeline } from '../components/TransactionTimeline';
import { AuditLog } from '../components/AuditLog';
import { SettingsView } from '../components/SettingsView';
import { api } from '../lib/api';
import {
  SystemHealth,
  AuditLogItem,
  PurchaseMandate,
  AuditSummaryResponse,
  AuditIntegrityResponse,
  TransactionSummaryItem,
  StageProposalResponse,
} from '../types';
import { formatCurrency, cn } from '../lib/utils';

export const Dashboard: React.FC = () => {
  const [activeSection, setActiveSection] = useState<NavigationSection>('dashboard');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [confirmedMandate, setConfirmedMandate] = useState<PurchaseMandate | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Proposals sub-tab (Composer vs Policy Simulator)
  const [proposalsSubTab, setProposalsSubTab] = useState<'composer' | 'simulator'>('composer');

  // Forensic drill-down modal in Transactions / Dashboard
  const [forensicTxId, setForensicTxId] = useState<string | null>(null);

  // Active Transaction ID in Audit Trail
  const [auditSelectedTxId, setAuditSelectedTxId] = useState<string | null>(null);

  // Telemetry & metrics state
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [isLoadingHealth, setIsLoadingHealth] = useState(false);
  const [auditSummary, setAuditSummary] = useState<AuditSummaryResponse | null>(null);
  const [auditIntegrity, setAuditIntegrity] = useState<AuditIntegrityResponse | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [recentTransactions, setRecentTransactions] = useState<TransactionSummaryItem[]>([]);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number>(0);

  const fetchTelemetry = useCallback(async () => {
    setIsLoadingHealth(true);
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch (e) {
      console.warn('Health fetch error:', e);
    } finally {
      setIsLoadingHealth(false);
    }

    try {
      const sum = await api.getAuditSummary();
      setAuditSummary(sum);
    } catch (e) {
      console.warn('Audit summary fetch error:', e);
    }

    try {
      const integrity = await api.checkAuditIntegrity();
      setAuditIntegrity(integrity);
    } catch (e) {
      console.warn('Audit integrity check error:', e);
      setAuditIntegrity(null);
    }

    try {
      const txRes = await api.getPersistedTransactions(20);
      const txs = txRes.transactions || [];
      setRecentTransactions(txs);
      const pending = txs.filter((t: any) => t.status === 'STAGED').length;
      setPendingApprovalsCount(pending);
    } catch (e) {
      console.warn('Transactions fetch error:', e);
    }

    try {
      setIsLoadingLogs(true);
      const res = await api.getAuditLogs();
      setAuditLogs(res.logs || []);
    } catch (e) {
      console.warn('Audit logs fetch error:', e);
    } finally {
      setIsLoadingLogs(false);
    }
  }, []);

  useEffect(() => {
    fetchTelemetry();
  }, [fetchTelemetry]);

  // Handler when user confirms mandate in Describe Your Purchase
  const handleConfirmMandate = (mandate: PurchaseMandate) => {
    setConfirmedMandate(mandate);
    setActiveSection('discover');
    setToastMessage(
      `Purchase mandate confirmed (${mandate.currency} ${mandate.max_amount.toFixed(
        2
      )}) and loaded into Product Discovery!`
    );
    setTimeout(() => setToastMessage(null), 6000);
  };

  // Handler when candidate proposal is staged from Product Discovery
  const handleProposalStaged = (staged: StageProposalResponse) => {
    setPendingApprovalsCount((prev) => prev + 1);
    setToastMessage(
      `Proposal for "${staged.product_name}" staged for human sign-off! Navigate to Approval Center to authorize.`
    );
    fetchTelemetry();
    setTimeout(() => setToastMessage(null), 8000);
  };

  return (
    <div className="min-h-screen bg-navy-950 text-slate-100 flex font-sans">
      {/* Permanent Left Sidebar (Desktop) + Mobile Drawer */}
      <Sidebar
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        pendingApprovalsCount={pendingApprovalsCount}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main App Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto min-h-screen">
        {/* Top Navigation Bar */}
        <TopNavbar
          currentSection={activeSection}
          health={health}
          isLoadingHealth={isLoadingHealth}
          onRefreshHealth={fetchTelemetry}
          onOpenMobileMenu={() => setIsMobileSidebarOpen(true)}
        />

        {/* View Container */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl w-full mx-auto">
          {/* Toast Notification Banner */}
          {toastMessage && (
            <div className="p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-500/40 text-xs font-mono text-emerald-300 flex items-center justify-between shadow-emerald-glow animate-in fade-in duration-300">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{toastMessage}</span>
              </div>
              <div className="flex items-center gap-2">
                {activeSection !== 'approvals' && (
                  <button
                    type="button"
                    onClick={() => setActiveSection('approvals')}
                    className="px-2.5 py-1 rounded bg-emerald-500 text-navy-950 font-bold hover:bg-emerald-400 transition-colors"
                  >
                    Go to Approvals
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setToastMessage(null)}
                  className="text-slate-400 hover:text-white px-1 text-sm"
                >
                  ×
                </button>
              </div>
            </div>
          )}

          {/* ============================================================= */}
          {/* 1. DASHBOARD VIEW                                             */}
          {/* ============================================================= */}
          {activeSection === 'dashboard' && (
            <div className="space-y-6">
              {/* Security Perimeter Hero Card */}
              <div className="relative overflow-hidden rounded-2xl border border-navy-800 bg-gradient-to-r from-navy-900 via-navy-900/90 to-emerald-950/30 p-6 sm:p-7 shadow-card-glow">
                <div className="relative z-10 max-w-3xl space-y-2">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span>Dual-Layer Security Perimeter & SQLite ACID Ledger Active</span>
                  </div>
                  <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
                    PayPal TrustGate Agentic Commerce Guard
                  </h2>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    TrustGate bridges autonomous AI product discovery with deterministic policy
                    enforcement and mandatory human approval. The AI agent operates with{' '}
                    <strong className="text-emerald-400">zero payment authorization rights</strong>.
                    Every transaction is validated against TG-001–TG-007 invariants and logged to an
                    immutable SHA-256 chained audit trail before PayPal Sandbox checkout handoff.
                  </p>
                </div>
                <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-emerald-500/5 to-transparent pointer-events-none hidden md:block" />
              </div>

              {/* 4 Core Status Metric Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatusCard
                  title="AI Payment Privilege"
                  value="ZERO AUTH"
                  subtitle="Barred from authorization / charge APIs"
                  icon={Lock}
                  badgeText="Enforced"
                  badgeType="success"
                  highlight={true}
                />
                <StatusCard
                  title="Groq Intent Interpreter"
                  value={health?.integrations.grok_ai.configured ? 'GROQ ONLINE' : 'STANDBY'}
                  subtitle={health?.integrations.grok_ai.model || 'openai/gpt-oss-120b'}
                  icon={Cpu}
                  badgeText={health?.integrations.grok_ai.configured ? 'Configured' : 'Active'}
                  badgeType={health?.integrations.grok_ai.configured ? 'info' : 'warning'}
                />
                <StatusCard
                  title="Policy Engine & Ledger"
                  value={`${auditSummary?.total_audit_events ?? auditLogs.length} EVENTS`}
                  subtitle="SQLite Persistent • SHA-256 Chained"
                  icon={Database}
                  badgeText="ACID Trail"
                  badgeType="success"
                />
                <StatusCard
                  title="PayPal Gateway"
                  value="SANDBOX"
                  subtitle="Orders v2 (Staged - No Auto-Execution)"
                  icon={CreditCard}
                  badgeText="Safe Hold"
                  badgeType="warning"
                />
              </div>

              {/* Executive Trust Metrics (Aggregated backend metrics) */}
              <div className="rounded-2xl border border-navy-800 bg-navy-900/40 p-1">
                <div className="px-5 py-3 border-b border-navy-800/80 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-bold text-white">Executive Trust & Policy Telemetry</h3>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">
                    Live data from /api/v1/audit/summary
                  </span>
                </div>
                <div className="p-4">
                  <TrustDashboard />
                </div>
              </div>

              {/* Recent Transaction Activity Section */}
              <div className="rounded-2xl border border-navy-800 bg-navy-900/70 shadow-card-glow p-5 sm:p-6 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-navy-800">
                  <div className="flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-bold text-white">Recent Transaction Ledger Activity</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveSection('transactions')}
                    className="text-xs font-mono text-emerald-400 hover:text-emerald-300 transition-colors flex items-center gap-1"
                  >
                    <span>View Full Ledger</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {recentTransactions.length === 0 ? (
                  <div className="py-8 text-center text-xs font-mono text-slate-500">
                    No transactions recorded in the persistent ledger yet. Stage a proposal to begin.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {recentTransactions.slice(0, 5).map((tx) => (
                      <div
                        key={tx.transaction_id}
                        className="p-3 rounded-xl bg-navy-950 border border-navy-850 flex items-center justify-between text-xs font-mono gap-3 hover:border-navy-750 transition-colors"
                      >
                        <div className="flex items-center gap-3 truncate min-w-0">
                          <span
                            className={cn(
                              'px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider shrink-0',
                              tx.status === 'STAGED'
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                                : tx.status === 'HUMAN_APPROVED' || tx.status === 'CAPTURED'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                                  : 'bg-slate-500/10 text-slate-400 border-slate-500/30'
                            )}
                          >
                            {tx.status}
                          </span>
                          <span className="font-bold text-slate-200 truncate">{tx.product_name}</span>
                          <span className="text-slate-500 hidden md:inline truncate">•</span>
                          <span className="text-slate-400 hidden md:inline truncate">
                            {tx.merchant_name || 'Retailer'}
                          </span>
                        </div>

                        <div className="flex items-center gap-3 shrink-0">
                          <span className="font-extrabold text-emerald-400">
                            {formatCurrency(tx.amount, tx.currency)}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              if (tx.status === 'STAGED') {
                                setActiveSection('approvals');
                              } else {
                                setForensicTxId(tx.transaction_id);
                              }
                            }}
                            className="px-2.5 py-1 rounded bg-navy-900 hover:bg-navy-800 text-[11px] text-slate-300 hover:text-white border border-navy-800 transition-colors"
                          >
                            {tx.status === 'STAGED' ? 'Review Sign-off' : 'Inspect'}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Quick Navigation Action Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <button
                  type="button"
                  onClick={() => setActiveSection('discover')}
                  className="p-4 rounded-xl border border-navy-800 bg-navy-900/60 hover:border-emerald-500/40 hover:bg-navy-900 transition-all text-left space-y-2 group"
                >
                  <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 w-fit group-hover:scale-105 transition-transform">
                    <Compass className="w-4 h-4" />
                  </div>
                  <h4 className="text-sm font-bold text-white flex items-center justify-between">
                    <span>Discover Products</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-400 group-hover:translate-x-1 transition-all" />
                  </h4>
                  <p className="text-xs text-slate-400 leading-snug">
                    Query the Channel3 Universal Product Graph (100M+ items) and Amazon Creators API.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveSection('approvals')}
                  className="p-4 rounded-xl border border-navy-800 bg-navy-900/60 hover:border-amber-500/40 hover:bg-navy-900 transition-all text-left space-y-2 group"
                >
                  <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 w-fit group-hover:scale-105 transition-transform">
                    <UserCheck className="w-4 h-4" />
                  </div>
                  <h4 className="text-sm font-bold text-white flex items-center justify-between">
                    <span>Human Approval Center</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-amber-400 group-hover:translate-x-1 transition-all" />
                  </h4>
                  <p className="text-xs text-slate-400 leading-snug">
                    Explicitly authorize pending proposals. Review budget caps and cryptographic signatures.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveSection('audit')}
                  className="p-4 rounded-xl border border-navy-800 bg-navy-900/60 hover:border-emerald-500/40 hover:bg-navy-900 transition-all text-left space-y-2 group"
                >
                  <div className="p-2 rounded-lg bg-navy-800 text-slate-300 w-fit group-hover:scale-105 transition-transform">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <h4 className="text-sm font-bold text-white flex items-center justify-between">
                    <span>Audit Trail Ledger</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-400 group-hover:translate-x-1 transition-all" />
                  </h4>
                  <p className="text-xs text-slate-400 leading-snug">
                    Inspect the unbroken SHA-256 hash chain and mathematical tamper-evidence guarantees.
                  </p>
                </button>
              </div>
            </div>
          )}

          {/* ============================================================= */}
          {/* 2. DISCOVER PRODUCTS VIEW                                     */}
          {/* ============================================================= */}
          {activeSection === 'discover' && (
            <div className="space-y-6">
              <AgenticProposalFlow
                mandate={confirmedMandate}
                onSelectMandateTab={() => {
                  setActiveSection('proposals');
                  setProposalsSubTab('composer');
                }}
                onProposalStaged={handleProposalStaged}
                onNavigateToApprovals={() => setActiveSection('approvals')}
                onViewAuditTimeline={(txId) => {
                  setAuditSelectedTxId(txId);
                  setActiveSection('audit');
                }}
              />
            </div>
          )}

          {/* ============================================================= */}
          {/* 3. PURCHASE PROPOSALS & POLICIES VIEW                         */}
          {/* ============================================================= */}
          {activeSection === 'proposals' && (
            <div className="space-y-6">
              {/* Proposals Sub-Tabs */}
              <div className="flex items-center gap-3 border-b border-navy-800 pb-3">
                <button
                  type="button"
                  onClick={() => setProposalsSubTab('composer')}
                  className={cn(
                    'px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2',
                    proposalsSubTab === 'composer'
                      ? 'bg-emerald-500 text-navy-950 shadow-emerald-glow'
                      : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
                  )}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span>1. AI Mandate Composer (Groq)</span>
                  {confirmedMandate && (
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setProposalsSubTab('simulator')}
                  className={cn(
                    'px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2',
                    proposalsSubTab === 'simulator'
                      ? 'bg-emerald-500 text-navy-950 shadow-emerald-glow'
                      : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
                  )}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>2. TG-001–TG-007 Policy Simulator</span>
                </button>
              </div>

              {proposalsSubTab === 'composer' && (
                <div className="space-y-4">
                  <DescribeYourPurchase onConfirmMandate={handleConfirmMandate} />
                </div>
              )}

              {proposalsSubTab === 'simulator' && (
                <div className="space-y-4">
                  <TrustGatePolicySimulator initialMandate={confirmedMandate} />
                </div>
              )}
            </div>
          )}

          {/* ============================================================= */}
          {/* 4. HUMAN APPROVAL CENTER VIEW                                 */}
          {/* ============================================================= */}
          {activeSection === 'approvals' && (
            <div className="space-y-6">
              <ApprovalCenter
                onRefreshSummary={fetchTelemetry}
                onNavigateToAudit={(txId) => {
                  setAuditSelectedTxId(txId || null);
                  setActiveSection('audit');
                }}
              />
            </div>
          )}

          {/* ============================================================= */}
          {/* 5. TRANSACTIONS VIEW                                          */}
          {/* ============================================================= */}
          {activeSection === 'transactions' && (
            <div className="space-y-6">
              {forensicTxId ? (
                <div className="space-y-4">
                  <button
                    type="button"
                    onClick={() => setForensicTxId(null)}
                    className="px-3 py-1.5 rounded-lg bg-navy-900 border border-navy-800 text-xs font-mono text-slate-300 hover:text-white flex items-center gap-1.5"
                  >
                    <span>← Back to Transaction Intelligence Table</span>
                  </button>
                  <ForensicDetail
                    transactionId={forensicTxId}
                    onClose={() => setForensicTxId(null)}
                  />
                </div>
              ) : (
                <IntelligenceTable onSelectTransaction={(txId) => setForensicTxId(txId)} />
              )}
            </div>
          )}

          {/* ============================================================= */}
          {/* 6. AUDIT TRAIL VIEW                                           */}
          {/* ============================================================= */}
          {activeSection === 'audit' && (
            <div className="space-y-6">
              {/* Cryptographic Hash-Chain Verification Banner */}
              {(() => {
                const isVerified =
                  auditIntegrity?.is_valid ?? auditSummary?.audit_chain_verified;
                const isConfirmed = isVerified === true;
                const isFailed = isVerified === false;

                return (
                  <div
                    className={cn(
                      'rounded-xl border bg-navy-900/90 p-5 space-y-3',
                      isConfirmed
                        ? 'border-emerald-500/30'
                        : isFailed
                        ? 'border-rose-500/40 bg-rose-950/10'
                        : 'border-navy-800'
                    )}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-navy-800">
                      <div className="flex items-center gap-2.5">
                        <ShieldCheck
                          className={cn(
                            'w-5 h-5',
                            isConfirmed
                              ? 'text-emerald-400'
                              : isFailed
                              ? 'text-rose-400'
                              : 'text-amber-400'
                          )}
                        />
                        <div>
                          <h3 className="text-sm font-bold text-white">
                            Cryptographic Hash-Chain Integrity Status
                          </h3>
                          <p className="text-[11px] font-mono text-slate-400">
                            {isConfirmed
                              ? auditIntegrity?.tamper_evident_guarantee ||
                                'SHA-256 deterministic hash chaining • SQLite engine trigger protection'
                              : isFailed
                              ? `TAMPER WARNING: ${
                                  auditIntegrity?.failure_reason ||
                                  'Cryptographic hash mismatch or broken sequence detected in ledger.'
                                }`
                              : 'SHA-256 deterministic hash chain telemetry pending from backend.'}
                          </p>
                        </div>
                      </div>

                      {isConfirmed ? (
                        <span className="px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-xs font-mono font-bold flex items-center gap-1.5 self-start">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>CHAIN VERIFIED (UNBROKEN)</span>
                        </span>
                      ) : isFailed ? (
                        <span className="px-2.5 py-1 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 text-xs font-mono font-bold flex items-center gap-1.5 self-start">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>TAMPER DETECTED (INVALID)</span>
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-xs font-mono font-bold flex items-center gap-1.5 self-start">
                          <Clock className="w-3.5 h-3.5" />
                          <span>VERIFICATION UNAVAILABLE</span>
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                      <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 space-y-1">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Genesis Hash</span>
                        <div className="text-[11px] text-slate-300 truncate">
                          {auditIntegrity?.genesis_hash ||
                            auditSummary?.genesis_hash ||
                            'Genesis Hash Unavailable'}
                        </div>
                      </div>

                      <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 space-y-1">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Latest Head Event Hash</span>
                        <div
                          className={cn(
                            'text-[11px] truncate',
                            isConfirmed
                              ? 'text-emerald-400'
                              : isFailed
                              ? 'text-rose-400 font-bold'
                              : 'text-slate-400'
                          )}
                        >
                          {auditIntegrity?.last_event_hash ||
                            auditSummary?.last_event_hash ||
                            'No events recorded / Chain head unavailable'}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Transaction Lifecycle Timeline */}
              <TransactionTimeline
                activeTransactionId={auditSelectedTxId}
                onSelectTransaction={(txId) => setAuditSelectedTxId(txId)}
              />

              {/* Canonical Immutable Audit Ledger & Event Stream */}
              <AuditLog
                logs={auditLogs}
                onRefresh={fetchTelemetry}
                isLoading={isLoadingLogs}
                onOpenTimeline={(txId) => {
                  if (txId) {
                    setAuditSelectedTxId(txId);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }
                }}
                selectedTransactionId={auditSelectedTxId}
              />
            </div>
          )}

          {/* ============================================================= */}
          {/* 7. SETTINGS & DIAGNOSTICS VIEW                                */}
          {/* ============================================================= */}
          {activeSection === 'settings' && (
            <SettingsView health={health} onRefreshHealth={fetchTelemetry} />
          )}
        </main>
      </div>

      {/* Forensic Drilldown Modal from Dashboard */}
      {forensicTxId && activeSection === 'dashboard' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-navy-700 bg-navy-900 p-6 shadow-2xl">
            <ForensicDetail
              transactionId={forensicTxId}
              onClose={() => setForensicTxId(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
};
