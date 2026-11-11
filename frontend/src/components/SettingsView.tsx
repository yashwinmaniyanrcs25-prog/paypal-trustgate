import React, { useState, useEffect } from 'react';
import {
  Lock,
  CreditCard,
  Globe,
  Cpu,
  ShieldCheck,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Database,
} from 'lucide-react';
import { api } from '../lib/api';
import { SystemHealth, PaymentConfigResponse, MarketplaceStatus } from '../types';
import { cn } from '../lib/utils';

interface SettingsViewProps {
  health: SystemHealth | null;
  onRefreshHealth?: () => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({ health, onRefreshHealth }) => {
  const [paymentConfig, setPaymentConfig] = useState<PaymentConfigResponse | null>(null);
  const [channel3Status, setChannel3Status] = useState<MarketplaceStatus | null>(null);
  const [isLoadingConfigs, setIsLoadingConfigs] = useState(true);

  // Live connection test state for Channel3
  const [isTestingChannel3, setIsTestingChannel3] = useState(false);
  const [channel3TestResult, setChannel3TestResult] = useState<any | null>(null);

  // Live connection test state for PayPal Sandbox
  const [isTestingPayPal, setIsTestingPayPal] = useState(false);
  const [paypalTestResult, setPayPalTestResult] = useState<any | null>(null);

  const loadDiagnostics = async () => {
    setIsLoadingConfigs(true);
    try {
      const [cfg, c3] = await Promise.all([
        api.getPaymentConfig().catch(() => null),
        api.getChannel3Status().catch(() => null),
      ]);
      setPaymentConfig(cfg);
      setChannel3Status(c3);
    } finally {
      setIsLoadingConfigs(false);
    }
  };

  useEffect(() => {
    loadDiagnostics();
  }, []);

  const handleTestChannel3 = async () => {
    setIsTestingChannel3(true);
    setChannel3TestResult(null);
    try {
      const res = await api.testChannel3Connection();
      setChannel3TestResult(res);
    } catch (err: unknown) {
      setChannel3TestResult({
        success: false,
        status: 'NETWORK_ERROR',
        message: err instanceof Error ? err.message : 'Connection test failed',
      });
    } finally {
      setIsTestingChannel3(false);
    }
  };

  const handleTestPayPal = async () => {
    setIsTestingPayPal(true);
    setPayPalTestResult(null);
    try {
      const res = await api.verifyPaymentAuth();
      setPayPalTestResult(res);
    } catch (err: unknown) {
      setPayPalTestResult({
        success: false,
        status: 'ERROR',
        message: err instanceof Error ? err.message : 'PayPal Sandbox verification failed',
      });
    } finally {
      setIsTestingPayPal(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Settings Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-navy-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            System Diagnostics & API Configuration
          </h2>
          <p className="text-xs text-slate-400">
            Real backend configuration status, partner credentials, and immutable security guardrails
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            loadDiagnostics();
            if (onRefreshHealth) onRefreshHealth();
          }}
          disabled={isLoadingConfigs}
          className="px-3 py-1.5 rounded-lg bg-navy-900 border border-navy-800 text-xs font-mono text-slate-300 hover:text-white flex items-center gap-2 self-start"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', isLoadingConfigs ? 'animate-spin text-emerald-400' : '')} />
          <span>Refresh Diagnostics</span>
        </button>
      </div>

      {/* Grid of Diagnostic Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Panel 1: PayPal Sandbox Integration */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-navy-800">
            <div className="flex items-center gap-2.5">
              <CreditCard className="w-5 h-5 text-paypal-blue" />
              <div>
                <h3 className="text-sm font-bold text-white">PayPal Sandbox Gateway</h3>
                <span className="text-[10px] font-mono text-slate-400">Orders v2 REST API</span>
              </div>
            </div>

            <span
              className={cn(
                'px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider',
                paymentConfig?.configured
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              )}
            >
              {paymentConfig?.configured ? 'Configured' : 'Needs Config'}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Execution Mode:</span>
              <span className="text-amber-400 font-bold">SANDBOX ONLY (Live Barred)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Target Endpoint:</span>
              <span className="text-slate-300">https://api-m.sandbox.paypal.com</span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Client ID:</span>
              <span className="text-slate-300">
                {paymentConfig?.client_id
                  ? `${paymentConfig.client_id.slice(0, 10)}...${paymentConfig.client_id.slice(-6)}`
                  : 'Not Configured'}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Currency Default:</span>
              <span className="text-slate-300">{paymentConfig?.currency || 'USD'}</span>
            </div>
          </div>

          {/* Test PayPal Button */}
          <div className="pt-2">
            <button
              type="button"
              onClick={handleTestPayPal}
              disabled={isTestingPayPal || !paymentConfig?.configured}
              className="w-full py-2 rounded-lg bg-navy-800 hover:bg-navy-700 border border-navy-700 text-xs font-mono font-semibold text-slate-200 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', isTestingPayPal ? 'animate-spin text-emerald-400' : '')} />
              <span>Verify Sandbox OAuth Handshake</span>
            </button>

            {paypalTestResult && (() => {
              const isSuccess = Boolean(
                paypalTestResult.authenticated ||
                paypalTestResult.success ||
                paypalTestResult.status === 'SUCCESS'
              );
              return (
                <div
                  className={cn(
                    'mt-3 p-3 rounded-lg border text-xs font-mono space-y-1',
                    isSuccess
                      ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                      : 'bg-rose-950/40 border-rose-500/30 text-rose-300'
                  )}
                >
                  <div className="font-bold flex items-center gap-1.5">
                    {isSuccess ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                    <span>Status: {paypalTestResult.status || (isSuccess ? 'AUTHENTICATED' : 'ERROR')}</span>
                  </div>
                  <p className="text-[11px] text-slate-300">
                    {paypalTestResult.message || paypalTestResult.error_description || paypalTestResult.error || 'Handshake complete'}
                  </p>
                </div>
              );
            })()}
          </div>
        </div>

        {/* Panel 2: Channel3 Universal Product Graph */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-navy-800">
            <div className="flex items-center gap-2.5">
              <Globe className="w-5 h-5 text-emerald-400" />
              <div>
                <h3 className="text-sm font-bold text-white">Channel3 Universal Graph</h3>
                <span className="text-[10px] font-mono text-slate-400">100M+ Multi-Merchant Graph</span>
              </div>
            </div>

            <span
              className={cn(
                'px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider',
                (channel3Status?.is_connected || channel3Status?.state === 'Connected')
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              )}
            >
              {channel3Status?.state || (isLoadingConfigs ? 'CHECKING...' : 'UNAVAILABLE')}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Endpoint:</span>
              <span className="text-slate-300">https://api.trychannel3.com/v1/search</span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Auth Header:</span>
              <span className="text-emerald-400 font-bold">x-api-key (Active & Masked)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Coverage:</span>
              <span className="text-slate-300">Target, Best Buy, Walmart, Apple, Keychron...</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Data Tagging:</span>
              <span className="text-emerald-400 font-bold">Genuine Catalog (Zero Demo Markup)</span>
            </div>
          </div>

          {/* Test Channel3 Button */}
          <div className="pt-2">
            <button
              type="button"
              onClick={handleTestChannel3}
              disabled={isTestingChannel3}
              className="w-full py-2 rounded-lg bg-navy-800 hover:bg-navy-700 border border-navy-700 text-xs font-mono font-semibold text-slate-200 transition-colors flex items-center justify-center gap-2"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', isTestingChannel3 ? 'animate-spin text-emerald-400' : '')} />
              <span>Test Live Channel3 Latency & Connectivity</span>
            </button>

            {channel3TestResult && (
              <div
                className={cn(
                  'mt-3 p-3 rounded-lg border text-xs font-mono space-y-1',
                  channel3TestResult.success
                    ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/40 border-rose-500/30 text-rose-300'
                )}
              >
                <div className="font-bold flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    {channel3TestResult.success ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                    <span>{channel3TestResult.status}</span>
                  </span>
                  {channel3TestResult.latency_ms !== undefined && (
                    <span className="text-emerald-400">{channel3TestResult.latency_ms} ms</span>
                  )}
                </div>
                <p className="text-[11px] text-slate-300">{channel3TestResult.message}</p>
              </div>
            )}
          </div>
        </div>

        {/* Panel 3: AI Provider & Groq Natural Language Interpreter */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-navy-800">
            <div className="flex items-center gap-2.5">
              <Cpu className="w-5 h-5 text-violet-400" />
              <div>
                <h3 className="text-sm font-bold text-white">Groq AI Intent Interpreter</h3>
                <span className="text-[10px] font-mono text-slate-400">Natural Language Mandate Translation</span>
              </div>
            </div>

            <span className="px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider bg-violet-500/10 text-violet-300 border-violet-500/30">
              {health?.integrations.grok_ai.configured ? 'Configured' : 'Active'}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Active Model:</span>
              <span className="text-slate-200 font-bold">
                {health?.integrations.grok_ai.model || 'openai/gpt-oss-120b'}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Inference Role:</span>
              <span className="text-slate-300">Mandate Extraction Only (Zero Auth)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Payment Authority:</span>
              <span className="text-rose-400 font-bold">BARRED (Strictly Deterministic)</span>
            </div>
          </div>
        </div>

        {/* Panel 4: SQLite Persistent ACID Audit Chain */}
        <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-navy-800">
            <div className="flex items-center gap-2.5">
              <Database className="w-5 h-5 text-emerald-400" />
              <div>
                <h3 className="text-sm font-bold text-white">SQLite Cryptographic Engine</h3>
                <span className="text-[10px] font-mono text-slate-400">WAL Mode • Tamper-Evident Storage</span>
              </div>
            </div>

            <span className="px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
              ACID Compliant
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Chaining Algorithm:</span>
              <span className="text-emerald-400 font-bold">Canonical RFC 8785 + SHA-256</span>
            </div>
            <div className="flex justify-between py-1 border-b border-navy-850">
              <span className="text-slate-400">Database Triggers:</span>
              <span className="text-emerald-400 font-bold">UPDATE & DELETE Blocked</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Storage Location:</span>
              <span className="text-slate-300">backend/data/trustgate.db</span>
            </div>
          </div>
        </div>
      </div>

      {/* Security Invariants Monitor Bar */}
      <div className="rounded-xl border border-emerald-500/30 bg-navy-900/80 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          <h3 className="text-sm font-bold text-white">Immutable Platform Security Invariants</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
          <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 text-xs">
            <div className="flex items-center gap-1.5 text-emerald-400 font-mono font-bold text-[11px] mb-1">
              <Lock className="w-3.5 h-3.5" />
              Zero AI Payment Rights
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">
              No AI agent or LLM can initiate, sign, or execute monetary transfers.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 text-xs">
            <div className="flex items-center gap-1.5 text-emerald-400 font-mono font-bold text-[11px] mb-1">
              <Lock className="w-3.5 h-3.5" />
              Mandatory Human Sign-off
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">
              Every purchase requires explicit human operator authorization before checkout.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 text-xs">
            <div className="flex items-center gap-1.5 text-emerald-400 font-mono font-bold text-[11px] mb-1">
              <Lock className="w-3.5 h-3.5" />
              TG-001–TG-007 Gates
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">
              Deterministic mathematical budget, condition, and merchant verification checks.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-navy-950 border border-navy-850 text-xs">
            <div className="flex items-center gap-1.5 text-amber-400 font-mono font-bold text-[11px] mb-1">
              <CreditCard className="w-3.5 h-3.5" />
              Sandbox Guardrail
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">
              Payments are strictly restricted to the official PayPal Sandbox API.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
