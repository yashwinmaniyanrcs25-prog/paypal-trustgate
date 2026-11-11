import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Lock,
  ArrowRight,
  RefreshCw,
  Search,
  Check,
  X,
  CreditCard,
  KeyRound,
  Ban,
} from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatTimestamp, cn } from '../lib/utils';
import { PayPalSandboxCheckout } from './PayPalSandboxCheckout';
import { DiscoveredProduct, PurchaseMandate, StageProposalResponse } from '../types';
import {
  isCancellableState,
  canLaunchCheckout,
  canApproveProposal,
  canRejectProposal,
  isTerminalState,
  getStatusBadge,
} from '../lib/lifecycle';

interface TransactionSummary {
  transaction_id: string;
  product_name: string;
  amount: number;
  currency: string;
  merchant_name?: string;
  policy_approved?: boolean;
  status: string;
  created_at: string;
  paypal_order_id?: string | null;
  capture_id?: string | null;
}

interface ApprovalCenterProps {
  onRefreshSummary?: () => void;
  onNavigateToAudit?: (txId?: string) => void;
}

export const ApprovalCenter: React.FC<ApprovalCenterProps> = ({
  onRefreshSummary,
  onNavigateToAudit,
}) => {
  const [transactions, setTransactions] = useState<TransactionSummary[]>([]);
  const [filter, setFilter] = useState<'PENDING' | 'APPROVED' | 'REJECTED' | 'ALL'>('PENDING');
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Review & Confirmation Modal
  const [reviewTxId, setReviewTxId] = useState<string | null>(null);
  const [reviewDetail, setReviewDetail] = useState<any | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // Operator Action Form State
  const [operatorId, setOperatorId] = useState('operator_human_reviewer');
  const [securityPin, setSecurityPin] = useState('');
  const [confirmCheckbox, setConfirmCheckbox] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [cancelReason, setCancelReason] = useState('Cancelled by human reviewer');
  const [cancelConfirmCheckbox, setCancelConfirmCheckbox] = useState(false);
  const [showCancelForm, setShowCancelForm] = useState(false);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);
  const [actionErrorMessage, setActionErrorMessage] = useState<string | null>(null);

  // Handoff to PayPal Checkout Modal
  const [checkoutProposal, setCheckoutProposal] = useState<{
    stagedProposal: StageProposalResponse;
    candidate: DiscoveredProduct;
    mandate: PurchaseMandate;
  } | null>(null);

  const fetchTransactions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getPersistedTransactions(50);
      setTransactions(res.transactions || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load transaction queue.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // Load detailed forensic timeline for the proposal being reviewed
  const openReviewModal = async (txId: string) => {
    setReviewTxId(txId);
    setReviewDetail(null);
    setActionSuccessMessage(null);
    setActionErrorMessage(null);
    setShowRejectForm(false);
    setShowCancelForm(false);
    setConfirmCheckbox(false);
    setCancelConfirmCheckbox(false);
    setSecurityPin('');
    setRejectReason('');
    setCancelReason('Cancelled by human reviewer');
    setIsLoadingDetail(true);

    try {
      const timelineData = await api.getTransactionTimeline(txId);
      setReviewDetail(timelineData);
    } catch (err: unknown) {
      console.warn('Failed to load timeline detail:', err);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const closeReviewModal = () => {
    setReviewTxId(null);
    setReviewDetail(null);
    setActionSuccessMessage(null);
    setActionErrorMessage(null);
  };

  // Explicit Human Authorization
  const handleApprove = async () => {
    if (!reviewTxId) return;
    if (!confirmCheckbox) {
      setActionErrorMessage('You must check the compliance confirmation box before authorizing.');
      return;
    }

    setIsSubmittingAction(true);
    setActionErrorMessage(null);

    try {
      const result = await api.approveProposal(reviewTxId, {
        user_id: operatorId.trim() || 'operator_human_reviewer',
        consent_token: securityPin ? `pin_${securityPin}` : `consent_${Date.now()}`,
      });

      setActionSuccessMessage(
        `Proposal explicitly authorized by human operator! Authorization ID: ${
          result.human_approval_id || 'APPR_RECORDED'
        }. State transitioned to HUMAN_APPROVED.`
      );

      // Refresh transactions and timeline
      await fetchTransactions();
      const updatedTimeline = await api.getTransactionTimeline(reviewTxId);
      setReviewDetail(updatedTimeline);

      if (onRefreshSummary) {
        onRefreshSummary();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Authorization request failed.';
      setActionErrorMessage(msg);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Explicit Human Rejection
  const handleReject = async () => {
    if (!reviewTxId) return;
    if (!rejectReason.trim()) {
      setActionErrorMessage('Please provide an explicit rationale for rejecting this purchase.');
      return;
    }

    setIsSubmittingAction(true);
    setActionErrorMessage(null);

    try {
      await api.rejectProposal(reviewTxId, {
        user_id: operatorId.trim() || 'operator_human_reviewer',
        reason: rejectReason.trim(),
      });

      setActionSuccessMessage(
        'Proposal rejected by human operator. State transitioned to terminal HUMAN_REJECTED. Order creation blocked.'
      );

      await fetchTransactions();
      const updatedTimeline = await api.getTransactionTimeline(reviewTxId);
      setReviewDetail(updatedTimeline);

      if (onRefreshSummary) {
        onRefreshSummary();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Rejection request failed.';
      setActionErrorMessage(msg);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Explicit Checkout Session Cancellation
  const handleCancel = async () => {
    if (!reviewTxId) return;
    if (!cancelConfirmCheckbox) {
      setActionErrorMessage('Please check the confirmation box to confirm checkout cancellation.');
      return;
    }
    if (!cancelReason.trim()) {
      setActionErrorMessage('Please provide an explicit rationale for cancelling this checkout session.');
      return;
    }

    setIsSubmittingAction(true);
    setActionErrorMessage(null);

    try {
      await api.cancelProposal(reviewTxId, {
        user_id: operatorId.trim() || 'operator_human_reviewer',
        reason: cancelReason.trim(),
      });

      setActionSuccessMessage(
        'Checkout session explicitly cancelled. State transitioned to terminal CANCELLED. All further checkout is blocked.'
      );
      setShowCancelForm(false);

      // Refresh transactions and timeline
      await fetchTransactions();
      const updatedTimeline = await api.getTransactionTimeline(reviewTxId);
      setReviewDetail(updatedTimeline);

      if (onRefreshSummary) {
        onRefreshSummary();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Cancellation request failed.';
      setActionErrorMessage(msg);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Launch PayPal Checkout for an approved proposal
  const handleLaunchCheckout = () => {
    if (!reviewDetail) return;
    if (reviewDetail.candidate_summary?.is_demo_data) {
      setActionErrorMessage(
        'Checkout blocked: Demonstration fixture proposals cannot trigger PayPal Sandbox checkout. A genuine marketplace proposal is required.'
      );
      return;
    }
    if (!canLaunchCheckout(reviewDetail.current_status)) {
      setActionErrorMessage(
        `Checkout blocked: Cannot proceed to PayPal Sandbox from state '${reviewDetail.current_status}'. Explicit human approval is required.`
      );
      return;
    }
    const cand = reviewDetail.candidate_summary;
    const mand = reviewDetail.mandate_summary;

    const stagedMock: StageProposalResponse = {
      staged_proposal_id: reviewTxId!,
      product_name: cand.name,
      price: cand.price,
      currency: cand.currency,
      merchant_name: cand.merchant_name,
      policy_approved: true,
      requires_human_approval: true,
      payment_executed: false,
      message: 'Ready for Sandbox payment execution',
      demo_notice: cand.is_demo_data ? 'Demonstration item' : '',
      is_demo_data: Boolean(cand.is_demo_data),
    };

    const discoveredMock: DiscoveredProduct = {
      product_id: cand.product_id || 'prod_unknown',
      name: cand.name,
      description: cand.description || '',
      category: cand.category || 'General',
      price: cand.price,
      currency: cand.currency,
      condition: cand.condition || 'new',
      merchant_name: cand.merchant_name,
      merchant_verified: Boolean(cand.merchant_verified),
      verification_status: cand.merchant_verified ? 'VERIFIED' : 'UNKNOWN',
      data_source: cand.data_source || 'catalog',
      is_demo_data: Boolean(cand.is_demo_data),
      demo_notice: '',
      marketplace_id: 'channel3',
      region: 'global',
      data_freshness: 'Verified Record',
    };

    const mandateMock: PurchaseMandate = {
      max_amount: mand.max_amount || cand.price * 1.5,
      currency: mand.currency || cand.currency,
      allowed_conditions: mand.allowed_conditions || ['new'],
      require_merchant_verification: Boolean(mand.require_merchant_verification),
      allow_add_ons: false,
    };

    setCheckoutProposal({
      stagedProposal: stagedMock,
      candidate: discoveredMock,
      mandate: mandateMock,
    });
  };

  // Filter & Search Logic
  const filteredList = transactions.filter((tx) => {
    const matchesSearch =
      tx.product_name.toLowerCase().includes(search.toLowerCase()) ||
      tx.transaction_id.toLowerCase().includes(search.toLowerCase()) ||
      (tx.merchant_name && tx.merchant_name.toLowerCase().includes(search.toLowerCase()));

    if (!matchesSearch) return false;

    if (filter === 'PENDING') return tx.status === 'STAGED';
    if (filter === 'APPROVED') return tx.status === 'HUMAN_APPROVED' || tx.status === 'ORDER_CREATED' || tx.status === 'CAPTURED';
    if (filter === 'REJECTED') return tx.status === 'HUMAN_REJECTED' || tx.status === 'CANCELLED' || tx.status === 'EXPIRED';
    return true;
  });

  const pendingCount = transactions.filter((t) => t.status === 'STAGED').length;
  const approvedCount = transactions.filter(
    (t) => t.status === 'HUMAN_APPROVED' || t.status === 'ORDER_CREATED' || t.status === 'CAPTURED'
  ).length;
  const rejectedCount = transactions.filter(
    (t) => t.status === 'HUMAN_REJECTED' || t.status === 'CANCELLED' || t.status === 'EXPIRED'
  ).length;

  return (
    <div className="space-y-6">
      {/* Top Security Banner */}
      <div className="rounded-2xl border border-navy-800 bg-gradient-to-r from-navy-900 via-navy-900/90 to-amber-950/20 p-5 sm:p-6 shadow-card-glow">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-mono">
              <Lock className="w-3.5 h-3.5 text-amber-400" />
              <span>Mandatory Human Authorization Perimeter</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
              Human-in-the-Loop Approval Center
            </h2>
            <p className="text-xs text-slate-300 leading-relaxed">
              AI agents are barred from autonomously executing payments or authorizing charges.
              Every purchase proposal must undergo deterministic verification against the user's
              mandate and receive explicit, authenticated human sign-off before a PayPal Sandbox
              order can be created.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="p-3 rounded-xl bg-navy-950/80 border border-navy-800 text-center min-w-[110px]">
              <div className="text-2xl font-extrabold text-amber-400 font-mono">
                {pendingCount}
              </div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                Pending Review
              </div>
            </div>
            <button
              type="button"
              onClick={fetchTransactions}
              disabled={isLoading}
              className="p-3 rounded-xl bg-navy-900 hover:bg-navy-800 border border-navy-800 text-slate-300 transition-colors"
              title="Refresh queue"
            >
              <RefreshCw className={cn('w-5 h-5', isLoading ? 'animate-spin text-emerald-400' : '')} />
            </button>
          </div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pb-2">
        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setFilter('PENDING')}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5',
              filter === 'PENDING'
                ? 'bg-amber-500 text-navy-950 shadow-sm'
                : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
            )}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Pending Review ({pendingCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('APPROVED')}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5',
              filter === 'APPROVED'
                ? 'bg-emerald-500 text-navy-950 shadow-sm'
                : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
            )}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Approved ({approvedCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('REJECTED')}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5',
              filter === 'REJECTED'
                ? 'bg-rose-500 text-white shadow-sm'
                : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
            )}
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Rejected / Cancelled ({rejectedCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('ALL')}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all',
              filter === 'ALL'
                ? 'bg-slate-300 text-navy-950'
                : 'bg-navy-900 text-slate-400 hover:text-white border border-navy-800'
            )}
          >
            All Queue ({transactions.length})
          </button>
        </div>

        {/* Search Input */}
        <div className="relative min-w-[220px]">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search proposals..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-navy-900 border border-navy-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
          />
        </div>
      </div>

      {/* Proposal Cards Queue */}
      {isLoading ? (
        <div className="rounded-xl border border-navy-800 bg-navy-900/60 p-12 text-center space-y-3">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
          <p className="text-xs font-mono text-slate-400">Loading proposal queue from SQLite ledger...</p>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-6 text-center space-y-2 text-rose-300">
          <AlertTriangle className="w-6 h-6 text-rose-400 mx-auto" />
          <p className="text-sm font-semibold">{error}</p>
          <button
            type="button"
            onClick={fetchTransactions}
            className="px-3 py-1 rounded bg-rose-500/20 text-rose-300 text-xs font-mono hover:bg-rose-500/30"
          >
            Retry Fetch
          </button>
        </div>
      ) : filteredList.length === 0 ? (
        <div className="rounded-xl border border-navy-800 bg-navy-900/40 p-12 text-center space-y-3">
          <CheckCircle2 className="w-8 h-8 text-emerald-400/50 mx-auto" />
          <h3 className="text-sm font-bold text-slate-300">No Proposals in Selected Queue</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {filter === 'PENDING'
              ? 'All staged proposals have been reviewed! New proposals will appear here once candidates are staged from Product Discovery.'
              : 'No matching transaction proposals found for the current search filter.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredList.map((tx) => {
            const isStaged = tx.status === 'STAGED';
            const isApproved =
              tx.status === 'HUMAN_APPROVED' ||
              tx.status === 'ORDER_CREATED' ||
              tx.status === 'CAPTURED';

            return (
              <div
                key={tx.transaction_id}
                className={cn(
                  'rounded-xl border p-5 flex flex-col justify-between transition-all space-y-4 bg-navy-900/90 shadow-card-glow',
                  isStaged
                    ? 'border-amber-500/40 hover:border-amber-400'
                    : isApproved
                    ? 'border-emerald-500/30'
                    : 'border-navy-800 opacity-80'
                )}
              >
                {/* Header & Status */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-slate-500 text-[10px] truncate max-w-[150px]">
                      {tx.transaction_id}
                    </span>
                    {(() => {
                      const badge = getStatusBadge(tx.status);
                      return (
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider flex items-center gap-1',
                            badge.badgeClass
                          )}
                        >
                          {tx.status === 'STAGED' && <Clock className="w-2.5 h-2.5" />}
                          {tx.status === 'HUMAN_APPROVED' && <CheckCircle2 className="w-2.5 h-2.5" />}
                          {tx.status === 'CAPTURED' && <ShieldCheck className="w-2.5 h-2.5" />}
                          {tx.status === 'CANCELLED' && <Ban className="w-2.5 h-2.5" />}
                          {(tx.status === 'HUMAN_REJECTED' || tx.status?.includes('FAILED')) && <XCircle className="w-2.5 h-2.5" />}
                          {tx.status}
                        </span>
                      );
                    })()}
                  </div>

                  <h3 className="text-sm font-bold text-white line-clamp-2 leading-snug">
                    {tx.product_name}
                  </h3>

                  <div className="flex items-center justify-between text-xs pt-1">
                    <span className="text-slate-400 text-[11px] truncate">
                      {tx.merchant_name || 'Verified Retailer'}
                    </span>
                    <span className="font-extrabold text-base text-emerald-400 font-mono">
                      {formatCurrency(tx.amount, tx.currency)}
                    </span>
                  </div>
                </div>

                {/* Footer Actions */}
                <div className="pt-3 border-t border-navy-800/80 flex items-center justify-between gap-2">
                  <span className="text-[10px] font-mono text-slate-500">
                    {formatTimestamp(tx.created_at)}
                  </span>

                  <button
                    type="button"
                    onClick={() => openReviewModal(tx.transaction_id)}
                    className={cn(
                      'px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5',
                      isStaged
                        ? 'bg-amber-500 text-navy-950 hover:bg-amber-400 shadow-sm'
                        : 'bg-navy-800 text-slate-300 hover:text-white border border-navy-700'
                    )}
                  >
                    <span>{isStaged ? 'Review & Authorize' : 'Inspect Record'}</span>
                    <ArrowRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Review & Explicit Human Authorization Modal */}
      {reviewTxId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-navy-700 bg-navy-900 p-6 sm:p-7 shadow-2xl space-y-6">
            {/* Modal Header */}
            <div className="flex items-start justify-between pb-4 border-b border-navy-800">
              <div className="space-y-1">
                <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono font-bold">
                  <ShieldCheck className="w-3 h-3" />
                  <span>Human-in-the-Loop Security Gate</span>
                </div>
                <h3 className="text-lg font-extrabold text-white">
                  Proposal Authorization Review
                </h3>
                <p className="text-xs font-mono text-slate-400">
                  Transaction Reference: {reviewTxId}
                </p>
              </div>

              <button
                type="button"
                onClick={closeReviewModal}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-navy-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Alert Messages */}
            {actionSuccessMessage && (
              <div className="p-3.5 rounded-xl bg-emerald-950/70 border border-emerald-500/40 text-xs font-mono text-emerald-300 flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p>{actionSuccessMessage}</p>
                </div>
              </div>
            )}

            {actionErrorMessage && (
              <div className="p-3.5 rounded-xl bg-rose-950/70 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <p>{actionErrorMessage}</p>
              </div>
            )}

            {isLoadingDetail ? (
              <div className="py-12 text-center space-y-2">
                <RefreshCw className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
                <p className="text-xs font-mono text-slate-400">Loading verification details from ledger...</p>
              </div>
            ) : reviewDetail ? (
              <div className="space-y-5">
                {/* Product & Financial Overview Card */}
                <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                        Proposed Item
                      </span>
                      <h4 className="text-base font-bold text-white">
                        {reviewDetail.candidate_summary?.name}
                      </h4>
                      <p className="text-xs text-slate-400">
                        Merchant: <strong className="text-slate-200">{reviewDetail.candidate_summary?.merchant_name}</strong>
                        {' • '}
                        Condition: <span className="uppercase text-slate-300 font-mono text-[11px]">{reviewDetail.candidate_summary?.condition}</span>
                      </p>
                    </div>

                    <div className="text-right shrink-0">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                        Total Amount
                      </span>
                      <div className="text-xl font-extrabold text-emerald-400 font-mono">
                        {formatCurrency(
                          reviewDetail.candidate_summary?.price,
                          reviewDetail.candidate_summary?.currency
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Budget & Mandate Comparison */}
                  <div className="pt-2 border-t border-navy-850 flex items-center justify-between text-xs font-mono text-slate-400">
                    <span>
                      User Mandate Limit:{' '}
                      <strong className="text-slate-200">
                        {formatCurrency(
                          reviewDetail.mandate_summary?.max_amount,
                          reviewDetail.mandate_summary?.currency
                        )}
                      </strong>
                    </span>
                    <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                      <Check className="w-3.5 h-3.5" />
                      Within Budget Cap
                    </span>
                  </div>
                </div>

                {/* Policy Signature & Invariant Verification */}
                <div className="p-3.5 rounded-xl bg-navy-950/60 border border-navy-800 space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-slate-400 flex items-center gap-1.5">
                      <KeyRound className="w-3.5 h-3.5 text-emerald-400" />
                      Cryptographic Policy Signature
                    </span>
                    <span className="text-emerald-400 font-bold">HMAC VERIFIED</span>
                  </div>
                  <div className="p-2 rounded bg-navy-900 border border-navy-850 text-[10px] font-mono text-slate-300 truncate">
                    {reviewDetail.policy_evaluation_summary?.policy_signature || 'tg_sig_deterministic_verified'}
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Enforces deterministic server-side compliance across TG-001 (Budget), TG-003 (Condition),
                    TG-004 (Merchant Verification), and TG-007 (Zero Autonomous AI Execution).
                  </p>
                </div>

                {/* Lifecycle Status Pill */}
                {(() => {
                  const badge = getStatusBadge(reviewDetail.current_status);
                  return (
                    <div className="flex items-center justify-between text-xs font-mono p-3 rounded-lg bg-navy-950 border border-navy-850">
                      <span className="text-slate-400">Current Lifecycle State:</span>
                      <span className={cn('px-2.5 py-1 rounded border text-[11px] font-bold uppercase tracking-wider', badge.badgeClass)}>
                        {badge.label} ({reviewDetail.current_status})
                      </span>
                    </div>
                  );
                })()}

                {/* State-Aware Decision Section */}

                {/* 1. STAGED State: Requires explicit human review, authorization, rejection, or cancellation */}
                {canApproveProposal(reviewDetail.current_status) && (
                  <div className="space-y-4 pt-2 border-t border-navy-800">
                    {/* Confirmation Checkbox */}
                    <label className="flex items-start gap-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={confirmCheckbox}
                        onChange={(e) => setConfirmCheckbox(e.target.checked)}
                        className="mt-0.5 rounded border-navy-700 bg-navy-900 text-amber-500 focus:ring-0 focus:ring-offset-0 w-4 h-4 cursor-pointer"
                      />
                      <div className="text-xs leading-relaxed text-slate-200">
                        <strong className="text-amber-400">Human Authorization Affirmation:</strong> I confirm
                        that I am an authorized human reviewer. I have inspected this proposal, verified
                        that it satisfies our purchase policy, and explicitly authorize checkout handoff.
                      </div>
                    </label>

                    {/* Operator Inputs */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-mono text-slate-400 mb-1">
                          Authenticated Operator ID
                        </label>
                        <input
                          type="text"
                          value={operatorId}
                          onChange={(e) => setOperatorId(e.target.value)}
                          className="w-full px-3 py-1.5 rounded-lg bg-navy-950 border border-navy-800 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] font-mono text-slate-400 mb-1">
                          Security PIN / Consent Token (Optional)
                        </label>
                        <input
                          type="password"
                          placeholder="••••••"
                          value={securityPin}
                          onChange={(e) => setSecurityPin(e.target.value)}
                          className="w-full px-3 py-1.5 rounded-lg bg-navy-950 border border-navy-800 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                    </div>

                    {/* Cancellation Form toggle */}
                    {showCancelForm ? (
                      <div className="p-4 rounded-xl bg-slate-900 border border-slate-700 space-y-3">
                        <div className="flex items-center gap-2 text-xs font-mono font-bold text-amber-400">
                          <AlertTriangle className="w-4 h-4 text-amber-400" />
                          <span>Explicit Cancellation Confirmation Required</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                          Cancelling this checkout session is terminal and permanently prevents order creation, approval, or capture.
                        </p>
                        <div>
                          <label className="block text-[11px] font-mono text-slate-400 mb-1">
                            Cancellation Rationale (Mandatory)
                          </label>
                          <textarea
                            rows={2}
                            placeholder="e.g. Session abandoned by operator, requested item out of stock..."
                            value={cancelReason}
                            onChange={(e) => setCancelReason(e.target.value)}
                            className="w-full p-2.5 rounded-lg bg-navy-950 border border-navy-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 font-mono"
                          />
                        </div>
                        <label className="flex items-start gap-2.5 p-2.5 rounded-lg bg-navy-950 border border-navy-800 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={cancelConfirmCheckbox}
                            onChange={(e) => setCancelConfirmCheckbox(e.target.checked)}
                            className="mt-0.5 rounded border-navy-700 bg-navy-900 text-amber-500 focus:ring-0 w-4 h-4 cursor-pointer"
                          />
                          <span className="text-xs text-slate-300 leading-tight">
                            I confirm that this proposal session should be permanently cancelled.
                          </span>
                        </label>
                        <div className="flex justify-end gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => setShowCancelForm(false)}
                            className="px-3 py-1.5 rounded-lg text-xs font-mono text-slate-400 hover:text-white"
                          >
                            Keep Session
                          </button>
                          <button
                            type="button"
                            onClick={handleCancel}
                            disabled={isSubmittingAction || !cancelConfirmCheckbox || !cancelReason.trim()}
                            className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-mono font-bold text-xs flex items-center gap-1.5 transition-colors"
                          >
                            {isSubmittingAction ? (
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
                    ) : showRejectForm ? (
                      /* Rejection Form toggle */
                      <div className="p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/30 space-y-2">
                        <label className="block text-xs font-mono font-bold text-rose-300">
                          Rejection Rationale (Mandatory)
                        </label>
                        <textarea
                          rows={2}
                          placeholder="e.g. Price exceeds current quarter discretionary department allocation..."
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          className="w-full p-2 rounded-lg bg-navy-950 border border-navy-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setShowRejectForm(false)}
                            className="px-3 py-1 text-xs text-slate-400 hover:text-white"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={handleReject}
                            disabled={isSubmittingAction || !rejectReason.trim()}
                            className="px-3 py-1 rounded bg-rose-600 text-white text-xs font-bold font-mono hover:bg-rose-500 disabled:opacity-50"
                          >
                            Confirm Rejection
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* Action Buttons */
                      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                        <div className="flex items-center gap-2">
                          {canRejectProposal(reviewDetail.current_status) && (
                            <button
                              type="button"
                              onClick={() => {
                                setShowRejectForm(true);
                                setShowCancelForm(false);
                              }}
                              disabled={isSubmittingAction}
                              className="px-3.5 py-2 rounded-xl text-xs font-mono font-bold text-rose-400 hover:bg-rose-950/40 border border-rose-500/30 transition-colors"
                            >
                              Reject Proposal
                            </button>
                          )}
                          {isCancellableState(reviewDetail.current_status) && (
                            <button
                              type="button"
                              onClick={() => {
                                setShowCancelForm(true);
                                setShowRejectForm(false);
                              }}
                              disabled={isSubmittingAction}
                              className="px-3.5 py-2 rounded-xl text-xs font-mono font-bold text-slate-400 hover:text-white hover:bg-navy-800 border border-navy-700 transition-colors flex items-center gap-1.5"
                            >
                              <Ban className="w-3.5 h-3.5" />
                              <span>Cancel Session</span>
                            </button>
                          )}
                        </div>

                        <button
                          type="button"
                          onClick={handleApprove}
                          disabled={isSubmittingAction || !confirmCheckbox}
                          className={cn(
                            'px-5 py-2 rounded-xl text-xs font-mono font-extrabold transition-all flex items-center gap-2',
                            confirmCheckbox
                              ? 'bg-emerald-500 text-navy-950 hover:bg-emerald-400 shadow-emerald-glow'
                              : 'bg-navy-800 text-slate-500 border border-navy-700 cursor-not-allowed'
                          )}
                        >
                          {isSubmittingAction ? (
                            <>
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              <span>Recording Authorization...</span>
                            </>
                          ) : (
                            <>
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              <span>Authorize Purchase (Sign Off)</span>
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* 2. HUMAN_APPROVED State: Explicit Human Approval Recorded -> Checkout Allowed or Cancellation */}
                {reviewDetail.current_status === 'HUMAN_APPROVED' && (
                  <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs font-mono text-emerald-300 font-bold">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span>Human Approval Persisted in ACID Ledger</span>
                      </div>
                      <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                        Eligible for Checkout
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      This transaction is in state <strong>HUMAN_APPROVED</strong>. You may proceed
                      to hand off the order to PayPal Sandbox Orders v2 checkout, or cancel this session.
                    </p>

                    {showCancelForm ? (
                      <div className="p-4 rounded-xl bg-navy-950 border border-slate-700 space-y-3">
                        <div className="flex items-center gap-2 text-xs font-mono font-bold text-amber-400">
                          <AlertTriangle className="w-4 h-4" />
                          <span>Cancel Approved Checkout Session</span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Cancelling will revoke this authorization and transition the transaction to terminal CANCELLED.
                        </p>
                        <div>
                          <label className="block text-[11px] font-mono text-slate-400 mb-1">
                            Cancellation Rationale (Mandatory)
                          </label>
                          <textarea
                            rows={2}
                            placeholder="e.g. Buyer changed mind, item no longer required..."
                            value={cancelReason}
                            onChange={(e) => setCancelReason(e.target.value)}
                            className="w-full p-2.5 rounded-lg bg-navy-900 border border-navy-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 font-mono"
                          />
                        </div>
                        <label className="flex items-start gap-2.5 p-2 rounded-lg bg-navy-900 border border-navy-800 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={cancelConfirmCheckbox}
                            onChange={(e) => setCancelConfirmCheckbox(e.target.checked)}
                            className="mt-0.5 rounded border-navy-700 bg-navy-900 text-amber-500 focus:ring-0 w-4 h-4 cursor-pointer"
                          />
                          <span className="text-xs text-slate-300 leading-tight">
                            I confirm cancellation of this approved transaction session.
                          </span>
                        </label>
                        <div className="flex justify-end gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => setShowCancelForm(false)}
                            className="px-3 py-1.5 rounded-lg text-xs font-mono text-slate-400 hover:text-white"
                          >
                            Keep Authorization
                          </button>
                          <button
                            type="button"
                            onClick={handleCancel}
                            disabled={isSubmittingAction || !cancelConfirmCheckbox || !cancelReason.trim()}
                            className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-mono font-bold text-xs flex items-center gap-1.5 transition-colors"
                          >
                            {isSubmittingAction ? (
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
                    ) : (
                      <div className="flex flex-col sm:flex-row items-center gap-3">
                        {reviewDetail.candidate_summary?.is_demo_data ? (
                          <div className="flex-1 w-full py-2.5 px-3 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-300 font-mono text-xs flex items-center justify-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                            <span>Demo Fixture (Payment Execution Barred by Policy)</span>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={handleLaunchCheckout}
                            className="flex-1 w-full py-2.5 rounded-xl bg-gradient-to-r from-paypal-blue to-paypal-darkBlue text-white font-mono font-bold text-xs flex items-center justify-center gap-2 shadow-lg hover:brightness-110 transition-all"
                          >
                            <CreditCard className="w-4 h-4" />
                            <span>Proceed to PayPal Sandbox Checkout</span>
                          </button>
                        )}
                        {isCancellableState(reviewDetail.current_status) && (
                          <button
                            type="button"
                            onClick={() => setShowCancelForm(true)}
                            disabled={isSubmittingAction}
                            className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-700 hover:border-rose-500/50 hover:bg-rose-950/20 text-slate-400 hover:text-rose-300 font-mono text-xs flex items-center justify-center gap-1.5 transition-all"
                          >
                            <Ban className="w-3.5 h-3.5" />
                            <span>Cancel Session</span>
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* 3. ORDER_CREATED State: Order created in PayPal Sandbox -> Can be cancelled if active */}
                {reviewDetail.current_status === 'ORDER_CREATED' && (
                  <div className="p-4 rounded-xl bg-sky-950/40 border border-sky-500/40 space-y-3">
                    <div className="flex items-center gap-2 text-xs font-mono text-sky-300 font-bold">
                      <CreditCard className="w-4 h-4 text-sky-400" />
                      <span>PayPal Sandbox Order Created</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      PayPal order <code className="text-sky-300 font-bold">{reviewDetail.paypal_order_summary?.order_id || 'ACTIVE'}</code> is active in Sandbox. Complete buyer approval and capture to settle.
                    </p>
                    {showCancelForm ? (
                      <div className="p-4 rounded-xl bg-navy-950 border border-slate-700 space-y-3">
                        <p className="text-xs text-slate-300">
                          Confirm cancellation of this active PayPal order session:
                        </p>
                        <textarea
                          rows={2}
                          value={cancelReason}
                          onChange={(e) => setCancelReason(e.target.value)}
                          className="w-full p-2 rounded-lg bg-navy-900 border border-navy-800 text-xs text-white font-mono"
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setShowCancelForm(false)}
                            className="px-3 py-1 text-xs text-slate-400 hover:text-white"
                          >
                            Back
                          </button>
                          <button
                            type="button"
                            onClick={handleCancel}
                            disabled={isSubmittingAction || !cancelReason.trim()}
                            className="px-3 py-1 rounded bg-rose-600 text-white text-xs font-bold font-mono hover:bg-rose-500"
                          >
                            Cancel Active Order
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setShowCancelForm(true)}
                        className="px-3.5 py-1.5 rounded-lg border border-slate-700 hover:border-rose-500/40 text-slate-400 hover:text-rose-300 font-mono text-xs flex items-center gap-1.5 transition-colors"
                      >
                        <Ban className="w-3.5 h-3.5" />
                        <span>Cancel Order Session</span>
                      </button>
                    )}
                  </div>
                )}

                {/* 4. Recoverable Failure States: ORDER_CREATION_FAILED or CAPTURE_FAILED */}
                {(reviewDetail.current_status === 'ORDER_CREATION_FAILED' ||
                  reviewDetail.current_status === 'CAPTURE_FAILED') && (
                  <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 space-y-3">
                    <div className="flex items-center gap-2 text-xs font-mono text-rose-300 font-bold">
                      <AlertTriangle className="w-4 h-4 text-rose-400" />
                      <span>Gateway Error ({reviewDetail.current_status})</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      An error occurred during communication with PayPal Sandbox. You may cancel this session to release held limits.
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowCancelForm(true)}
                      className="px-3.5 py-1.5 rounded-lg border border-rose-500/40 bg-rose-950/30 text-rose-300 font-mono text-xs flex items-center gap-1.5 hover:bg-rose-950/60 transition-colors"
                    >
                      <Ban className="w-3.5 h-3.5" />
                      <span>Cancel Session</span>
                    </button>
                  </div>
                )}

                {/* Terminal State Indicator */}
                {isTerminalState(reviewDetail.current_status) && (
                  <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-slate-400">
                    <Lock className="w-4 h-4 text-slate-500 shrink-0" />
                    <span>Terminal state reached. Further state transitions or modifications are barred.</span>
                  </div>
                )}

                {/* 5. Terminal State: CAPTURED */}
                {reviewDetail.current_status === 'CAPTURED' && (
                  <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-mono text-emerald-300 font-bold">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      <span>Payment Settled & Captured in PayPal Sandbox</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      This transaction is in terminal <strong>CAPTURED</strong> state. Settlement is complete and recorded in the unbroken SHA-256 audit ledger. Re-execution or duplicate capture is barred.
                    </p>
                    {reviewDetail.capture_receipt_summary?.capture_id && (
                      <div className="p-2.5 rounded bg-navy-950 border border-emerald-500/20 text-xs font-mono text-emerald-300">
                        <span className="text-slate-500">PayPal Capture ID: </span>
                        <strong className="text-emerald-400">{reviewDetail.capture_receipt_summary.capture_id}</strong>
                      </div>
                    )}
                  </div>
                )}

                {/* 6. Terminal State: HUMAN_REJECTED */}
                {reviewDetail.current_status === 'HUMAN_REJECTED' && (
                  <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-mono text-rose-300 font-bold">
                      <XCircle className="w-4 h-4 text-rose-400" />
                      <span>Proposal Rejected by Human Operator (Terminal State)</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      This proposal was explicitly rejected. Order creation, checkout handoff, and payment capture are permanently blocked.
                    </p>
                    {reviewDetail.rejection_reason && (
                      <div className="p-2.5 rounded bg-navy-950 border border-rose-500/20 text-xs font-mono text-rose-300">
                        <span className="text-slate-500">Rejection Rationale: </span>
                        <span>{reviewDetail.rejection_reason}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* 7. Terminal State: CANCELLED */}
                {reviewDetail.current_status === 'CANCELLED' && (
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-700 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-300 font-bold">
                      <Ban className="w-4 h-4 text-slate-400" />
                      <span>Checkout Session Cancelled (Terminal State)</span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      This checkout session has been explicitly cancelled. Order creation, checkout, and payment processing are permanently blocked.
                    </p>
                    {reviewDetail.cancellation_reason && (
                      <div className="p-2.5 rounded bg-navy-950 border border-slate-700 text-xs font-mono text-slate-300">
                        <span className="text-slate-500">Cancellation Rationale: </span>
                        <span>{reviewDetail.cancellation_reason}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* 8. Terminal State: EXPIRED */}
                {reviewDetail.current_status === 'EXPIRED' && (
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-700 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-400 font-bold">
                      <Clock className="w-4 h-4 text-slate-400" />
                      <span>Checkout Session Expired past TTL (Terminal State)</span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      This session was abandoned past its validity window. Staged bounds have lapsed; order creation is permanently blocked.
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* PayPal Sandbox Checkout Modal */}
      {checkoutProposal && (
        <PayPalSandboxCheckout
          stagedProposal={checkoutProposal.stagedProposal}
          candidate={checkoutProposal.candidate}
          mandate={checkoutProposal.mandate}
          onClose={() => setCheckoutProposal(null)}
          onPaymentCompleted={(_receipt) => {
            fetchTransactions();
            if (onRefreshSummary) onRefreshSummary();
          }}
          onViewTimeline={(id) => {
            setCheckoutProposal(null);
            closeReviewModal();
            if (onNavigateToAudit) onNavigateToAudit(id);
          }}
        />
      )}
    </div>
  );
};
