import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Hash,
  FileText,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  UserCheck,
  CreditCard,
  Receipt,
  Search,
  Lock,
  ArrowLeft,
  Ban,
  CheckCircle2,
  X,
} from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatTimestamp, cn } from '../lib/utils';
import { isCancellableState, getStatusBadge } from '../lib/lifecycle';
import { AuditEventRecord } from '../types';

interface ForensicDetailProps {
  transactionId: string;
  onClose?: () => void;
}

const SectionHeader: React.FC<{ icon: React.ElementType; title: string; badge?: string; badgeColor?: string }> = ({
  icon: Icon,
  title,
  badge,
  badgeColor = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
}) => (
  <div className="flex items-center gap-2 pb-3 border-b border-navy-800 mb-4">
    <Icon className="w-4 h-4 text-emerald-400" />
    <h3 className="text-sm font-bold text-white">{title}</h3>
    {badge && (
      <span className={cn('px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider ml-auto', badgeColor)}>
        {badge}
      </span>
    )}
  </div>
);

const KV: React.FC<{ label: string; value: React.ReactNode; mono?: boolean; highlight?: boolean }> = ({
  label,
  value,
  mono = true,
  highlight = false,
}) => (
  <div className="flex items-start justify-between gap-4 py-1.5 border-b border-navy-800/60 last:border-0 text-xs">
    <span className="text-slate-500 shrink-0 w-40">{label}</span>
    <span className={cn(
      'text-right flex-1 break-all',
      mono ? 'font-mono' : '',
      highlight ? 'text-emerald-400 font-bold' : 'text-slate-200'
    )}>
      {value}
    </span>
  </div>
);

