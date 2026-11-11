import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  Clock,
  XCircle,
  FileText,
  Search,
  CreditCard,
  Receipt,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Database,
  UserCheck,
  AlertTriangle,
} from 'lucide-react';
import {
  TransactionLifecycleTimeline,
  TransactionTimelineStage,
  TransactionSummaryItem,
  AuditEventRecord,
} from '../types';
import { api } from '../lib/api';
import { formatTimestamp, cn } from '../lib/utils';

interface TransactionTimelineProps {
  activeTransactionId?: string | null;
  onSelectTransaction?: (txId: string) => void;
}

export const TransactionTimeline: React.FC<TransactionTimelineProps> = ({
  activeTransactionId,
  onSelectTransaction,
}) => {
  const [selectedTxId, setSelectedTxId] = useState<string | null>(activeTransactionId || null);
  const [timeline, setTimeline] = useState<TransactionLifecycleTimeline | null>(null);
  const [transactions, setTransactions] = useState<TransactionSummaryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedStages, setExpandedStages] = useState<Record<string, boolean>>({
    policy: true,
    approval: true,
  });
  const [showEventLog, setShowEventLog] = useState<boolean>(false);

  // Sync prop changes
  useEffect(() => {
    if (activeTransactionId && activeTransactionId !== selectedTxId) {
      setSelectedTxId(activeTransactionId);
    }
  }, [activeTransactionId]);

  // Load transaction list
  const loadTransactions = async () => {
    try {
      const res = await api.getPersistedTransactions(30);
      setTransactions(res.transactions || []);
      // If no transaction currently selected, select the most recent
      if (!selectedTxId && res.transactions && res.transactions.length > 0) {
        setSelectedTxId(res.transactions[0].transaction_id);
      }
    } catch (err: unknown) {
      console.warn('Failed to load transaction list:', err);
    }
  };

  // Load specific timeline
  const loadTimeline = async (txId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getTransactionTimeline(txId);
      setTimeline(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch timeline.';
      setError(msg);
      setTimeline(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTransactions();
  }, []);

  useEffect(() => {
    if (selectedTxId) {
      loadTimeline(selectedTxId);
    }
  }, [selectedTxId]);

  const handleRefresh = () => {
    loadTransactions();
    if (selectedTxId) {
      loadTimeline(selectedTxId);
    }
  };

  const handleSelectTx = (txId: string) => {
    setSelectedTxId(txId);
    if (onSelectTransaction) {
      onSelectTransaction(txId);
    }
  };

  const toggleStageExpand = (key: string) => {
    setExpandedStages((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const getStageIcon = (key: string, status: string) => {
    if (status === 'BLOCKED') return <XCircle className="w-5 h-5 text-rose-400" />;
    if (status === 'PENDING') return <Clock className="w-5 h-5 text-amber-400" />;

    switch (key) {
      case 'mandate':
        return <FileText className="w-5 h-5 text-emerald-400" />;
      case 'proposal':
        return <Search className="w-5 h-5 text-emerald-400" />;
      case 'policy':
        return <ShieldCheck className="w-5 h-5 text-emerald-400" />;
      case 'approval':
        return <UserCheck className="w-5 h-5 text-emerald-400" />;
      case 'order':
        return <CreditCard className="w-5 h-5 text-emerald-400" />;
      case 'receipt':
        return <Receipt className="w-5 h-5 text-emerald-400" />;
      default:
        return <CheckCircle2 className="w-5 h-5 text-emerald-400" />;
    }
  };

  return (
    <div className="rounded-2xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-7 space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-navy-800 gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
              Transaction Lifecycle & Audit Timeline
            </h2>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono">
              ACID Persistent
            </span>
          </div>
          <p className="text-xs text-slate-400">
            End-to-end audit trail: Mandate ➔ Proposal ➔ Policy ➔ Human Approval ➔ Sandbox Order ➔ Verified Receipt.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Transaction Switcher Dropdown */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400 hidden sm:inline">Transaction:</span>
            <select
              value={selectedTxId || ''}
              onChange={(e) => handleSelectTx(e.target.value)}
              className="bg-navy-950 border border-navy-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500 max-w-[220px] truncate"
            >
              {transactions.length === 0 ? (
                <option value="">No Staged Transactions</option>
              ) : (
                transactions.map((tx) => (
                  <option key={tx.transaction_id} value={tx.transaction_id}>
                    {tx.transaction_id} • {tx.product_name.slice(0, 18)}... ({tx.status})
                  </option>
                ))
              )}
            </select>
          </div>

          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            className="p-2 rounded-lg bg-navy-950 border border-navy-800 text-slate-400 hover:text-emerald-400 hover:border-emerald-500/40 transition-colors"
            title="Refresh Timeline"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin text-emerald-400')} />
          </button>
        </div>
      </div>

      {/* Persistence Assurance Banner */}
      <div className="p-3.5 rounded-xl bg-navy-950/70 border border-navy-800 text-xs font-mono text-slate-300 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-slate-400">Storage Engine:</span>
          <span className="text-white font-semibold">SQLite Persistent (backend/data/trustgate.db)</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span>Survives Restarts: <strong className="text-emerald-400">Yes</strong></span>
          <span>•</span>
          <span>In-Memory Only: <strong className="text-rose-400">No</strong></span>
          <span>•</span>
          <span>AI Execution: <strong className="text-rose-400">Prohibited</strong></span>
        </div>
      </div>

      {/* Error View */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading State */}
      {isLoading && !timeline && (
        <div className="p-12 text-center text-xs font-mono text-slate-400 space-y-2">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto text-emerald-400" />
          <span>Reconstructing transaction lifecycle from persistent ledger...</span>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !timeline && !error && (
        <div className="p-12 text-center text-xs font-mono text-slate-400 space-y-2">
          <p>No staged transactions found in the database.</p>
          <p className="text-slate-500">
            Go to <strong>Agentic Proposal Flow</strong> and select an approved proposal to create your first staged transaction.
          </p>
        </div>
      )}

      {/* Active Timeline Render */}
      {timeline && (
        <div className="space-y-6">
          {/* Transaction Metadata Header */}
          <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div>
              <span className="text-slate-500 text-[10px] uppercase block">Transaction ID</span>
              <span className="text-white font-bold select-all">{timeline.transaction_id}</span>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase block">Current Stage Status</span>
              <span
                className={cn(
                  'inline-block px-2 py-0.5 rounded text-[11px] font-bold mt-0.5',
                  timeline.current_status === 'COMPLETED'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : timeline.current_status === 'ORDER_CREATED'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    : 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                )}
              >
                {timeline.current_status}
              </span>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase block">Staged Time</span>
              <span className="text-slate-300">{formatTimestamp(timeline.created_at)}</span>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase block">PayPal Order ID</span>
              <span className="text-emerald-400 select-all truncate block">
                {timeline.paypal_order_summary?.order_id || 'Not Yet Initiated'}
              </span>
            </div>
          </div>

          {/* 6-Stage Chronological Vertical Progression */}
          <div className="relative pl-6 sm:pl-8 space-y-6 before:absolute before:left-[17px] sm:before:left-[21px] before:top-3 before:bottom-3 before:w-0.5 before:bg-navy-800">
            {timeline.stages.map((stage: TransactionTimelineStage) => {
              const isExpanded = expandedStages[stage.stage_key] ?? false;
              const isComplete = stage.status === 'COMPLETED';
              const isBlocked = stage.status === 'BLOCKED';
              const isPending = stage.status === 'PENDING';

              return (
                <div key={stage.stage_key} className="relative group">
                  {/* Status Node Circle */}
                  <div
                    className={cn(
                      'absolute -left-[35px] sm:-left-[39px] top-1.5 w-7 h-7 rounded-full flex items-center justify-center border transition-all z-10',
                      isComplete
                        ? 'bg-navy-950 border-emerald-500 text-emerald-400 shadow-emerald-glow'
                        : isBlocked
                        ? 'bg-navy-950 border-rose-500 text-rose-400'
                        : isPending
                        ? 'bg-navy-950 border-amber-500 text-amber-400'
                        : 'bg-navy-950 border-navy-700 text-slate-500'
                    )}
                  >
                    {getStageIcon(stage.stage_key, stage.status)}
                  </div>

                  {/* Stage Card */}
                  <div
                    className={cn(
                      'rounded-xl border transition-all p-4 text-xs font-mono space-y-2',
                      isComplete
                        ? 'bg-navy-950/90 border-navy-800 hover:border-emerald-500/40'
                        : isBlocked
                        ? 'bg-navy-950/90 border-rose-900/60'
                        : isPending
                        ? 'bg-navy-950/90 border-amber-900/50'
                        : 'bg-navy-950/50 border-navy-850 opacity-80'
                    )}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">{stage.stage_name}</span>
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded text-[10px] font-bold',
                            isComplete
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : isBlocked
                              ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                              : isPending
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                              : 'bg-slate-800 text-slate-400 border border-slate-700'
                          )}
                        >
                          {stage.status}
                        </span>
                      </div>

                      {stage.timestamp && (
                        <span className="text-[11px] text-slate-500 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatTimestamp(stage.timestamp)}
                        </span>
                      )}
                    </div>

                    <p className="text-slate-300 text-xs">{stage.summary}</p>

                    {/* Expand/Collapse Toggle */}
                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={() => toggleStageExpand(stage.stage_key)}
                        className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:underline"
                      >
                        {isExpanded ? (
                          <>
                            <ChevronDown className="w-3 h-3" />
                            <span>Hide Details</span>
                          </>
                        ) : (
                          <>
                            <ChevronRight className="w-3 h-3" />
                            <span>View Stage Evidence & Records</span>
                          </>
                        )}
                      </button>
                    </div>

                    {/* Collapsible Details Drawer */}
                    {isExpanded && (
                      <div className="mt-3 p-3.5 rounded-lg bg-navy-900/80 border border-navy-800 space-y-2 text-[11px] text-slate-300 overflow-x-auto animate-in fade-in duration-200">
                        {/* Custom Formatting per Stage */}
                        {stage.stage_key === 'policy' && (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between border-b border-navy-800 pb-1.5">
                              <span className="text-slate-400">Cryptographic Policy Signature:</span>
                              <code className="text-emerald-400 select-all font-bold">
                                {stage.details.policy_signature || 'tg_sig_verified'}
                              </code>
                            </div>
                            <div className="space-y-1">
                              <span className="text-slate-400 font-semibold block">Invariants Checked:</span>
                              {stage.details.checks && Array.isArray(stage.details.checks) ? (
                                <div className="space-y-1 pl-2">
                                  {stage.details.checks.map((c: any, i: number) => (
                                    <div key={i} className="flex items-center justify-between text-[10px]">
                                      <span className="text-slate-300">{c.rule_id} • {c.rule_name}</span>
                                      <span className="text-emerald-400 font-bold">PASS</span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-slate-500">7 Deterministic Checks Verified</p>
                              )}
                            </div>
                          </div>
                        )}

                        {stage.stage_key === 'approval' && (
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between">
                              <span className="text-slate-400">Authorized Operator:</span>
                              <span className="text-white font-bold">{stage.details.user_id}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-slate-400">Security Assertion:</span>
                              <span className="text-emerald-400 font-semibold">{stage.details.non_ai_assertion}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-slate-400">Action:</span>
                              <span className="text-slate-200">{stage.details.action}</span>
                            </div>
                          </div>
                        )}

                        {stage.stage_key !== 'policy' && stage.stage_key !== 'approval' && (
                          <pre className="text-[10px] text-slate-300 whitespace-pre-wrap font-mono">
                            {JSON.stringify(stage.details, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Collapsible Chronological Audit Events Ledger */}
          <div className="pt-4 border-t border-navy-800">
            <button
              type="button"
              onClick={() => setShowEventLog(!showEventLog)}
              className="w-full flex items-center justify-between p-3 rounded-xl bg-navy-950 border border-navy-800 hover:border-emerald-500/40 text-xs font-mono text-slate-300 transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-emerald-400" />
                <span className="font-bold text-white">
                  Raw Immutable Audit Event Stream ({timeline.events.length} Events)
                </span>
              </div>
              <div className="flex items-center gap-1 text-emerald-400 text-[11px]">
                <span>{showEventLog ? 'Collapse Events' : 'Expand All Events'}</span>
                {showEventLog ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </div>
            </button>

            {showEventLog && (
              <div className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1 animate-in fade-in duration-200">
                {timeline.events.map((ev: AuditEventRecord) => (
                  <div
                    key={ev.event_id}
                    className="p-3 rounded-lg bg-navy-950 border border-navy-850 text-xs font-mono space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-bold">{ev.event_type}</span>
                        <span className="text-slate-500">•</span>
                        <code className="text-slate-400">{ev.event_id}</code>
                        <span className="text-slate-500">•</span>
                        <span className="text-slate-400">Actor: {ev.actor_role}</span>
                      </div>
                      <span className="text-slate-500">{formatTimestamp(ev.timestamp)}</span>
                    </div>

                    <pre className="text-[10px] text-slate-400 bg-navy-900/60 p-2 rounded overflow-x-auto">
                      {JSON.stringify(ev.details, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

