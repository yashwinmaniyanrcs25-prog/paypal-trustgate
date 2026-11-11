import React, { useState, useEffect, useCallback } from 'react';
import {
  Terminal,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ExternalLink,
  Search,
  RefreshCw,
  Hash,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  Eye,
  X,
  Lock,
  ArrowUpDown,
  Layers,
  Database,
  FileText,
} from 'lucide-react';
import { AuditEventRecord, AuditIntegrityResponse, AuditLogItem } from '../types';
import { api } from '../lib/api';
import { formatCurrency, formatTimestamp, cn } from '../lib/utils';

interface AuditLogProps {
  logs?: AuditLogItem[];
  onRefresh?: () => void;
  isLoading?: boolean;
  onOpenTimeline?: (txId?: string) => void;
  selectedTransactionId?: string | null;
}

// Helper to mask sensitive keys in audit payloads
function sanitizeDetails(details: Record<string, unknown>): Record<string, unknown> {
  if (!details || typeof details !== 'object') return {};
  const sanitized: Record<string, unknown> = {};
  const sensitivePattern = /secret|password|token|pin|credential|authorization|private/i;

  for (const [key, val] of Object.entries(details)) {
    if (sensitivePattern.test(key)) {
      sanitized[key] = '[PROTECTED_CREDENTIAL_REDACTED]';
    } else if (val && typeof val === 'object' && !Array.isArray(val)) {
      sanitized[key] = sanitizeDetails(val as Record<string, unknown>);
    } else {
      sanitized[key] = val;
    }
  }
  return sanitized;
}

