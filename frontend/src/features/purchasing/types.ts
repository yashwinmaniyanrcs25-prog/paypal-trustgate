import { AgentAnalysisResponse, PolicyEvaluationResponse } from '../../types';

export type PurchasingStep =
  | 'idle'
  | 'analyzing'
  | 'proposals_ready'
  | 'evaluating_policy'
  | 'policy_checked'
  | 'awaiting_human_signature'
  | 'ready_for_paypal_checkout';

export interface PurchaseFlowState {
  step: PurchasingStep;
  instruction: string;
  analysis: AgentAnalysisResponse | null;
  policyResult: PolicyEvaluationResponse | null;
  humanApproved: boolean;
  isLoading: boolean;
  error: string | null;
}

