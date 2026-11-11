/**
 * Centralized Transaction Lifecycle & State Guardrails for PayPal TrustGate.
 *
 * Implements strict frontend invariant checks reflecting the backend state machine
 * (app/models/lifecycle.py):
 *
 * State Machine Transitions:
 * - STAGED -> [HUMAN_APPROVED, HUMAN_REJECTED, CANCELLED, EXPIRED]
 * - HUMAN_APPROVED -> [ORDER_CREATED, ORDER_CREATION_FAILED, CANCELLED, EXPIRED]
 * - ORDER_CREATED -> [CAPTURED, CAPTURE_FAILED, CANCELLED, EXPIRED]
 * - ORDER_CREATION_FAILED -> [ORDER_CREATED, CANCELLED, EXPIRED]
 * - CAPTURE_FAILED -> [CAPTURED, CANCELLED]
 *
 * Terminal States (No transitions permitted):
 * - CAPTURED
 * - HUMAN_REJECTED
 * - CANCELLED
 * - EXPIRED
 *
 * Security Invariants:
 * 1. Checkout can ONLY be launched when current_status === 'HUMAN_APPROVED'.
 * 2. Pre-approval checkout is barred (STAGED cannot checkout).
 * 3. Terminal proposals (REJECTED, CANCELLED, EXPIRED, CAPTURED) cannot checkout.
 * 4. Cancellation is allowed ONLY from active/non-terminal states.
 * 5. Re-approval or re-cancellation of terminal proposals is blocked.
 */

import { TransactionState } from '../types';

export const CANCELLABLE_STATES: readonly TransactionState[] = [
  'STAGED',
  'HUMAN_APPROVED',
  'ORDER_CREATED',
  'ORDER_CREATION_FAILED',
  'CAPTURE_FAILED',
] as const;

export const TERMINAL_STATES: readonly TransactionState[] = [
  'CAPTURED',
  'HUMAN_REJECTED',
  'CANCELLED',
  'EXPIRED',
] as const;

/**
 * Determines whether a proposal's current state permits explicit cancellation.
 * Only non-terminal states can be cancelled.
 */
export function isCancellableState(status: string | undefined | null): boolean {
  if (!status) return false;
  const upper = status.trim().toUpperCase() as TransactionState;
  return (CANCELLABLE_STATES as readonly string[]).includes(upper);
}

/**
 * Determines whether PayPal Sandbox checkout may be launched.
 * Strict Invariant: Checkout can ONLY proceed from HUMAN_APPROVED state.
 * Any other state (STAGED, HUMAN_REJECTED, CANCELLED, EXPIRED, CAPTURED, etc.) is rejected.
 */
export function canLaunchCheckout(status: string | undefined | null): boolean {
  if (!status) return false;
  return status.trim().toUpperCase() === 'HUMAN_APPROVED';
}

/**
 * Determines whether human approval can be granted.
 * Only previously unapproved STAGED proposals may transition to HUMAN_APPROVED.
 */
export function canApproveProposal(status: string | undefined | null): boolean {
  if (!status) return false;
  return status.trim().toUpperCase() === 'STAGED';
}

/**
 * Determines whether human rejection can be recorded.
 * Only STAGED proposals can be rejected.
 */
export function canRejectProposal(status: string | undefined | null): boolean {
  if (!status) return false;
  return status.trim().toUpperCase() === 'STAGED';
}

/**
 * Determines whether a proposal is in an unalterable terminal state.
 */
export function isTerminalState(status: string | undefined | null): boolean {
  if (!status) return false;
  const upper = status.trim().toUpperCase() as TransactionState;
  return (TERMINAL_STATES as readonly string[]).includes(upper);
}

export interface StatusBadgeConfig {
  label: string;
  badgeClass: string;
  description: string;
  isTerminal: boolean;
  canCheckout: boolean;
  canCancel: boolean;
}

/**
 * Returns consistent UI styling and human-readable metadata for a lifecycle state.
 */
export function getStatusBadge(status: string | undefined | null): StatusBadgeConfig {
  const norm = (status || '').trim().toUpperCase();

  switch (norm) {
    case 'STAGED':
      return {
        label: 'Awaiting Human Approval',
        badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
        description: 'Candidate verified against policy; awaiting explicit human operator review.',
        isTerminal: false,
        canCheckout: false,
        canCancel: true,
      };

    case 'HUMAN_APPROVED':
      return {
        label: 'Human Approved',
        badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        description: 'Explicit human sign-off recorded. Eligible for PayPal Sandbox checkout.',
        isTerminal: false,
        canCheckout: true,
        canCancel: true,
      };

    case 'ORDER_CREATED':
      return {
        label: 'PayPal Order Created',
        badgeClass: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
        description: 'PayPal Sandbox order created; awaiting buyer authorization & capture.',
        isTerminal: false,
        canCheckout: false,
        canCancel: true,
      };

    case 'ORDER_CREATION_FAILED':
      return {
        label: 'Order Creation Failed',
        badgeClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        description: 'PayPal API or network timeout occurred during order creation.',
        isTerminal: false,
        canCheckout: false,
        canCancel: true,
      };

    case 'CAPTURED':
      return {
        label: 'Payment Captured',
        badgeClass: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/40 font-bold',
        description: 'Payment settled in PayPal Sandbox. Terminal state; re-execution barred.',
        isTerminal: true,
        canCheckout: false,
        canCancel: false,
      };

    case 'CAPTURE_FAILED':
      return {
        label: 'Capture Failed',
        badgeClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        description: 'PayPal gateway declined capture or error occurred.',
        isTerminal: false,
        canCheckout: false,
        canCancel: true,
      };

    case 'HUMAN_REJECTED':
      return {
        label: 'Rejected by Human',
        badgeClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        description: 'Explicit human refusal. Terminal state; checkout barred.',
        isTerminal: true,
        canCheckout: false,
        canCancel: false,
      };

    case 'CANCELLED':
      return {
        label: 'Session Cancelled',
        badgeClass: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
        description: 'Checkout session explicitly cancelled. Terminal state.',
        isTerminal: true,
        canCheckout: false,
        canCancel: false,
      };

    case 'EXPIRED':
      return {
        label: 'Session Expired',
        badgeClass: 'bg-slate-600/10 text-slate-500 border-slate-600/30',
        description: 'Checkout session abandoned past TTL. Terminal state.',
        isTerminal: true,
        canCheckout: false,
        canCancel: false,
      };

    default:
      return {
        label: status || 'Unknown State',
        badgeClass: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
        description: 'Unrecognized state.',
        isTerminal: false,
        canCheckout: false,
        canCancel: false,
      };
  }
}