export const AuditLog: React.FC<AuditLogProps> = ({
  logs = [],
  onRefresh: parentRefresh,
  onOpenTimeline,
  selectedTransactionId: initialTxId,
}) => {
  // Active View Tab: Canonical SQLite Ledger vs Supplementary Policy Engine Logs
  const [activeTab, setActiveTab] = useState<'canonical' | 'supplementary'>('canonical');

  // Canonical Ledger State
  const [events, setEvents] = useState<AuditEventRecord[]>([]);
  const [totalEvents, setTotalEvents] = useState<number>(0);
  const [isLoadingEvents, setIsLoadingEvents] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Filters & Pagination
  const [txFilter, setTxFilter] = useState<string>(initialTxId || '');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('ALL');
  const [stageFilter, setStageFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [pageSize, setPageSize] = useState<number>(15);
  const [pageOffset, setPageOffset] = useState<number>(0);

  // Cryptographic Integrity Verification State
  const [integrity, setIntegrity] = useState<AuditIntegrityResponse | null>(null);
  const [isCheckingIntegrity, setIsCheckingIntegrity] = useState<boolean>(false);
  const [integrityError, setIntegrityError] = useState<string | null>(null);

  // Inspection Modal State
  const [inspectedEvent, setInspectedEvent] = useState<AuditEventRecord | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Sync prop changes for transaction filtering
  useEffect(() => {
    if (initialTxId !== undefined && initialTxId !== txFilter) {
      setTxFilter(initialTxId || '');
      setPageOffset(0);
    }
  }, [initialTxId]);

  // Fetch Cryptographic Integrity Status
  const runIntegrityCheck = useCallback(async () => {
    setIsCheckingIntegrity(true);
    setIntegrityError(null);
    try {
      const res = await api.checkAuditIntegrity();
      setIntegrity(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Cryptographic integrity check failed.';
      setIntegrityError(msg);
      setIntegrity(null);
    } finally {
      setIsCheckingIntegrity(false);
    }
  }, []);

  // Fetch Canonical Audit Events from SQLite Ledger
  const fetchCanonicalEvents = useCallback(async () => {
    setIsLoadingEvents(true);
    setLoadError(null);
    try {
      const res = await api.getAuditEvents({
        transaction_id: txFilter.trim() || undefined,
        event_type: eventTypeFilter !== 'ALL' ? eventTypeFilter : undefined,
        stage: stageFilter !== 'ALL' ? stageFilter : undefined,
        limit: pageSize,
        offset: pageOffset,
        order: sortOrder,
      });

      setEvents(res.events || []);
      setTotalEvents(res.total ?? res.count ?? 0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to retrieve canonical audit ledger.';
      setLoadError(msg);
      setEvents([]);
    } finally {
      setIsLoadingEvents(false);
    }
  }, [txFilter, eventTypeFilter, stageFilter, pageSize, pageOffset, sortOrder]);

  useEffect(() => {
    fetchCanonicalEvents();
  }, [fetchCanonicalEvents]);

  useEffect(() => {
    runIntegrityCheck();
  }, [runIntegrityCheck]);

  const handleRefreshAll = async () => {
    await fetchCanonicalEvents();
    await runIntegrityCheck();
    if (parentRefresh) {
      parentRefresh();
    }
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(label);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Client-side quick filter on current batch by search query
  const filteredEvents = events.filter((ev) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const eventIdMatch = ev.event_id?.toLowerCase().includes(q);
    const txIdMatch = ev.transaction_id?.toLowerCase().includes(q);
    const typeMatch = ev.event_type?.toLowerCase().includes(q);
    const actorMatch = ev.actor_role?.toLowerCase().includes(q);
    const detailsMatch = JSON.stringify(ev.details || {}).toLowerCase().includes(q);
    return eventIdMatch || txIdMatch || typeMatch || actorMatch || detailsMatch;
  });

  const currentPage = Math.floor(pageOffset / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(totalEvents / pageSize));

  return (
    <div className="rounded-2xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-7 space-y-6">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Canonical Ledger Tabs                                   */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-navy-800">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
              Audit Trail & Immutable Ledger
            </h2>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono font-bold uppercase tracking-wider">
              SHA-256 Chained
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Cryptographically sealed, append-only security ledger persisting all agentic purchasing milestones.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={isLoadingEvents || isCheckingIntegrity}
            className="px-3 py-1.5 rounded-xl border border-navy-700 bg-navy-950 hover:bg-navy-800 text-xs font-mono text-slate-300 hover:text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', (isLoadingEvents || isCheckingIntegrity) && 'animate-spin text-emerald-400')} />
            <span>Sync Ledger</span>
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Cryptographic Integrity Visibility Banner                        */}
      {/* ------------------------------------------------------------------- */}
      <div
        className={cn(
          'p-4 sm:p-5 rounded-xl border transition-all space-y-3',
          integrity?.is_valid === true
            ? 'bg-emerald-950/20 border-emerald-500/30'
            : integrity?.is_valid === false
            ? 'bg-rose-950/30 border-rose-500/50 shadow-red-glow'
            : 'bg-navy-950 border-navy-800'
        )}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center gap-3">
            {integrity?.is_valid === true ? (
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center shrink-0">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
              </div>
            ) : integrity?.is_valid === false ? (
              <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/40 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-400" />
              </div>
            ) : (
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0">
                <Clock className="w-5 h-5 text-amber-400" />
              </div>
            )}

            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs sm:text-sm font-bold text-white font-mono">
                  Cryptographic Chain Integrity:
                </span>
                {integrity?.is_valid === true ? (
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[11px] font-mono font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>VERIFIED (UNBROKEN)</span>
                  </span>
                ) : integrity?.is_valid === false ? (
                  <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[11px] font-mono font-bold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>TAMPER DETECTED (INVALID)</span>
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[11px] font-mono font-bold flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    <span>VERIFICATION UNAVAILABLE</span>
                  </span>
                )}
              </div>
              <p className="text-[11px] font-mono text-slate-400 mt-0.5">
                {integrity?.is_valid === true
                  ? `${integrity.total_events} consecutive events cryptographically validated via continuous SHA-256 hash chaining.`
                  : integrity?.is_valid === false
                  ? `Cryptographic digest mismatch: ${integrity.failure_reason || 'Tampered block detected.'}`
                  : integrityError || 'Audit integrity telemetry is awaiting backend confirmation.'}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={runIntegrityCheck}
            disabled={isCheckingIntegrity}
            className="px-3 py-1.5 rounded-lg border border-navy-700 bg-navy-900 hover:bg-navy-800 text-xs font-mono text-slate-300 hover:text-white transition-all flex items-center gap-1.5 self-start sm:self-center shrink-0"
          >
            <Hash className="w-3.5 h-3.5 text-emerald-400" />
            <span>{isCheckingIntegrity ? 'Verifying Hashes...' : 'Re-verify Chain'}</span>
          </button>
        </div>

        {/* Diagnostic Metadata & Head Hashes */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-2 border-t border-navy-850 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-navy-950/70 border border-navy-850">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Genesis Hash</span>
            <span className="text-[11px] text-slate-300 truncate block select-all">
              {integrity?.genesis_hash || '0'.repeat(64)}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-navy-950/70 border border-navy-850">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Latest Head Event Hash</span>
            <span className={cn(
              'text-[11px] truncate block select-all',
              integrity?.is_valid ? 'text-emerald-400' : 'text-slate-300'
            )}>
              {integrity?.last_event_hash || 'No head hash available'}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-navy-950/70 border border-navy-850">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Verified At</span>
            <span className="text-[11px] text-slate-300 block">
              {integrity?.verified_at ? formatTimestamp(integrity.verified_at) : '—'}
            </span>
          </div>
        </div>

        {/* Tamper Alert Details if Chain Broken */}
        {integrity?.is_valid === false && integrity.first_invalid_sequence && (
          <div className="p-3 rounded-lg bg-rose-950/80 border border-rose-500/60 text-xs font-mono text-rose-200 space-y-1">
            <div className="font-bold flex items-center gap-1.5 text-rose-300">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>Tamper Alert: Cryptographic Breach at Sequence #{integrity.first_invalid_sequence}</span>
            </div>
            <p className="text-[11px] text-rose-300">
              Event ID: <code>{integrity.first_invalid_event_id || 'Unknown'}</code> • {integrity.failure_reason}
            </p>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Source Selection Tabs                                            */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex items-center gap-2 border-b border-navy-800 pb-2">
        <button
          type="button"
          onClick={() => setActiveTab('canonical')}
          className={cn(
            'px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-2',
            activeTab === 'canonical'
              ? 'bg-emerald-500 text-navy-950 shadow-emerald-glow'
              : 'text-slate-400 hover:text-white hover:bg-navy-800'
          )}
        >
          <Database className="w-3.5 h-3.5" />
          <span>Canonical SQLite Transaction Ledger ({totalEvents})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('supplementary')}
          className={cn(
            'px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-2',
            activeTab === 'supplementary'
              ? 'bg-emerald-500 text-navy-950 shadow-emerald-glow'
              : 'text-slate-400 hover:text-white hover:bg-navy-800'
          )}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Supplementary Policy Engine Logs ({logs.length})</span>
        </button>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Canonical SQLite Ledger View                                     */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === 'canonical' && (
        <div className="space-y-4">
          {/* Controls & Filter Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {/* Search Input */}
            <div className="lg:col-span-2 relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search event ID, transaction ID, keyword..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-2 rounded-xl bg-navy-950 border border-navy-800 text-xs text-white placeholder-slate-500 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Event Type Filter */}
            <div>
              <select
                value={eventTypeFilter}
                onChange={(e) => {
                  setEventTypeFilter(e.target.value);
                  setPageOffset(0);
                }}
                className="w-full px-3 py-2 rounded-xl bg-navy-950 border border-navy-800 text-xs text-white font-mono focus:outline-none focus:border-emerald-500 cursor-pointer"
              >
                <option value="ALL">All Event Types</option>
                <option value="PROPOSAL_STAGED">PROPOSAL_STAGED</option>
                <option value="HUMAN_APPROVAL_GRANTED">HUMAN_APPROVAL_GRANTED</option>
                <option value="HUMAN_APPROVAL_REJECTED">HUMAN_APPROVAL_REJECTED</option>
                <option value="CHECKOUT_CANCELLED">CHECKOUT_CANCELLED</option>
                <option value="CHECKOUT_EXPIRED">CHECKOUT_EXPIRED</option>
                <option value="PAYPAL_ORDER_CREATED">PAYPAL_ORDER_CREATED</option>
                <option value="PAYPAL_CAPTURED">PAYPAL_CAPTURED</option>
                <option value="PAYPAL_ORDER_CREATION_FAILED">PAYPAL_ORDER_CREATION_FAILED</option>
                <option value="PAYPAL_CAPTURE_FAILED">PAYPAL_CAPTURE_FAILED</option>
                <option value="POLICY_EVALUATION">POLICY_EVALUATION</option>
              </select>
            </div>

            {/* Stage Filter */}
            <div>
              <select
                value={stageFilter}
                onChange={(e) => {
                  setStageFilter(e.target.value);
                  setPageOffset(0);
                }}
                className="w-full px-3 py-2 rounded-xl bg-navy-950 border border-navy-800 text-xs text-white font-mono focus:outline-none focus:border-emerald-500 cursor-pointer"
              >
                <option value="ALL">All Stages</option>
                <option value="PROPOSAL">PROPOSAL</option>
                <option value="APPROVAL">APPROVAL</option>
                <option value="PAYMENT">PAYMENT</option>
                <option value="RECEIPT">RECEIPT</option>
                <option value="LIFECYCLE">LIFECYCLE</option>
                <option value="POLICY">POLICY</option>
              </select>
            </div>

            {/* Sort Order Toggle */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
                className="flex-1 py-2 px-3 rounded-xl bg-navy-950 border border-navy-800 text-xs text-slate-300 font-mono hover:text-white flex items-center justify-center gap-1.5 transition-colors"
              >
                <ArrowUpDown className="w-3.5 h-3.5 text-emerald-400" />
                <span>{sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}</span>
              </button>
            </div>
          </div>

          {/* Active Transaction Pin (if set) */}
          {txFilter && (
            <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Filtered by Transaction ID:</span>
                <code className="text-emerald-400 font-bold">{txFilter}</code>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTxFilter('');
                  setPageOffset(0);
                }}
                className="text-[11px] text-slate-400 hover:text-rose-400 transition-colors flex items-center gap-1"
              >
                <X className="w-3 h-3" />
                <span>Clear Filter</span>
              </button>
            </div>
          )}

          {/* Ledger Table / List */}
          {isLoadingEvents ? (
            <div className="p-12 text-center rounded-xl border border-navy-800 bg-navy-950/60 space-y-3">
              <RefreshCw className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
              <p className="text-xs font-mono text-slate-400">Loading immutable audit stream from SQLite...</p>
            </div>
          ) : loadError ? (
            <div className="p-8 text-center rounded-xl border border-rose-500/30 bg-rose-950/20 space-y-2">
              <AlertTriangle className="w-6 h-6 text-rose-400 mx-auto" />
              <p className="text-sm font-semibold text-rose-300">{loadError}</p>
              <button
                type="button"
                onClick={fetchCanonicalEvents}
                className="px-3 py-1.5 rounded-lg bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 text-xs font-mono"
              >
                Retry Sync
              </button>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="p-12 text-center rounded-xl border border-navy-800 bg-navy-950/40 space-y-3">
              <CheckCircle2 className="w-8 h-8 text-emerald-400/50 mx-auto" />
              <h3 className="text-sm font-bold text-slate-300">No Audit Events Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No events match the current filter criteria. Actions staged from Product Discovery or Approval Center will be appended here.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredEvents.map((ev) => {
                const isPassed = ev.status === 'GRANTED' || ev.status === 'COMPLETED' || ev.status === 'STAGED' || ev.status === 'CREATED';
                const isFailed = ev.status === 'REJECTED' || ev.status === 'CANCELLED' || ev.status === 'EXPIRED' || ev.status?.includes('FAILED');

                return (
                  <div
                    key={ev.event_id}
                    className="p-3.5 rounded-xl bg-navy-950 border border-navy-850 hover:border-navy-700 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono"
                  >
                    <div className="flex items-start sm:items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-navy-900 border border-navy-800 text-[10px] text-slate-400 font-bold shrink-0">
                        #{ev.sequence_number ?? '—'}
                      </span>

                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-white font-bold text-xs">{ev.event_type}</span>
                          <span
                            className={cn(
                              'px-2 py-0.2 rounded text-[10px] font-bold uppercase',
                              isPassed
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : isFailed
                                ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                                : 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                            )}
                          >
                            {ev.status}
                          </span>
                          <span className="text-[10px] text-slate-500">Stage: {ev.stage}</span>
                        </div>

                        <div className="flex items-center gap-2 text-[11px] text-slate-400 flex-wrap">
                          <span>Tx: <strong className="text-slate-300">{ev.transaction_id}</strong></span>
                          <span>•</span>
                          <span>Actor: <strong className="text-slate-300">{ev.actor_role}</strong></span>
                          <span>•</span>
                          <span className="text-slate-500">{formatTimestamp(ev.timestamp)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                      {onOpenTimeline && (
                        <button
                          type="button"
                          onClick={() => onOpenTimeline(ev.transaction_id)}
                          className="px-2.5 py-1 rounded bg-navy-900 hover:bg-navy-855 border border-navy-800 text-slate-300 hover:text-emerald-400 text-[11px] transition-colors flex items-center gap-1"
                        >
                          <span>Timeline</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => setInspectedEvent(ev)}
                        className="px-2.5 py-1 rounded bg-navy-900 hover:bg-navy-855 border border-navy-800 text-slate-300 hover:text-white text-[11px] transition-colors flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3 text-emerald-400" />
                        <span>Inspect Payload</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination Controls */}
          {totalEvents > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-navy-800 text-xs font-mono text-slate-400">
              <div className="flex items-center gap-2">
                <span>Show</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPageOffset(0);
                  }}
                  className="px-2 py-1 rounded bg-navy-950 border border-navy-800 text-xs text-white"
                >
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
                <span>per page • Total: <strong>{totalEvents}</strong> events</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPageOffset((prev) => Math.max(0, prev - pageSize))}
                  disabled={pageOffset === 0}
                  className="px-3 py-1 rounded-lg bg-navy-950 border border-navy-800 disabled:opacity-40 text-slate-300 hover:text-white flex items-center gap-1"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Previous</span>
                </button>

                <span className="px-2 py-1 text-slate-300 font-bold">
                  Page {currentPage} of {totalPages}
                </span>

                <button
                  type="button"
                  onClick={() => setPageOffset((prev) => prev + pageSize)}
                  disabled={currentPage >= totalPages}
                  className="px-3 py-1 rounded-lg bg-navy-950 border border-navy-800 disabled:opacity-40 text-slate-300 hover:text-white flex items-center gap-1"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 5. Supplementary Policy Engine Logs View                            */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === 'supplementary' && (
        <div className="space-y-4">
          <div className="p-3.5 rounded-xl bg-navy-950 border border-navy-800 text-xs text-slate-400 font-mono space-y-1">
            <div className="flex items-center gap-2 text-white font-bold">
              <FileText className="w-4 h-4 text-emerald-400" />
              <span>Supplementary Policy Engine Logs</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              These records reflect deterministic evaluations executed during interactive discovery and simulation.
              They are mirrored into persistent SQLite storage alongside the canonical transaction ledger.
            </p>
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {logs.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center font-mono">No supplementary policy evaluations recorded yet.</p>
            ) : (
              logs.map((log, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg bg-navy-950 border border-navy-850 flex items-center justify-between text-xs font-mono gap-3"
                >
                  <div className="flex items-center gap-2 truncate">
                    {log.passed ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    )}
                    <span className="text-slate-200 font-bold">{log.evaluation_id}</span>
                    <span className="text-slate-500 hidden sm:inline">•</span>
                    <span className="text-slate-400 hidden sm:inline truncate">
                      {log.passed ? 'VERIFIED' : `VIOLATION: ${log.violations[0] || 'Interception'}`}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 text-slate-400 text-[11px]">
                    <span className="text-emerald-400 font-bold">
                      {formatCurrency(log.total_cost)}
                    </span>
                    <span className="flex items-center gap-1 text-slate-500">
                      <Clock className="w-3 h-3" />
                      {formatTimestamp(log.timestamp)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 6. Event Detail Modal (Safe Payload Inspection)                     */}
      {/* ------------------------------------------------------------------- */}
      {inspectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border border-navy-700 bg-navy-900 p-6 shadow-2xl space-y-4">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-navy-800 pb-3">
              <div className="flex items-center gap-2">
                <Hash className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white font-mono">
                  Audit Event #{inspectedEvent.sequence_number ?? '—'} • {inspectedEvent.event_type}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setInspectedEvent(null)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Event Key Identifiers */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-850">
                <span className="text-[10px] text-slate-500 uppercase block">Event ID</span>
                <span className="text-slate-200 select-all font-bold">{inspectedEvent.event_id}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-850">
                <span className="text-[10px] text-slate-500 uppercase block">Transaction Reference</span>
                <span className="text-emerald-400 select-all font-bold">{inspectedEvent.transaction_id}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-850">
                <span className="text-[10px] text-slate-500 uppercase block">Stage & Status</span>
                <span className="text-slate-200">{inspectedEvent.stage} • {inspectedEvent.status}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-850">
                <span className="text-[10px] text-slate-500 uppercase block">Actor / Role</span>
                <span className="text-slate-200">{inspectedEvent.actor_role}</span>
              </div>
            </div>

            {/* Cryptographic Linkage Hashes */}
            <div className="p-3.5 rounded-xl bg-navy-950 border border-navy-850 space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between text-slate-400 text-[11px] font-bold">
                <span className="flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Cryptographic Proof Linkage</span>
                </span>
                <span className="text-emerald-400">SHA-256 Canonical Digest</span>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-500">Previous Block Hash (prev_hash):</span>
                  <button
                    type="button"
                    onClick={() => handleCopy(inspectedEvent.prev_hash || '', 'prev')}
                    className="text-slate-400 hover:text-white flex items-center gap-1 text-[10px]"
                  >
                    {copiedHash === 'prev' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    <span>Copy</span>
                  </button>
                </div>
                <code className="block p-2 rounded bg-navy-900 border border-navy-800 text-[10px] text-slate-400 break-all select-all">
                  {inspectedEvent.prev_hash || 'Genesis Hash (None)'}
                </code>
              </div>

              <div className="space-y-1 pt-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-500">Current Event Hash (event_hash):</span>
                  <button
                    type="button"
                    onClick={() => handleCopy(inspectedEvent.event_hash || '', 'curr')}
                    className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 text-[10px]"
                  >
                    {copiedHash === 'curr' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    <span>Copy</span>
                  </button>
                </div>
                <code className="block p-2 rounded bg-navy-900 border border-navy-800 text-[10px] text-emerald-400 break-all select-all font-bold">
                  {inspectedEvent.event_hash || 'Uncomputed'}
                </code>
              </div>
            </div>

            {/* Sanitized JSON Payload */}
            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span className="font-bold">Sanitized Event Payload:</span>
                <span className="text-[10px] text-slate-500">Sensitive credentials masked</span>
              </div>
              <pre className="p-3.5 rounded-xl bg-navy-950 border border-navy-850 text-[11px] text-slate-300 whitespace-pre-wrap font-mono max-h-56 overflow-y-auto">
                {JSON.stringify(sanitizeDetails(inspectedEvent.details || {}), null, 2)}
              </pre>
            </div>

            {/* Modal Actions */}
            <div className="flex justify-end pt-2 border-t border-navy-800">
              <button
                type="button"
                onClick={() => setInspectedEvent(null)}
                className="px-4 py-2 rounded-xl bg-navy-800 hover:bg-navy-700 text-xs font-mono text-white transition-colors"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