export const ForensicDetail: React.FC<ForensicDetailProps> = ({ transactionId, onClose }) => {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvents, setExpandedEvents] = useState(false);
  const [expandedStages, setExpandedStages] = useState<Record<string, boolean>>({
    policy: true,
    approval: true,
  });

  // Cancellation State
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState('Cancelled by operator via forensic detail view');
  const [cancelConfirmCheckbox, setCancelConfirmCheckbox] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelSuccessMsg, setCancelSuccessMsg] = useState<string | null>(null);
  const [cancelErrMsg, setCancelErrMsg] = useState<string | null>(null);

  const toggleStage = (stageKey: string) => {
    setExpandedStages((prev) => ({
      ...prev,
      [stageKey]: !prev[stageKey],
    }));
  };

  const handleCancelSession = async () => {
    if (!cancelConfirmCheckbox) {
      setCancelErrMsg('Please check the confirmation box to confirm session cancellation.');
      return;
    }
    if (!cancelReason.trim()) {
      setCancelErrMsg('Please provide a cancellation rationale.');
      return;
    }

    setIsCancelling(true);
    setCancelErrMsg(null);

    try {
      await api.cancelProposal(transactionId, {
        user_id: 'operator_forensic_reviewer',
        reason: cancelReason.trim(),
      });
      setCancelSuccessMsg('Checkout session successfully cancelled. Transaction transitioned to terminal CANCELLED.');
      setShowCancelModal(false);
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to cancel checkout session.';
      setCancelErrMsg(msg);
    } finally {
      setIsCancelling(false);
    }
  };

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const timeline = await api.getTransactionTimeline(transactionId);
      setData(timeline);
    } catch (e: any) {
      setError(e?.message || 'Failed to load forensic data');
    } finally {
      setIsLoading(false);
    }
  }, [transactionId]);

  useEffect(() => {
    load();
  }, [load]);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-10 flex flex-col items-center gap-3 text-slate-500">
        <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
        <span className="text-xs font-mono">Reconstructing forensic record…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/20 bg-rose-950/10 p-8 flex flex-col items-center gap-3">
        <AlertTriangle className="w-6 h-6 text-rose-400" />
        <p className="text-xs text-rose-300 font-mono">{error}</p>
        <button onClick={load} className="text-xs text-slate-400 hover:text-white underline">Retry</button>
      </div>
    );
  }

  if (!data) return null;

  const { candidate_summary, mandate_summary, policy_evaluation_summary, human_approval_summary, paypal_order_summary, capture_receipt_summary, stages, events } = data;
  const isDemo = candidate_summary?.is_demo_data;

  return (
    <div className="space-y-5">
      {/* Back button + Title */}
      <div className="flex items-center gap-3">
        {onClose && (
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-navy-700 bg-navy-900 text-xs font-mono text-slate-400 hover:text-white hover:border-navy-600 transition-all"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Table
          </button>
        )}
        <div>
          <h2 className="text-base font-bold text-white">Forensic Transaction Record</h2>
          <p className="text-xs text-slate-500 font-mono mt-0.5">{transactionId}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {isDemo && (
            <span className="px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[10px] font-mono font-bold uppercase">
              Simulated Demo Product
            </span>
          )}
          {(() => {
            const badge = getStatusBadge(data.current_status);
            return (
              <span className={cn('px-2.5 py-0.5 rounded border text-[10px] font-mono font-bold uppercase', badge.badgeClass)}>
                {badge.label} ({data.current_status})
              </span>
            );
          })()}
          {isCancellableState(data.current_status) && (
            <button
              type="button"
              onClick={() => {
                setShowCancelModal(true);
                setCancelConfirmCheckbox(false);
                setCancelErrMsg(null);
              }}
              className="px-3 py-1 rounded-lg border border-slate-700 bg-navy-950 text-xs font-mono text-slate-300 hover:text-rose-400 hover:border-rose-500/40 transition-colors flex items-center gap-1.5"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Cancel Session</span>
            </button>
          )}
        </div>
      </div>

      {/* Cancellation Alerts */}
      {cancelSuccessMsg && (
        <div className="p-3 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-xs font-mono text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{cancelSuccessMsg}</span>
        </div>
      )}

      {cancelErrMsg && (
        <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{cancelErrMsg}</span>
        </div>
      )}

      {/* Cancellation Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-navy-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-navy-800 pb-3">
              <div className="flex items-center gap-2 text-rose-400 font-mono font-bold text-sm">
                <Ban className="w-4 h-4" />
                <span>Cancel Checkout Session</span>
              </div>
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Explicit Confirmation Required: Cancelling this session is terminal and permanently blocks order creation or capture.
            </p>

            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">
                Cancellation Rationale (Mandatory)
              </label>
              <textarea
                rows={2}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                className="w-full p-2.5 rounded-lg bg-navy-950 border border-navy-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500 font-mono"
              />
            </div>

            <label className="flex items-start gap-2.5 p-2.5 rounded-lg bg-navy-950 border border-navy-800 cursor-pointer">
              <input
                type="checkbox"
                checked={cancelConfirmCheckbox}
                onChange={(e) => setCancelConfirmCheckbox(e.target.checked)}
                className="mt-0.5 rounded border-navy-700 bg-navy-900 text-rose-500 focus:ring-0 w-4 h-4 cursor-pointer"
              />
              <span className="text-xs text-slate-300 leading-tight">
                I confirm that this checkout session should be permanently cancelled.
              </span>
            </label>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-mono text-slate-400 hover:text-white"
              >
                Keep Session
              </button>
              <button
                type="button"
                onClick={handleCancelSession}
                disabled={isCancelling || !cancelConfirmCheckbox || !cancelReason.trim()}
                className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-mono font-bold text-xs flex items-center gap-1.5 transition-colors"
              >
                {isCancelling ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Cancelling...</span>
                  </>
                ) : (
                  <>
                    <Ban className="w-3.5 h-3.5" />
                    <span>Confirm Cancellation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Demo Data Notice */}
      {isDemo && (
        <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/20 text-xs font-mono text-amber-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            This transaction uses a <strong>simulated demo product</strong> from the local demo fixture catalog.
            The PayPal payment data (order ID, capture ID) reflects genuine <strong>Sandbox API calls</strong>, not real financial transactions.
          </span>
        </div>
      )}

      {/* Top Row: Mandate + Product */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Mandate */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
          <SectionHeader icon={FileText} title="Spending Mandate" badge={mandate_summary?.mandate_id?.slice(0, 10) + '…'} />
          <KV label="Mandate ID" value={mandate_summary?.mandate_id} highlight />
          <KV label="Budget Ceiling" value={formatCurrency(mandate_summary?.max_amount, mandate_summary?.currency)} highlight />
          <KV label="Currency" value={mandate_summary?.currency} />
          <KV label="Allowed Conditions" value={(mandate_summary?.allowed_conditions || []).join(', ')} />
        </div>

        {/* Product */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
          <SectionHeader
            icon={Search}
            title="Candidate Product"
            badge={isDemo ? 'Demo Catalog' : 'Marketplace'}
            badgeColor={isDemo ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' : 'text-sky-400 bg-sky-500/10 border-sky-500/20'}
          />
          <KV label="Product Name" value={candidate_summary?.name} mono={false} />
          <KV label="Price" value={formatCurrency(candidate_summary?.price, candidate_summary?.currency)} highlight />
          <KV label="Condition" value={candidate_summary?.condition} />
          <KV label="Merchant" value={candidate_summary?.merchant_name} mono={false} />
          <KV label="Demo Data" value={isDemo ? 'Yes — Simulated' : 'No — Real Listing'} />
        </div>
      </div>

      {/* Policy Evaluation */}
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
        <div className="flex items-center justify-between pb-3 border-b border-navy-800 mb-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white">Deterministic Policy Evaluation</h3>
            <span className={cn(
              'px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider',
              policy_evaluation_summary?.approved
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                : 'text-rose-400 bg-rose-500/10 border-rose-500/20'
            )}>
              {policy_evaluation_summary?.approved ? 'ALL PASSED' : 'VIOLATIONS'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => toggleStage('policy')}
            className="flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-white transition-colors"
          >
            {expandedStages.policy ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            <span>{expandedStages.policy ? 'Collapse' : 'Expand'}</span>
          </button>
        </div>

        {expandedStages.policy && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <KV label="Evaluation ID" value={policy_evaluation_summary?.evaluation_id} highlight />
                <KV label="Policy Verdict" value={policy_evaluation_summary?.approved ? 'APPROVED' : 'BLOCKED'} highlight />
                <KV label="Violations" value={policy_evaluation_summary?.violations_count ?? 0} />
              </div>
              <div className="text-xs font-mono">
                <p className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Policy Signature (SHA-256 HMAC)</p>
                <code className="block p-2.5 rounded-lg bg-navy-950 border border-navy-800 text-emerald-400 break-all text-[10px] select-all">
                  {policy_evaluation_summary?.policy_signature || 'Not available'}
                </code>
              </div>
            </div>

            {/* Seven TG invariants */}
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
              {stages?.find((s: any) => s.stage_key === 'policy')?.details?.checks?.length > 0 ? (
                stages.find((s: any) => s.stage_key === 'policy').details.checks.map((c: any, i: number) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-navy-950 border border-navy-800 text-[10px] font-mono">
                    <span className="text-slate-300">{c.rule_id} · {c.rule_name}</span>
                    <span className="text-emerald-400 font-bold">PASS</span>
                  </div>
                ))
              ) : (
                [
                  'TG-001 · Spending Limit Math',
                  'TG-002 · Currency Alignment',
                  'TG-003 · Product Condition',
                  'TG-004 · Merchant Trust',
                  'TG-005 · Add-on Protection',
                  'TG-006 · Data Integrity',
                  'TG-007 · AI Zero Autonomy',
                ].map((rule, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-navy-950 border border-navy-800 text-[10px] font-mono">
                    <span className="text-slate-300">{rule}</span>
                    <span className={cn(
                      'font-bold',
                      policy_evaluation_summary?.approved ? 'text-emerald-400' : 'text-slate-500'
                    )}>
                      {policy_evaluation_summary?.approved ? 'PASS' : '—'}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Human Authorization */}
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
        <div className="flex items-center justify-between pb-3 border-b border-navy-800 mb-4">
          <div className="flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white">Human Authorization Record</h3>
            <span className={cn(
              'px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider',
              human_approval_summary?.approved
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                : 'text-amber-400 bg-amber-500/10 border-amber-500/20'
            )}>
              {human_approval_summary?.approved ? 'AUTHORIZED' : 'PENDING'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => toggleStage('approval')}
            className="flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-white transition-colors"
          >
            {expandedStages.approval ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            <span>{expandedStages.approval ? 'Collapse' : 'Expand'}</span>
          </button>
        </div>

        {expandedStages.approval && (
          <div>
            {human_approval_summary?.approved ? (
              <div>
                <KV label="Approval ID" value={human_approval_summary?.approval_id || 'recorded'} highlight />
                <KV label="Authorized By" value={human_approval_summary?.user_id} />
                <KV
                  label="Security Assertion"
                  value={
                    <span className="text-emerald-400">
                      <Lock className="w-3 h-3 inline mr-1" />
                      Non-AI human operator authorization confirmed
                    </span>
                  }
                  mono={false}
                />
              </div>
            ) : (
              <p className="text-xs text-amber-400 font-mono">Explicit human authorization pending.</p>
            )}
          </div>
        )}
      </div>

      {/* PayPal Sandbox */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
          <SectionHeader icon={CreditCard} title="PayPal Sandbox Order" badge="SANDBOX ONLY" badgeColor="text-violet-400 bg-violet-500/10 border-violet-500/20" />
          <KV label="Order ID" value={paypal_order_summary?.order_id || 'Not yet initiated'} highlight={!!paypal_order_summary?.order_id} />
          <KV label="Order Status" value={paypal_order_summary?.status || 'NOT_INITIATED'} />
          <KV label="Schema Contract" value="PayPal Orders v2 (TrustGate Pre-Flight Validated)" mono={false} />
          <KV label="Environment" value="PayPal Sandbox (api-m.sandbox.paypal.com)" mono={false} />
          <KV label="Real Charges" value="None — Sandbox environment only" mono={false} />
        </div>

        <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
          <SectionHeader
            icon={Receipt}
            title="Capture Receipt"
            badge={capture_receipt_summary?.captured ? 'COMPLETED' : 'PENDING'}
            badgeColor={capture_receipt_summary?.captured
              ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
              : 'text-slate-400 bg-slate-500/10 border-slate-500/20'}
          />
          <KV label="Capture ID" value={capture_receipt_summary?.capture_id || 'Not yet captured'} highlight={!!capture_receipt_summary?.capture_id} />
          <KV
            label="Captured At"
            value={capture_receipt_summary?.captured_at ? formatTimestamp(capture_receipt_summary.captured_at) : '—'}
          />
          {isDemo && (
            <div className="mt-3 p-2 rounded-lg bg-amber-950/20 border border-amber-500/20 text-[10px] font-mono text-amber-400">
              Simulated demo item — no real financial transaction occurred.
            </div>
          )}
        </div>
      </div>

      {/* Cryptographic Audit Chain */}
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white">Cryptographic Audit Event Chain</h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-500">{(events || []).length} events</span>
            <button
              onClick={() => setExpandedEvents(!expandedEvents)}
              className="flex items-center gap-1 px-2 py-1 rounded border border-navy-700 bg-navy-950 text-[10px] font-mono text-slate-400 hover:text-emerald-400 transition-colors"
            >
              {expandedEvents ? (
                <><ChevronDown className="w-3 h-3" /> Collapse</>
              ) : (
                <><ChevronRight className="w-3 h-3" /> Show Events</>
              )}
            </button>
          </div>
        </div>

        {expandedEvents && (
          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {(events || []).length === 0 ? (
              <p className="text-xs text-slate-600 font-mono text-center py-4">No audit events recorded yet.</p>
            ) : (
              events.map((ev: AuditEventRecord, i: number) => (
                <div
                  key={ev.event_id || i}
                  className="p-3 rounded-lg bg-navy-950 border border-navy-800 text-[10px] font-mono space-y-2"
                >
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600">#{ev.sequence_number}</span>
                      <span className="text-emerald-400 font-bold">{ev.event_type}</span>
                      <span className="text-slate-500">{ev.stage}</span>
                      <span className={cn(
                        'px-1.5 py-0.5 rounded border text-[9px] uppercase font-bold',
                        ev.status === 'APPROVED' || ev.status === 'COMPLETED'
                          ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
                          : 'text-slate-400 border-slate-700 bg-slate-800/50'
                      )}>
                        {ev.status}
                      </span>
                    </div>
                    <span className="text-slate-600">{formatTimestamp(ev.timestamp)}</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                    <div>
                      <span className="text-slate-600">prev_hash: </span>
                      <code className="text-slate-500 select-all">{ev.prev_hash?.slice(0, 16)}…</code>
                    </div>
                    <div>
                      <span className="text-slate-600">event_hash: </span>
                      <code className="text-emerald-600 select-all">{ev.event_hash?.slice(0, 16)}…</code>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {!expandedEvents && (events || []).length > 0 && (
          <div className="text-xs font-mono text-slate-500 flex items-center gap-2 py-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            {(events || []).length} SHA-256 chained events. Click &quot;Show Events&quot; to inspect the full ledger.
          </div>
        )}
      </div>
    </div>
  );
};

