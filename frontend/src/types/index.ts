export type RuleSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM';

export interface PurchaseConstraints {
  max_budget: number;
  allowed_categories: string[];
  allowed_merchants: string[];
  required_specs: string[];
  destination_country: string;
}

export interface ProductProposal {
  id: string;
  title: string;
  description: string;
  merchant: string;
  merchant_trusted: boolean;
  price: number;
  shipping_cost: number;
  currency: string;
  confidence_score: number;
  specs_matched: string[];
  specs_unmatched: string[];
  product_url?: string;
}

export interface AgentAnalysisResponse {
  request_id: string;
  original_instruction: string;
  extracted_constraints: PurchaseConstraints;
  reasoning_summary: string;
  proposed_product?: ProductProposal;
  ai_status: string;
  warning: string;
}

export interface PolicyCheckSummary {
  rule_id: string;
  rule_name: string;
  description: string;
  passed: boolean;
  details: string;
}

export interface PolicyViolation {
  rule_id: string;
  rule_name: string;
  message: string;
  severity: RuleSeverity;
  expected?: unknown;
  actual?: unknown;
}

export interface PurchaseMandate {
  max_amount: number;
  currency: string;
  allowed_conditions: string[];
  require_merchant_verification: boolean;
  allow_add_ons: boolean;
  user_restrictions?: string[];
  category?: string | null;
  search_query?: string | null;
  min_ram_gb?: number | null;
  min_storage_gb?: number | null;
  storage_type?: string | null;
  processor_requirement?: string | null;
  gpu_requirement?: string | null;
  display_size?: string | null;
  brand_preference?: string | null;
  model_preference?: string | null;
  marketplace?: string | null;
  in_stock_required?: boolean;
}

export interface ProposedTransaction {
  product_name: string;
  product_description?: string;
  product_price: number;
  shipping_cost: number;
  tax: number;
  additional_charges: number;
  final_total: number;
  currency: string;
  merchant_name: string;
  merchant_verified: boolean;
  product_condition: string;
  add_ons: string[];
  brand?: string | null;
  model?: string | null;
  ram_gb?: number | null;
  storage_gb?: number | null;
  storage_type?: string | null;
  processor?: string | null;
  gpu?: string | null;
  screen_size?: string | null;
  availability?: string | null;
  marketplace?: string | null;
  retailer?: string | null;
  original_price?: number | null;
  original_currency?: string | null;
  spec_verification_status?: string | null;
}

export interface MandatePolicyEvaluationRequest {
  mandate: PurchaseMandate;
  transaction: ProposedTransaction;
  caller_role?: string;
}

export interface MandatePolicyEvaluationResponse {
  evaluation_id: string;
  approved: boolean;
  status: 'APPROVED' | 'BLOCKED';
  violations: PolicyViolation[];
  explanation: string;
  checks: PolicyCheckSummary[];
  mandate_summary: {
    max_amount: number;
    currency: string;
    allowed_conditions: string[];
    require_merchant_verification: boolean;
    allow_add_ons: boolean;
    user_restrictions?: string[];
  };
  transaction_summary: {
    product_name: string;
    final_total: number;
    currency: string;
    merchant_name: string;
    merchant_verified: boolean;
    product_condition: string;
    add_ons: string[];
    itemized_breakdown: {
      product_price: number;
      shipping_cost: number;
      tax: number;
      additional_charges: number;
    };
  };
  requires_human_approval: boolean;
  can_proceed_to_paypal: boolean;
  policy_signature: string;
  evaluated_at: string;
}

export interface IntentInterpretationRequest {
  prompt: string;
}

export interface IntentInterpretationResponse {
  raw_prompt: string;
  success: boolean;
  status: 'SUCCESS' | 'NEEDS_CLARIFICATION' | 'PROVIDER_UNCONFIGURED' | 'PROVIDER_ERROR' | 'VALIDATION_ERROR';
  needs_clarification: boolean;
  clarification_prompt?: string | null;
  mandate?: PurchaseMandate | null;
  extracted_intent_summary?: string | null;
  ai_explanation?: string | null;
  is_confirmed: boolean;
  error_message?: string | null;
}

export interface PolicyEvaluationResponse {
  evaluation_id: string;
  passed: boolean;
  status: string;
  checks: PolicyCheckSummary[];
  violations: PolicyViolation[];
  total_evaluated_cost: number;
  budget_limit: number;
  requires_human_approval: boolean;
  can_proceed_to_paypal: boolean;
  policy_signature: string;
}

