import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldCheck,
  CreditCard,
  Lock,
  AlertTriangle,
  CheckCircle2,
  X,
  ExternalLink,
  RefreshCw,
  Info,
  FileCheck2,
  KeyRound,
} from 'lucide-react';
import {
  StageProposalResponse,
  DiscoveredProduct,
  PurchaseMandate,
  PaymentConfigResponse,
  CaptureOrderResponse,
} from '../types';
import { api } from '../lib/api';

declare global {
  interface Window {
    paypal?: any;
  }
}

interface PayPalSandboxCheckoutProps {
  stagedProposal: StageProposalResponse;
  candidate: DiscoveredProduct;
  mandate: PurchaseMandate;
  onClose: () => void;
  onPaymentCompleted?: (receipt: CaptureOrderResponse) => void;
  onViewTimeline?: (stagedProposalId: string) => void;
}

export const PayPalSandboxCheckout: React.FC<PayPalSandboxCheckoutProps> = ({
  stagedProposal,
  candidate,
  mandate,
  onClose,
  onPaymentCompleted,
  onViewTimeline,
}) => {
  const [config, setConfig] = useState<PaymentConfigResponse | null>(null);
  const [isLoadingConfig, setIsLoadingConfig] = useState<boolean>(true);
  const [configError, setConfigError] = useState<string | null>(null);

  const [isSdkReady, setIsSdkReady] = useState<boolean>(false);
  const [sdkLoadError, setSdkLoadError] = useState<string | null>(null);

  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [isCancelled, setIsCancelled] = useState<boolean>(false);

  const [captureReceipt, setCaptureReceipt] = useState<CaptureOrderResponse | null>(null);
  const paypalButtonContainerRef = useRef<HTMLDivElement>(null);

  // Fetch PayPal Sandbox public configuration
  const fetchConfig = async () => {
    setIsLoadingConfig(true);
    setConfigError(null);
    try {
      const cfg = await api.getPaymentConfig();
      setConfig(cfg);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load PayPal Sandbox configuration.';
      setConfigError(msg);
    } finally {
      setIsLoadingConfig(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // Dynamically load the official PayPal JavaScript SDK
  useEffect(() => {
    if (!config?.configured || !config?.client_id) {
      return;
    }

    const currency = candidate.currency.toUpperCase() || 'USD';
    const scriptId = 'paypal-sdk-script';

    // Remove old script if currency/client_id changed
    const existing = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (existing) {
      if (existing.src.includes(config.client_id) && existing.src.includes(currency)) {
        if (window.paypal) {
          setIsSdkReady(true);
          return;
        }
      } else {
        existing.remove();
      }
    }

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(
      config.client_id
    )}&currency=${encodeURIComponent(currency)}&intent=capture`;
    script.async = true;

    script.onload = () => {
      setIsSdkReady(true);
      setSdkLoadError(null);
    };

    script.onerror = () => {
      setSdkLoadError('Failed to load the official PayPal Sandbox JavaScript SDK.');
      setIsSdkReady(false);
    };

    document.body.appendChild(script);
  }, [config, candidate.currency]);

  // Render official PayPal Buttons into container when SDK is ready
  useEffect(() => {
    if (!isSdkReady || !window.paypal || !paypalButtonContainerRef.current || captureReceipt) {
      return;
    }

    // Clean previous buttons
    paypalButtonContainerRef.current.innerHTML = '';

    try {
      window.paypal
        .Buttons({
          createOrder: async () => {
            setIsProcessing(true);
            setCheckoutError(null);
            setIsCancelled(false);
            try {
              const res = await api.createPaymentOrder(stagedProposal.staged_proposal_id);
              return res.order_id;
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : 'Failed to create PayPal Sandbox order.';
              setCheckoutError(msg);
              throw err;
            } finally {
              setIsProcessing(false);
            }
          },
          onApprove: async (data: { orderID: string }) => {
            setIsProcessing(true);
            setCheckoutError(null);
            try {
              const receipt = await api.capturePaymentOrder(data.orderID);
              setCaptureReceipt(receipt);
              if (onPaymentCompleted) {
                onPaymentCompleted(receipt);
              }
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : 'Server-side capture verification failed.';
              setCheckoutError(msg);
            } finally {
              setIsProcessing(false);
            }
          },
          onCancel: () => {
            setIsCancelled(true);
            setIsProcessing(false);
          },
          onError: (err: unknown) => {
            console.error('PayPal button error:', err);
            setCheckoutError('PayPal Sandbox checkout encountered an issue. Please try again.');
            setIsProcessing(false);
          },
          style: {
            layout: 'vertical',
            color: 'gold',
            shape: 'rect',
            label: 'paypal',
          },
        })
        .render(paypalButtonContainerRef.current);
    } catch (renderErr) {
      console.error('Error rendering PayPal button:', renderErr);
    }
  }, [isSdkReady, stagedProposal.staged_proposal_id, captureReceipt]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-2xl rounded-2xl border border-emerald-500/50 bg-navy-900 p-6 shadow-card-glow space-y-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-navy-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <CreditCard className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white font-mono">
                  PayPal Sandbox Checkout
                </h3>
                <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-mono font-bold">
                  SANDBOX TEST
                </span>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Explicit Human-in-the-Loop Approval Required
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 transition-all"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ------------------------------------------------------------------ */}
        {/* VIEW 1: POST-CAPTURE VERIFIED RECEIPT */}
        {/* ------------------------------------------------------------------ */}
        {captureReceipt ? (
          <div className="space-y-6 animate-in fade-in duration-300">
            {/* Success Banner */}
            <div className="p-4 rounded-xl bg-emerald-950/70 border border-emerald-500/50 text-emerald-300 flex items-start gap-3 shadow-emerald-glow">
              <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold text-sm text-white font-mono block">
                  Payment Captured Successfully (PayPal Sandbox)
                </span>
                <p className="text-xs text-emerald-300/90 leading-relaxed font-mono">
                  {captureReceipt.receipt_notice}
                </p>
              </div>
            </div>

            {/* Itemized Receipt Details */}
            <div className="p-5 rounded-xl bg-navy-950 border border-navy-800 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between border-b border-navy-800 pb-2">
                <span className="text-slate-400 uppercase text-[10px]">Transaction Status</span>
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30">
                  {captureReceipt.status}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Item Purchased:</span>
                <span className="text-white font-bold">{captureReceipt.product_name}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Merchant:</span>
                <span className="text-slate-200">{captureReceipt.merchant_name}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Amount Captured:</span>
                <span className="text-emerald-400 font-bold text-sm">
                  {captureReceipt.currency} {captureReceipt.amount.toFixed(2)}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">PayPal Order ID:</span>
                <code className="text-slate-200 select-all">{captureReceipt.order_id}</code>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">PayPal Capture ID:</span>
                <code className="text-slate-200 select-all">{captureReceipt.capture_id}</code>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Staged Proposal ID:</span>
                <code className="text-slate-400">{captureReceipt.staged_proposal_id}</code>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Timestamp:</span>
                <span className="text-slate-300">{captureReceipt.captured_at}</span>
              </div>

              <div className="flex items-center justify-between border-t border-navy-800 pt-2">
                <span className="text-slate-400">TrustGate Policy Signature:</span>
                <code className="text-[11px] text-emerald-400 truncate max-w-xs">
                  {captureReceipt.policy_signature}
                </code>
              </div>
            </div>

            {/* Invariant Confirmation Notice */}
            <div className="p-3.5 rounded-xl bg-navy-950/60 border border-navy-800 text-[11px] font-mono text-slate-400 space-y-1">
              <div className="flex items-center gap-1.5 text-slate-200 font-bold">
                <FileCheck2 className="w-4 h-4 text-emerald-400" />
                <span>Security Invariant Audit: TG-007 Enforced</span>
              </div>
              <p className="leading-relaxed">
                Autonomous AI execution was strictly blocked. The order was created and captured
                only following human buyer authorization in the PayPal Sandbox portal.
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <span className="text-[11px] font-mono text-slate-500">
                Verified Backend Receipt
              </span>
              <div className="flex items-center gap-3">
                {onViewTimeline && (
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onViewTimeline(captureReceipt.staged_proposal_id);
                    }}
                    className="px-4 py-2.5 rounded-xl bg-navy-800 hover:bg-navy-750 text-slate-200 font-mono text-xs border border-navy-700 transition-all flex items-center gap-1.5"
                  >
                    <ExternalLink className="w-3.5 h-3.5 text-emerald-400" />
                    <span>View Audit Timeline</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={onClose}
                  className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-xs font-mono shadow-emerald-glow transition-all"
                >
                  Close Receipt
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* ------------------------------------------------------------------ */
          /* VIEW 2: CHECKOUT REVIEW & HUMAN AUTHORIZATION GATE */
          /* ------------------------------------------------------------------ */
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* Safety Statement: AI cannot authorize payments */}
            <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-500/40 text-xs font-mono text-amber-300 space-y-1.5">
              <div className="flex items-center gap-2 font-bold text-amber-200">
                <Lock className="w-4 h-4 text-amber-400 shrink-0" />
                <span>Security Guardrail: AI Cannot Authorize Payments</span>
              </div>
              <p className="text-amber-300/90 leading-relaxed text-[11px]">
                The AI model has zero payment authorization privilege. TrustGate mathematically
                revalidates candidate data against your purchase mandate immediately before
                creating the PayPal Sandbox order. Explicit human checkout is mandatory.
              </p>
            </div>

            {/* Candidate & Mandate Review Card */}
            <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 space-y-3 font-mono text-xs">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="text-[10px] uppercase text-slate-500 block">Proposed Product</span>
                  <span className="text-white font-bold text-sm block">{candidate.name}</span>
                  <span className="text-slate-400 text-[11px] block mt-0.5">
                    Merchant: <strong className="text-slate-200">{candidate.merchant_name}</strong>{' '}
                    {candidate.merchant_verified && (
                      <span className="text-emerald-400 font-semibold">(Verified)</span>
                    )}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] uppercase text-slate-500 block">Total Checkout</span>
                  <span className="text-emerald-400 font-bold text-base">
                    {candidate.currency} {candidate.price.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Data Source & Mandate Breakdown */}
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-navy-800/80 text-[11px]">
                <div className="p-2 rounded bg-navy-900 border border-navy-800">
                  <span className="text-slate-500 block text-[9px] uppercase">Catalog Source</span>
                  <span className="text-slate-300 font-semibold truncate block">
                    {candidate.is_demo_data ? 'Demo Fixture (Simulated)' : candidate.data_source}
                  </span>
                </div>

                <div className="p-2 rounded bg-navy-900 border border-navy-800">
                  <span className="text-slate-500 block text-[9px] uppercase">Mandate Budget</span>
                  <span className="text-emerald-300 font-semibold">
                    {mandate.currency} {mandate.max_amount.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Invariant Status Check */}
              <div className="flex items-center justify-between text-[11px] pt-1">
                <span className="text-slate-400">Deterministic Policy Engine:</span>
                <span className="inline-flex items-center gap-1 text-emerald-400 font-bold">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  APPROVED FOR SANDBOX CHECKOUT
                </span>
              </div>
            </div>

            {/* Error banners */}
            {configError && (
              <div className="p-3.5 rounded-lg bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{configError}</span>
                </div>
                <button
                  type="button"
                  onClick={fetchConfig}
                  className="px-2.5 py-1 rounded bg-rose-900/50 hover:bg-rose-900 border border-rose-700/60 text-[11px] font-bold text-white shrink-0"
                >
                  Retry
                </button>
              </div>
            )}

            {checkoutError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{checkoutError}</span>
              </div>
            )}

            {isCancelled && (
              <div className="p-3 rounded-lg bg-amber-950/60 border border-amber-500/40 text-xs font-mono text-amber-300 flex items-center gap-2">
                <Info className="w-4 h-4 text-amber-400 shrink-0" />
                <span>Payment was cancelled by the buyer in PayPal Sandbox. No funds were captured.</span>
              </div>
            )}

            {sdkLoadError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300">
                {sdkLoadError}
              </div>
            )}

            {/* Loading Configuration State */}
            {isLoadingConfig && (
              <div className="p-8 text-center text-xs font-mono text-slate-400 space-y-2">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto text-emerald-400" />
                <span>Connecting to PayPal Sandbox Gateway...</span>
              </div>
            )}

            {/* CASE A: Sandbox Not Configured */}
            {!isLoadingConfig && config && !config.configured && (
              <div className="rounded-xl border border-amber-500/40 bg-navy-950/90 p-5 space-y-3 font-mono text-xs">
                <div className="flex items-center gap-2 font-bold text-amber-300">
                  <KeyRound className="w-4 h-4 text-amber-400" />
                  <span>PayPal Sandbox Not Configured</span>
                </div>
                <p className="text-slate-300 text-[11px] leading-relaxed">
                  Real Sandbox checkout requires official client credentials. TrustGate enforces
                  integrity: we never generate fake receipts or fabricate payment success without a
                  verified server-side PayPal capture response.
                </p>

                <div className="p-3 rounded bg-navy-900 border border-navy-800 text-[11px] space-y-1.5">
                  <span className="text-slate-200 font-bold block">
                    Setup instructions in <code className="text-emerald-400">backend/.env</code>:
                  </span>
                  <pre className="text-[10px] text-slate-400 overflow-x-auto p-2 bg-navy-950 rounded">
                    {`PAYPAL_ENV=sandbox\nPAYPAL_CLIENT_ID=your_sandbox_client_id\nPAYPAL_CLIENT_SECRET=your_sandbox_client_secret`}
                  </pre>
                  <a
                    href="https://developer.paypal.com/dashboard/applications/sandbox"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:underline pt-1"
                  >
                    <span>Get free PayPal Sandbox credentials at developer.paypal.com</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            )}

            {/* CASE B: Sandbox Configured — Render Official PayPal Button */}
            {!isLoadingConfig && config?.configured && (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>Authorized Sandbox Buyer Checkout:</span>
                  <span className="text-emerald-400 font-semibold">Mode: PayPal Sandbox</span>
                </div>

                {isProcessing && (
                  <div className="p-3 rounded-xl bg-navy-950 border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center justify-center gap-2 animate-pulse">
                    <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                    <span>Communicating with PayPal Sandbox (Server-Side Invariants Active)...</span>
                  </div>
                )}

                {/* PayPal JS SDK Render Target */}
                <div
                  ref={paypalButtonContainerRef}
                  className="min-h-[50px] rounded-xl overflow-hidden"
                />

                {!isSdkReady && !sdkLoadError && (
                  <div className="p-4 text-center text-xs font-mono text-slate-400">
                    Loading PayPal Sandbox Buttons...
                  </div>
                )}
              </div>
            )}

            {/* Footer Notice */}
            <div className="flex items-center justify-between pt-2 border-t border-navy-800/80 text-[11px] font-mono text-slate-500">
              <span>Prototype Sandbox Only • No Real Charges</span>
              <button
                type="button"
                onClick={onClose}
                className="text-slate-400 hover:text-white transition-all underline"
              >
                Cancel & Return
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
