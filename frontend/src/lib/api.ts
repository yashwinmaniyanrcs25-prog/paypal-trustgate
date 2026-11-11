import {
  AgentAnalysisResponse,
  PolicyEvaluationResponse,
  MandatePolicyEvaluationResponse,
  PurchaseMandate,
  ProposedTransaction,
  IntentInterpretationResponse,
  SystemHealth,
  AuditLogItem,
  DiscoveredProduct,
  ProposalSearchResponse,
  StageProposalResponse,
  MarketplaceStatus,
  PaymentConfigResponse,
  CreateOrderResponse,
  CaptureOrderResponse,
  PaymentStatusResponse,
  AuditIntegrityResponse,
  StateTransitionResponse,
  AuditTrailResponse,
  AuditEventRecord,
  TransactionLifecycleTimeline,
  TransactionListResponse,
  AuditSummaryResponse,
} from '../types';
import { extractErrorMessage } from './utils';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
      },
      ...options,
    });

    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      const fallbackMsg = res.statusText
        ? `Request failed with status ${res.status}: ${res.statusText}`
        : `Request failed with status ${res.status}`;
      const message = extractErrorMessage(errorBody, fallbackMsg);
      throw new Error(message);
    }

    return await res.json();
  } catch (err: unknown) {
    console.warn(`[TrustGate API Warning] Network request to ${url} failed:`, err);
    throw err;
  }
}