export interface SystemHealth {
  status: string;
  service: string;
  environment: string;
  timestamp: string;
  security_policy: {
    ai_direct_execution_blocked: boolean;
    human_in_the_loop_mandatory: boolean;
    deterministic_guardrails: string;
  };
  integrations: {
    grok_ai: {
      provider?: string;
      model: string;
      endpoint: string;
      configured: boolean;
    };
    paypal_sandbox: {
      mode: string;
      currency: string;
      configured: boolean;
      target_api: string;
      payment_execution_enabled: boolean;
      policy_guardrail_active: boolean;
    };
    supabase: {
      configured: boolean;
      target_url: string;
      audit_table: string;
      active_in_memory_buffer_count: number;
    };
  };
}

export interface AuditLogItem {
  evaluation_id: string;
  user_id: string;
  passed: boolean;
  total_cost: number;
  rules_checked: number;
  violations: string[];
  timestamp: string;
  source: string;
}


export type MarketplaceIntegrationState =
  | 'Not Configured'
  | 'Credentials Missing'
  | 'Access Pending'
  | 'Connected'
  | 'Error';

export interface MarketplaceRegion {
  id: string;
  name: string;
  currency: string;
  host: string;
  is_default?: boolean;
}

export interface MarketplaceStatus {
  marketplace_id: string;
  name: string;
  state: MarketplaceIntegrationState;
  is_connected: boolean;
  configured: boolean;
  supported_regions: MarketplaceRegion[];
  active_region: string;
  currency: string;
  message: string;
  setup_guidance?: string | null;
  legal_disclaimer: string;
}

export interface DiscoveredProduct {
  product_id: string;
  name: string;
  description: string;
  category: string;
  price: number;
  currency: string;
  image_url?: string | null;
  condition: string;
  merchant_name: string;
  merchant_verified: boolean;
  verification_status: string;
  data_source: string;
  is_demo_data: boolean;
  demo_notice: string;
  marketplace_id?: string;
  region?: string;
  data_freshness?: string;
  purchase_url?: string | null;
  availability?: string | null;
  retailer?: string | null;
  brand?: string | null;
  model?: string | null;
  ram_gb?: number | null;
  storage_gb?: number | null;
  storage_type?: string | null;
  processor?: string | null;
  gpu?: string | null;
  screen_size?: string | null;
  original_price?: number | null;
  original_currency?: string | null;
  spec_verification_status?: string | null;
  enrichment_status?: string | null;
}

export interface Channel3TestResponse {
  success: boolean;
  configured: boolean;
  status: string;
  status_code?: number | null;
  latency_ms?: number | null;
  endpoint: string;
  products_returned?: number | null;
  sample_title?: string | null;
  message: string;
}

export interface CandidateEvaluation {
  product: DiscoveredProduct;
  policy_result: MandatePolicyEvaluationResponse;
  approved: boolean;
  status: 'APPROVED' | 'NEEDS_VERIFICATION' | 'BLOCKED';
  budget_remaining: number;
  currency: string;
  can_select: boolean;
  selection_blocked_reason?: string | null;
  unverified_reasons?: string[] | null;
  enrichment_status?: string | null;
}

export interface ProposalSearchRequest {
  mandate: PurchaseMandate;
  query?: string;
  catalog_mode?: 'demo' | 'external' | 'amazon';
  marketplace_id?: string;
  region?: string;
  page?: number;
  limit?: number;
  offset?: number;
  page_token?: string | null;
}

export interface ProposalSearchResponse {
  query?: string;
  candidates: CandidateEvaluation[];
  discovered_count?: number;
  enriched_count?: number;
  eligible_count?: number;
  unverified_count?: number;
  compliant_count: number;
  blocked_count: number;
  total_count: number;
  has_more?: boolean;
  page?: number;
  total_pages?: number;
  next_page_token?: string | null;
  catalog_mode: string;
  data_source: string;
  is_demo_data: boolean;
  demo_notice: string;
  marketplace_id?: string;
  marketplace_name?: string;
  region?: string;
  integration_state?: MarketplaceIntegrationState;
  setup_guidance?: string | null;
  legal_notice?: string;
  data_freshness?: string;
}

export interface StageProposalResponse {
  staged_proposal_id: string;
  product_name: string;
  price: number;
  currency: string;
  merchant_name: string;
  policy_approved: boolean;
  requires_human_approval: boolean;
  payment_executed: boolean;
  message: string;
  demo_notice: string;
  is_demo_data?: boolean;
}


export interface PaymentConfigResponse {
  configured: boolean;
  client_id?: string | null;
  mode: string;
  currency: string;
  base_url: string;
  merchant_name: string;
  is_sandbox: boolean;
  notice: string;
}

export interface CreateOrderRequest {
  staged_proposal_id: string;
  user_id?: string;
}

export interface CreateOrderResponse {
  order_id: string;
  staged_proposal_id: string;
  status: string;
  amount: number;
  currency: string;
  is_sandbox: boolean;
  is_demo_data: boolean;
  message: string;
}

export interface CaptureOrderRequest {
  order_id: string;
  user_id?: string;
}

