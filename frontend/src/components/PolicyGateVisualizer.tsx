import React from 'react';
import {
  ShieldCheck,
  ShieldX,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Lock,
  UserCheck,
  CreditCard,
  Key,
  FileCheck,
  RefreshCw,
} from 'lucide-react';
import { PolicyEvaluationResponse, ProductProposal } from '../types';
import { formatCurrency, cn } from '../lib/utils';

interface PolicyGateVisualizerProps {
  policyResult: PolicyEvaluationResponse | null;
  product: ProductProposal | null;
  budgetLimit: number;
  isLoading: boolean;
  humanApproved: boolean;
  onRunVerification: (callerRole?: string, simulatedPrice?: number) => void;
  onGrantApproval: () => void;
}

export const PolicyGateVisualizer: React.FC<PolicyGateVisualizerProps> = ({
  policyResult,
  product,
  budgetLimit,
  isLoading,
  humanApproved,
  onRunVerification,
  onGrantApproval,
}) => {
  if (!product && !policyResult) {
    return (
      <div className="rounded-xl border border-navy-800 bg-navy-900/60 p-8 text-center">
        <Lock className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <h3 className="text-sm font-semibold text-slate-300">Policy Gate Inactive</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          Submit purchasing instructions above to trigger Grok recommendation and run deterministic rule evaluations.
        </p>
      </div>
    );
  }

  const passed = policyResult?.passed ?? false;
  const isAwaitingHuman = passed && !humanApproved;
  const isCheckoutReady = passed && humanApproved;

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-6 space-y-5">
      {/* Visual Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-navy-800 gap-3">
        <div className="flex items-center gap-2.5">
          <div
            className={cn(
              'p-2 rounded-lg border',
              passed
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                : policyResult
                ? 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                : 'bg-navy-800 border-navy-700 text-slate-400'
            )}
          >
            {passed ? (
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            ) : policyResult ? (
              <ShieldX className="w-5 h-5 text-rose-400" />
            ) : (
              <Lock className="w-5 h-5" />
            )}
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Deterministic TrustGate Policy Engine
            </h2>
            <p className="text-xs text-slate-400">
              Mathematical boundary checks outside of LLM reasoning. Budget Cap: {formatCurrency(budgetLimit)}.
            </p>
          </div>
        </div>

        {/* Security Simulation Controls */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => onRunVerification('human_user')}
            disabled={isLoading}
            className="px-2.5 py-1.5 rounded-lg bg-navy-850 hover:bg-navy-800 border border-navy-700 text-xs text-slate-300 hover:text-emerald-300 font-mono transition-colors flex items-center gap-1.5"
            title="Re-run standard compliant verification"
          >
            <RefreshCw className={cn('w-3 h-3', isLoading && 'animate-spin')} />
            <span>Verify Standard</span>
          </button>

          <button
            type="button"
            onClick={() => onRunVerification('human_user', 499.0)}
            disabled={isLoading}
            className="px-2.5 py-1.5 rounded-lg bg-amber-950/40 hover:bg-amber-900/40 border border-amber-800/50 text-[11px] text-amber-300 font-mono transition-colors flex items-center gap-1"
            title="Simulate a price that exceeds user budget to test interception"
          >
            <AlertTriangle className="w-3 h-3" />
            <span>Test Budget Breach</span>
          </button>

          <button
            type="button"
            onClick={() => onRunVerification('ai_agent')}
            disabled={isLoading}
            className="px-2.5 py-1.5 rounded-lg bg-rose-950/40 hover:bg-rose-900/40 border border-rose-800/50 text-[11px] text-rose-300 font-mono transition-colors flex items-center gap-1"
            title="Simulate an AI agent attempting direct payment to test interception"
          >
            <ShieldX className="w-3 h-3" />
            <span>Test AI Autonomy Block</span>
          </button>
        </div>
      </div>

      {/* Policy Rules Evaluation Matrix */}
      {policyResult && (
        <div className="space-y-3">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-400 block">
            Rule Verification Matrix
          </span>

          <div className="grid grid-cols-1 gap-2.5">
            {policyResult.checks.map((check) => (
              <div
                key={check.rule_id}
                className={cn(
                  'p-3 rounded-lg border flex items-start justify-between gap-3 transition-colors',
                  check.passed
                    ? 'bg-navy-950/70 border-emerald-900/30 text-slate-200'
                    : 'bg-rose-950/20 border-rose-900/50 text-slate-200'
                )}
              >
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5">
                    {check.passed ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-slate-100">
                        {check.rule_name}
                      </span>
                      <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-navy-800 text-slate-400 border border-navy-700">
                        {check.rule_id}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">{check.description}</p>
                    <p
                      className={cn(
                        'text-[11px] font-mono mt-1',
                        check.passed ? 'text-emerald-400/90' : 'text-rose-400 font-semibold'
                      )}
                    >
                      Audit trace: {check.details}
                    </p>
                  </div>
                </div>

                <span
                  className={cn(
                    'shrink-0 text-[10px] font-mono uppercase px-2 py-0.5 rounded border font-semibold',
                    check.passed
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                      : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                  )}
                >
                  {check.passed ? 'PASSED' : 'VIOLATION'}
                </span>
              </div>
            ))}
          </div>

          {/* Violations Notice */}
          {policyResult.violations.length > 0 && (
            <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-800/60 text-xs text-rose-200 space-y-1.5">
              <div className="flex items-center gap-2 font-bold text-rose-300">
                <AlertTriangle className="w-4 h-4 text-rose-400" />
                <span>Deterministic Guardrail Interception Triggered</span>
              </div>
              <p className="text-slate-300">
                The transaction proposal was halted by TrustGate. The following deterministic policy invariant failed:
              </p>
              <ul className="list-disc list-inside space-y-1 font-mono text-[11px] text-rose-300">
                {policyResult.violations.map((v, i) => (
                  <li key={i}>{v.message}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Cryptographic Signature Token */}
          <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800 flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Key className="w-3 h-3 text-emerald-400" />
              Policy Signature:
            </span>
            <span className="text-emerald-400 font-semibold truncate max-w-xs sm:max-w-md">
              {policyResult.policy_signature}
            </span>
          </div>
        </div>
      )}

      {/* No Policy Evaluation State */}
      {!policyResult && product && (
        <div className="rounded-xl border border-navy-800 bg-navy-950/60 p-6 text-center space-y-2">
          <Lock className="w-5 h-5 text-slate-500 mx-auto" />
          <h4 className="text-xs font-mono font-bold text-slate-300">
            Pending Policy Evaluation
          </h4>
          <p className="text-xs font-mono text-slate-500 max-w-md mx-auto">
            No policy evaluation exists yet for "{product.title}". Run verification above to validate against TG-001–TG-007 deterministic policies.
          </p>
        </div>
      )}

      {/* Human Approval Gate */}
      {passed && policyResult && (
        <div className="pt-4 border-t border-navy-800 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <UserCheck className="w-4 h-4 text-emerald-400" />
              Mandatory Human-in-the-Loop Approval Gate
            </span>
            <span
              className={cn(
                'text-[10px] font-mono px-2 py-0.5 rounded border uppercase',
                humanApproved
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              )}
            >
              {humanApproved ? 'HUMAN CONSENT SIGNED' : 'AWAITING USER SIGNATURE'}
            </span>
          </div>

          {isAwaitingHuman ? (
            <div className="p-4 rounded-xl bg-navy-950 border border-emerald-900/40 space-y-3">
              <div className="text-xs text-slate-300 space-y-1">
                <p className="font-semibold text-white">
                  Verification passed. To proceed to PayPal Sandbox, please confirm authorization:
                </p>
                <p className="text-slate-400 text-[11px]">
                  Authorize transaction of{' '}
                  <strong className="text-white font-mono">
                    {formatCurrency(policyResult.total_evaluated_cost)}
                  </strong>{' '}
                  to merchant <strong className="text-white">{product?.merchant}</strong>.
                </p>
              </div>

              <button
                type="button"
                onClick={onGrantApproval}
                className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-navy-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-emerald-glow"
              >
                <FileCheck className="w-4 h-4" />
                <span>Sign & Authorize PayPal Staged Order</span>
              </button>
            </div>
          ) : isCheckoutReady ? (
            /* PayPal Sandbox Staged Order Preview */
            <div className="p-4 rounded-xl bg-navy-950 border border-emerald-500/30 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-paypal-lightBlue" />
                  <span className="text-xs font-bold text-white font-mono">
                    PayPal Sandbox Checkout Order Staged
                  </span>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-paypal-blue/20 text-paypal-lightBlue border border-paypal-blue/40">
                  READY FOR CHECKOUT HANDOFF
                </span>
              </div>

              <p className="text-xs text-slate-400">
                Order parameters verified and signed with human consent. In strict compliance with security constraints, payment execution is not triggered automatically.
              </p>

              {/* Order Payload Preview */}
              <div className="p-3 rounded-lg bg-navy-900 border border-navy-800 text-[11px] font-mono text-slate-300 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500">Intent:</span>
                  <span className="text-emerald-400 font-bold">CAPTURE</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Item:</span>
                  <span className="text-white">{product?.title}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Authorized Value:</span>
                  <span className="text-white font-bold">
                    {formatCurrency(policyResult.total_evaluated_cost)} USD
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Security Signature:</span>
                  <span className="text-emerald-400">{policyResult.policy_signature}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

