import { useState, useCallback } from 'react';
import { api } from '../../lib/api';
import { PurchaseFlowState } from './types';

export function usePurchaseFlow() {
  const [state, setState] = useState<PurchaseFlowState>({
    step: 'idle',
    instruction: '',
    analysis: null,
    policyResult: null,
    humanApproved: false,
    isLoading: false,
    error: null,
  });

  const submitInstruction = useCallback(async (instruction: string, explicitBudget?: number) => {
    setState((prev) => ({
      ...prev,
      instruction,
      step: 'analyzing',
      isLoading: true,
      error: null,
      policyResult: null,
      humanApproved: false,
    }));

    try {
      const analysis = await api.analyzeInstruction(instruction, explicitBudget);
      setState((prev) => ({
        ...prev,
        step: 'proposals_ready',
        analysis,
        isLoading: false,
      }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to analyze instructions with Grok';
      setState((prev) => ({
        ...prev,
        step: 'idle',
        isLoading: false,
        error: msg,
      }));
    }
  }, []);

  const runPolicyVerification = useCallback(
    async (overrideCallerRole?: string, simulatedPrice?: number) => {
      if (!state.analysis || !state.analysis.proposed_product) return;

      setState((prev) => ({
        ...prev,
        step: 'evaluating_policy',
        isLoading: true,
        error: null,
      }));

      const product = state.analysis.proposed_product;
      const budget = state.analysis.extracted_constraints.max_budget;
      const priceToEvaluate = simulatedPrice !== undefined ? simulatedPrice : product.price;

      try {
        const policyResult = await api.evaluatePolicy({
          instruction: state.instruction,
          budget,
          proposedPrice: priceToEvaluate,
          shippingCost: product.shipping_cost,
          merchant: product.merchant,
          callerRole: overrideCallerRole || 'human_user',
        });

        setState((prev) => ({
          ...prev,
          step: 'policy_checked',
          policyResult,
          isLoading: false,
        }));
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Policy evaluation failed';
        setState((prev) => ({
          ...prev,
          step: 'proposals_ready',
          isLoading: false,
          error: msg,
        }));
      }
    },
    [state.analysis, state.instruction]
  );

  const grantHumanConsent = useCallback(() => {
    if (!state.policyResult || !state.policyResult.passed) return;

    setState((prev) => ({
      ...prev,
      humanApproved: true,
      step: 'ready_for_paypal_checkout',
    }));
  }, [state.policyResult]);

  const reset = useCallback(() => {
    setState({
      step: 'idle',
      instruction: '',
      analysis: null,
      policyResult: null,
      humanApproved: false,
      isLoading: false,
      error: null,
    });
  }, []);

  return {
    ...state,
    submitInstruction,
    runPolicyVerification,
    grantHumanConsent,
    reset,
  };
}