export interface CaptureOrderResponse {
  order_id: string;
  capture_id: string;
  staged_proposal_id: string;
  status: string;
  amount: number;
  currency: string;
  product_name: string;
  merchant_name: string;
  captured_at: string;
  policy_decision: string;
  policy_signature: string;
  is_sandbox: boolean;
  is_demo_data: boolean;
  receipt_notice: string;
}

export interface PaymentStatusResponse {
  order_id: string;
  staged_proposal_id?: string | null;
  status: string;
  amount?: number | null;
  currency?: string | null;
  captured: boolean;
  capture_id?: string | null;
  is_sandbox: boolean;
  is_demo_data: boolean;
}

// ---------------------------------------------------------------------------
// Trust & Audit Layer Models
// ---------------------------------------------------------------------------

export interface AuditEventRecord {
  sequence_number?: number | null;
  event_id: string;
  transaction_id: string;
  event_type: string;
  stage: string;
  status: string;
  linked_mandate_id?: string | null;
  linked_proposal_id?: string | null;
  linked_evaluation_id?: string | null;
  linked_paypal_order_id?: string | null;
  linked_capture_id?: string | null;
  details: Record<string, any>;
  actor_role: string;
  timestamp: string;
  prev_hash?: string | null;
  event_hash?: string | null;
}

export interface HumanApprovalRecord {
  approval_id: string;
  transaction_id: string;
  user_id: string;
  policy_signature: string;
  approved_amount: number;
  currency: string;
  action: string;
  actor_role: string;
  consent_token?: string | null;
  created_at: string;
}

export interface TransactionTimelineStage {
  stage_name: string;
  stage_key: 'mandate' | 'proposal' | 'policy' | 'approval' | 'order' | 'receipt';
  status: 'COMPLETED' | 'PENDING' | 'BLOCKED' | 'NOT_STARTED';
  timestamp?: string | null;
  summary: string;
  details: Record<string, any>;
}

export interface TransactionLifecycleTimeline {
  transaction_id: string;
  current_status: TransactionState | string;
  created_at: string;
  updated_at: string;
  mandate_summary?: {
    mandate_id: string;
    currency: string;
    max_amount: number;
    allowed_conditions: string[];
  } | null;
  candidate_summary?: {
    product_id: string;
    name: string;
    price: number;
    currency: string;
    merchant_name: string;
    condition: string;
    is_demo_data: boolean;
  } | null;
  policy_evaluation_summary?: {
    evaluation_id: string;
    approved: boolean;
    policy_signature: string;
    violations_count: number;
  } | null;
  human_approval_summary?: {
    approved: boolean;
    approval_id?: string | null;
    user_id: string;
  } | null;
  paypal_order_summary?: {
    order_id?: string | null;
    status: string;
    is_sandbox: boolean;
  } | null;
  capture_receipt_summary?: {
    captured: boolean;
    capture_id?: string | null;
    captured_at?: string | null;
  } | null;
  stages: TransactionTimelineStage[];
  events: AuditEventRecord[];
}

export interface AuditTrailResponse {
  count: number;
  total?: number | null;
  offset?: number | null;
  limit?: number | null;
  events: AuditEventRecord[];
}

export interface AuditSummaryResponse {
  storage_engine: string;
  db_path: string;
  persisted: boolean;
  audit_chain_verified?: boolean;
  genesis_hash?: string;
  last_event_hash?: string;
  total_audit_events: number;
  total_mandates: number;
  total_staged_proposals: number;
  total_paypal_captures: number;
  total_evaluations: number;
  approved_evaluations: number;
  blocked_evaluations: number;
  total_human_approvals: number;
}

export interface AuditIntegrityResponse {
  is_valid: boolean;
  total_events: number;
  genesis_hash: string;
  last_event_hash?: string | null;
  first_invalid_sequence?: number | null;
  first_invalid_event_id?: string | null;
  failure_reason?: string | null;
  verified_at: string;
  tamper_evident_guarantee: string;
}

export interface TransactionSummaryItem {
  transaction_id: string;
  product_name: string;
  amount: number;
  currency: string;
  merchant_name: string;
  policy_approved: boolean;
  status: string;
  created_at: string;
  paypal_order_id?: string | null;
  capture_id?: string | null;
}

export interface TransactionListResponse {
  count: number;
  transactions: TransactionSummaryItem[];
}

export type TransactionState =
  | 'STAGED'
  | 'HUMAN_APPROVED'
  | 'HUMAN_REJECTED'
  | 'ORDER_CREATED'
  | 'ORDER_CREATION_FAILED'
  | 'CAPTURED'
  | 'CAPTURE_FAILED'
  | 'CANCELLED'
  | 'EXPIRED';

export interface StateTransitionResponse {
  transaction_id: string;
  previous_state: TransactionState;
  current_state: TransactionState;
  updated_at: string;
  audit_event_hash?: string | null;
  message: string;
  status?: TransactionState;
  human_approval_id?: string | null;
}