export const api = {
  getHealth: async (): Promise<SystemHealth> => {
    try {
      return await request<SystemHealth>('/health');
    } catch {
      return {
        status: 'standby',
        service: 'PayPal TrustGate (Local)',
        environment: 'development',
        timestamp: new Date().toISOString(),
        security_policy: {
          ai_direct_execution_blocked: true,
          human_in_the_loop_mandatory: true,
          deterministic_guardrails: 'ENFORCED',
        },
        integrations: {
          grok_ai: {
            model: 'grok-beta',
            endpoint: 'https://api.x.ai/v1',
            configured: false,
          },
          paypal_sandbox: {
            mode: 'sandbox',
            currency: 'USD',
            configured: false,
            target_api: 'https://api-m.sandbox.paypal.com',
            payment_execution_enabled: false,
            policy_guardrail_active: true,
          },
          supabase: {
            configured: false,
            target_url: 'Not connected',
            audit_table: 'trustgate_audit_logs',
            active_in_memory_buffer_count: 0,
          },
        },
      };
    }
  },

  interpretPurchaseIntent: async (
    prompt: string
  ): Promise<IntentInterpretationResponse> => {
    return await request<IntentInterpretationResponse>('/intent/interpret', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
  },

  analyzeInstruction: async (
    instruction: string,
    explicitBudget?: number
  ): Promise<AgentAnalysisResponse> => {
    return await request<AgentAnalysisResponse>('/agent/analyze', {
      method: 'POST',
      body: JSON.stringify({
        instruction,
        explicit_budget_cap: explicitBudget,
        user_id: 'user_frontend_session',
      }),
    });
  },

  evaluateMandatePolicy: async (params: {
    mandate: PurchaseMandate;
    transaction: ProposedTransaction;
    callerRole?: string;
  }): Promise<MandatePolicyEvaluationResponse> => {
    return await request<MandatePolicyEvaluationResponse>('/policy/evaluate', {
      method: 'POST',
      body: JSON.stringify({
        mandate: params.mandate,
        transaction: params.transaction,
        caller_role: params.callerRole || 'human_user',
      }),
    });
  },

  evaluatePolicy: async (params: {
    instruction: string;
    budget: number;
    proposedPrice: number;
    shippingCost?: number;
    merchant: string;
    callerRole?: string;
  }): Promise<PolicyEvaluationResponse> => {
    return await request<PolicyEvaluationResponse>('/policy/evaluate', {
      method: 'POST',
      body: JSON.stringify({
        user_id: 'user_frontend_session',
        original_instruction: params.instruction,
        budget_limit: params.budget,
        proposed_price: params.proposedPrice,
        shipping_cost: params.shippingCost || 0,
        merchant_name: params.merchant,
        caller_role: params.callerRole || 'human_user',
      }),
    });
  },

  getAuditLogs: async (): Promise<{ count: number; logs: AuditLogItem[] }> => {
    try {
      return await request<{ count: number; logs: AuditLogItem[] }>('/policy/audit');
    } catch {
      return { count: 0, logs: [] };
    }
  },

  getMarketplaces: async (region?: string): Promise<MarketplaceStatus[]> => {
    try {
      const q = region ? `?region=${encodeURIComponent(region)}` : '';
      return await request<MarketplaceStatus[]>(`/proposals/marketplaces${q}`);
    } catch {
      return [];
    }
  },

  getMarketplaceStatus: async (marketplaceId: string, region?: string): Promise<MarketplaceStatus> => {
    const q = region ? `?region=${encodeURIComponent(region)}` : '';
    return await request<MarketplaceStatus>(`/proposals/marketplaces/${marketplaceId}/status${q}`);
  },

  searchProposals: async (params: {
    mandate: PurchaseMandate;
    query?: string;
    catalogMode?: 'demo' | 'external' | 'amazon';
    marketplaceId?: string;
    region?: string;
  }): Promise<ProposalSearchResponse> => {
    return await request<ProposalSearchResponse>('/proposals/search', {
      method: 'POST',
      body: JSON.stringify({
        mandate: params.mandate,
        query: params.query || '',
        catalog_mode: params.catalogMode || (params.marketplaceId === 'amazon' ? 'amazon' : 'demo'),
        marketplace_id: params.marketplaceId || (params.catalogMode === 'external' ? 'external' : 'demo'),
        region: params.region || (params.marketplaceId === 'channel3' ? 'global' : (params.mandate.currency.toUpperCase() === 'INR' ? 'demo_in' : 'demo_us')),
      }),
    });
  },

  stageProposal: async (params: {
    mandate: PurchaseMandate;
    candidate: DiscoveredProduct;
    userId?: string;
  }): Promise<StageProposalResponse> => {
    return await request<StageProposalResponse>('/proposals/stage', {
      method: 'POST',
      body: JSON.stringify({
        mandate: params.mandate,
        candidate: params.candidate,
        user_id: params.userId || 'user_demo',
      }),
    });
  },

  getPaymentConfig: async (): Promise<PaymentConfigResponse> => {
    return await request<PaymentConfigResponse>('/payments/config');
  },

  verifyPaymentAuth: async (): Promise<any> => {
    return await request<any>('/payments/verify-auth');
  },

  createPaymentOrder: async (stagedProposalId: string, userId?: string): Promise<CreateOrderResponse> => {
    return await request<CreateOrderResponse>('/payments/create-order', {
      method: 'POST',
      body: JSON.stringify({
        staged_proposal_id: stagedProposalId,
        user_id: userId || 'user_demo',
      }),
    });
  },

  capturePaymentOrder: async (orderId: string, userId?: string): Promise<CaptureOrderResponse> => {
    return await request<CaptureOrderResponse>('/payments/capture-order', {
      method: 'POST',
      body: JSON.stringify({
        order_id: orderId,
        user_id: userId || 'user_demo',
      }),
    });
  },

  getPaymentOrderStatus: async (orderId: string): Promise<PaymentStatusResponse> => {
    return await request<PaymentStatusResponse>(`/payments/orders/${encodeURIComponent(orderId)}`);
  },

  // Lifecycle State Machine
  approveProposal: async (
    transactionId: string,
    options?: { user_id?: string; consent_token?: string }
  ): Promise<StateTransitionResponse> => {
    return await request<StateTransitionResponse>(`/payments/proposals/${encodeURIComponent(transactionId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(options || {}),
    });
  },

  rejectProposal: async (
    transactionId: string,
    options?: { user_id?: string; reason?: string }
  ): Promise<StateTransitionResponse> => {
    return await request<StateTransitionResponse>(`/payments/proposals/${encodeURIComponent(transactionId)}/reject`, {
      method: 'POST',
      body: JSON.stringify(options || {}),
    });
  },

  cancelProposal: async (
    transactionId: string,
    options?: { user_id?: string; reason?: string }
  ): Promise<StateTransitionResponse> => {
    return await request<StateTransitionResponse>(`/payments/proposals/${encodeURIComponent(transactionId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify(options || {}),
    });
  },

  expireProposal: async (
    transactionId: string,
    reason?: string
  ): Promise<StateTransitionResponse> => {
    const qs = reason ? `?reason=${encodeURIComponent(reason)}` : '';
    return await request<StateTransitionResponse>(`/payments/proposals/${encodeURIComponent(transactionId)}/expire${qs}`, {
      method: 'POST',
    });
  },

  getProposalState: async (transactionId: string): Promise<any> => {
    return await request<any>(`/payments/proposals/${encodeURIComponent(transactionId)}/state`);
  },

  // Trust & Audit Layer
  getAuditEvents: async (params?: {
    transaction_id?: string;
    event_type?: string;
    stage?: string;
    status?: string;
    limit?: number;
    offset?: number;
    order?: 'asc' | 'desc';
  }): Promise<AuditTrailResponse> => {
    try {
      const queryParams = new URLSearchParams();
      if (params?.transaction_id) queryParams.append('transaction_id', params.transaction_id);
      if (params?.event_type) queryParams.append('event_type', params.event_type);
      if (params?.stage) queryParams.append('stage', params.stage);
      if (params?.status) queryParams.append('status', params.status);
      if (params?.limit !== undefined) queryParams.append('limit', params.limit.toString());
      if (params?.offset !== undefined) queryParams.append('offset', params.offset.toString());
      if (params?.order) queryParams.append('order', params.order);
      const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';
      return await request<AuditTrailResponse>(`/audit/events${qs}`);
    } catch {
      return { count: 0, total: 0, events: [] };
    }
  },

  getAuditEventById: async (eventId: string): Promise<AuditEventRecord | null> => {
    try {
      return await request<AuditEventRecord>(`/audit/events/${encodeURIComponent(eventId)}`);
    } catch {
      return null;
    }
  },

  getTransactionTimeline: async (transactionId: string): Promise<TransactionLifecycleTimeline> => {
    return await request<TransactionLifecycleTimeline>(`/audit/timeline/${encodeURIComponent(transactionId)}`);
  },

  getPersistedTransactions: async (limit: number = 30): Promise<TransactionListResponse> => {
    try {
      return await request<TransactionListResponse>(`/audit/transactions?limit=${limit}`);
    } catch {
      return { count: 0, transactions: [] };
    }
  },

  getAuditSummary: async (): Promise<AuditSummaryResponse> => {
    try {
      return await request<AuditSummaryResponse>('/audit/summary');
    } catch {
      return {
        storage_engine: 'SQLite Persistent (ACID compliant)',
        db_path: 'backend/data/trustgate.db',
        persisted: true,
        audit_chain_verified: undefined,
        total_audit_events: 0,
        total_mandates: 0,
        total_staged_proposals: 0,
        total_paypal_captures: 0,
        total_evaluations: 0,
        approved_evaluations: 0,
        blocked_evaluations: 0,
        total_human_approvals: 0,
      };
    }
  },

  checkAuditIntegrity: async (): Promise<AuditIntegrityResponse> => {
    return await request<AuditIntegrityResponse>('/audit/integrity');
  },

  // Channel3 Universal Product Graph endpoints
  getChannel3Status: async (): Promise<MarketplaceStatus> => {
    return await request<MarketplaceStatus>('/channel3/status');
  },

  testChannel3Connection: async (): Promise<any> => {
    return await request<any>('/channel3/test-connection', {
      method: 'POST',
    });
  },

  searchChannel3: async (
    params:
      | {
          query: string;
          limit?: number;
          currency?: string;
          mandate?: PurchaseMandate;
        }
      | string,
    mandate?: PurchaseMandate
  ): Promise<any> => {
    const payload = typeof params === 'string' ? { query: params, mandate } : params;
    return await request<any>('/channel3/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
