import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldX,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Lock,
  RefreshCw,
  Store,
  Tag,
  Key,
  Info,
} from 'lucide-react';
import {
  PurchaseMandate,
  ProposedTransaction,
  MandatePolicyEvaluationResponse,
} from '../types';
import { api } from '../lib/api';
import { cn } from '../lib/utils';

interface TrustGatePolicySimulatorProps {
  initialMandate?: PurchaseMandate | null;
}

// Compliant preset (passes all checks)
const COMPLIANT_PRESET = {
  mandate: {
    max_amount: 150.0,
    currency: 'USD',
    allowed_conditions: ['new'],
    require_merchant_verification: true,
    allow_add_ons: false,
    user_restrictions: ['US domestic delivery only'],
  },
  transaction: {
    product_name: 'Keychron K2 Pro Wireless Mechanical Keyboard',
    product_description: 'Compact 75% layout, tactile hot-swappable brown switches, PBT keycaps.',
    product_price: 109.99,
    shipping_cost: 0.0,
    tax: 8.8,
    additional_charges: 0.0,
    final_total: 118.79,
    currency: 'USD',
    merchant_name: 'Keychron Official Direct',
    merchant_verified: true,
    product_condition: 'new',
    add_ons: [],
  },
};

// Violating preset (triggers budget breach, wrong condition, unverified merchant & add-ons)
const VIOLATING_PRESET = {
  mandate: {
    max_amount: 150.0,
    currency: 'USD',
    allowed_conditions: ['new'],
    require_merchant_verification: true,
    allow_add_ons: false,
    user_restrictions: ['US domestic delivery only'],
  },
  transaction: {
    product_name: 'Over-Spec Ultrawide Gaming Monitor Bundle',
    product_description: 'Curved 34-inch display with bundled aftermarket mounts and cables.',
    product_price: 219.0,
    shipping_cost: 15.0,
    tax: 18.0,
    additional_charges: 25.0,
    final_total: 277.0, // Exceeds $150 limit
    currency: 'USD',
    merchant_name: 'unverified_seller', // Unverified & blacklisted
    merchant_verified: false,
    product_condition: 'refurbished', // Prohibited condition (mandate allows only 'new')
    add_ons: ['2-Year Accidental Warranty Extension', 'Premium Desk Mounting Arm'], // Prohibited add-ons
  },
};

export const TrustGatePolicySimulator: React.FC<TrustGatePolicySimulatorProps> = ({
  initialMandate,
}) => {
  // Mandate state
  const [mandate, setMandate] = useState<PurchaseMandate>(initialMandate || COMPLIANT_PRESET.mandate);
  const [isImported, setIsImported] = useState(Boolean(initialMandate));

  // Transaction state
  const [transaction, setTransaction] = useState<ProposedTransaction>(COMPLIANT_PRESET.transaction);
  const [addOnInput, setAddOnInput] = useState<string>('');

  // Evaluation response state
  const [result, setResult] = useState<MandatePolicyEvaluationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync when initialMandate changes from natural language interpreter
  useEffect(() => {
    if (initialMandate) {
      setMandate(initialMandate);
      setIsImported(true);
      setResult(null);

      // Auto-adapt transaction currency and sensible candidate item
      if (initialMandate.currency === 'INR') {
        const base = Math.round(initialMandate.max_amount * 0.88);
        const txTax = Math.round(initialMandate.max_amount * 0.06);
        const tot = base + txTax;
        setTransaction({
          product_name: 'Lenovo IdeaPad Slim 3 15-inch Laptop',
          product_description: 'Intel Core i5 12th Gen, 16GB RAM, 512GB NVMe SSD.',
          product_price: base,
          shipping_cost: 0.0,
          tax: txTax,
          additional_charges: 0.0,
          final_total: tot,
          currency: 'INR',
          merchant_name: 'Lenovo Official India Direct',
          merchant_verified: true,
          product_condition: 'new',
          add_ons: [],
        });
      } else {
        setTransaction((prev) => ({
          ...prev,
          currency: initialMandate.currency,
          product_price: Math.min(prev.product_price, Math.round(initialMandate.max_amount * 0.8)),
          final_total: Math.min(prev.final_total, Math.round(initialMandate.max_amount * 0.9)),
        }));
      }
    }
  }, [initialMandate]);

  // Preset loaders
  const loadCompliantPreset = () => {
    setMandate(COMPLIANT_PRESET.mandate);
    setTransaction(COMPLIANT_PRESET.transaction);
    setAddOnInput('');
    setIsImported(false);
    setResult(null);
    setError(null);
  };

  const loadViolatingPreset = () => {
    setMandate(VIOLATING_PRESET.mandate);
    setTransaction(VIOLATING_PRESET.transaction);
    setAddOnInput(VIOLATING_PRESET.transaction.add_ons.join(', '));
    setIsImported(false);
    setResult(null);
    setError(null);
  };

  // Auto-sync calculated total if user adjusts component pricing
  const handlePriceChange = (field: keyof ProposedTransaction, val: number) => {
    const updated = { ...transaction, [field]: val };
    const calculatedSum =
      Math.round(
        (updated.product_price + updated.shipping_cost + updated.tax + updated.additional_charges) * 100
      ) / 100;
    updated.final_total = calculatedSum;
    setTransaction(updated);
  };

  // Submit to real FastAPI backend endpoint: POST /api/v1/policy/evaluate
  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    // Sync add-on tags from string input if present
    const parsedAddOns = addOnInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    const txPayload: ProposedTransaction = {
      ...transaction,
      add_ons: parsedAddOns,
    };

    try {
      const evaluation = await api.evaluateMandatePolicy({
        mandate,
        transaction: txPayload,
        callerRole: 'human_user',
      });
      setResult(evaluation);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Policy evaluation request failed.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Preset Switcher */}
      <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-navy-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <ShieldCheck className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-white tracking-tight">
                TrustGate Intent-to-Payment Policy Simulator
              </h2>
              {isImported && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  Mandate Loaded from Intent
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Deterministic validation of candidate transactions against user purchase mandates.
              The policy engine operates with zero AI discretion—strict mathematical invariants determine authorization.
            </p>
          </div>

          {/* Quick-test Presets */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={loadCompliantPreset}
              className="px-3 py-1.5 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-700/50 text-xs font-mono text-emerald-300 transition-colors flex items-center gap-1.5"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Load Compliant Example</span>
            </button>

            <button
              type="button"
              onClick={loadViolatingPreset}
              className="px-3 py-1.5 rounded-lg bg-rose-950/40 hover:bg-rose-900/40 border border-rose-800/50 text-xs font-mono text-rose-300 transition-colors flex items-center gap-1.5"
            >
              <XCircle className="w-3.5 h-3.5 text-rose-400" />
              <span>Load Violating Example</span>
            </button>
          </div>
        </div>

        {/* Simulator Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
          {/* Left Column: Form Inputs (7 Cols) */}
          <form onSubmit={handleEvaluate} className="lg:col-span-7 space-y-6">
            {/* Section 1: Purchase Mandate */}
            <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-bold flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5" />
                  1. Purchase Mandate (User Intent Bounds)
                </span>
                <span className="text-[11px] text-slate-400 font-mono">Bound Constraints</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">
                    Maximum Budget Cap
                  </label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-2.5 flex items-center text-slate-500 font-mono">
                      {mandate.currency === 'INR' ? '₹' : mandate.currency === 'EUR' ? '€' : mandate.currency === 'GBP' ? '£' : '$'}
                    </span>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      value={mandate.max_amount}
                      onChange={(e) =>
                        setMandate({ ...mandate, max_amount: parseFloat(e.target.value) || 0 })
                      }
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 pl-6 pr-2.5 py-1.5 text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Currency</label>
                  <select
                    value={mandate.currency}
                    onChange={(e) => setMandate({ ...mandate, currency: e.target.value })}
                    className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2.5 py-1.5 text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                  >
                    <option value="INR">INR (₹)</option>
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="CAD">CAD ($)</option>
                    <option value="AUD">AUD ($)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Allowed Condition</label>
                  <select
                    value={mandate.allowed_conditions[0] || 'new'}
                    onChange={(e) =>
                      setMandate({ ...mandate, allowed_conditions: [e.target.value] })
                    }
                    className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2.5 py-1.5 text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                  >
                    <option value="new">New Only</option>
                    <option value="refurbished">Refurbished Only</option>
                    <option value="used">Used Only</option>
                  </select>
                </div>
              </div>

              {/* Toggles */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-navy-900/80 border border-navy-800 text-xs text-slate-300 cursor-pointer hover:border-navy-700">
                  <input
                    type="checkbox"
                    checked={mandate.require_merchant_verification}
                    onChange={(e) =>
                      setMandate({
                        ...mandate,
                        require_merchant_verification: e.target.checked,
                      })
                    }
                    className="rounded bg-navy-950 border-navy-700 text-emerald-500 focus:ring-0"
                  />
                  <span>Require Verified Merchant</span>
                </label>

                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-navy-900/80 border border-navy-800 text-xs text-slate-300 cursor-pointer hover:border-navy-700">
                  <input
                    type="checkbox"
                    checked={mandate.allow_add_ons}
                    onChange={(e) =>
                      setMandate({ ...mandate, allow_add_ons: e.target.checked })
                    }
                    className="rounded bg-navy-950 border-navy-700 text-emerald-500 focus:ring-0"
                  />
                  <span>Allow Add-Ons & Warranties</span>
                </label>
              </div>
            </div>

            {/* Section 2: Proposed Transaction */}
            <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-sky-400 font-bold flex items-center gap-1.5">
                  <Store className="w-3.5 h-3.5" />
                  2. Candidate Transaction (From Merchant)
                </span>
                <span className="text-[11px] text-slate-400 font-mono">Structured Payload</span>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Product Title</label>
                  <input
                    type="text"
                    value={transaction.product_name}
                    onChange={(e) =>
                      setTransaction({ ...transaction, product_name: e.target.value })
                    }
                    className="w-full rounded-lg bg-navy-900 border border-navy-700 px-3 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500"
                    placeholder="e.g. Keychron K2 Pro Keyboard"
                  />
                </div>

                {/* Itemized Pricing Matrix */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1">Base Price</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={transaction.product_price}
                      onChange={(e) =>
                        handlePriceChange('product_price', parseFloat(e.target.value) || 0)
                      }
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2 py-1 text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1">Shipping</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={transaction.shipping_cost}
                      onChange={(e) =>
                        handlePriceChange('shipping_cost', parseFloat(e.target.value) || 0)
                      }
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2 py-1 text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1">Sales Tax</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={transaction.tax}
                      onChange={(e) => handlePriceChange('tax', parseFloat(e.target.value) || 0)}
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2 py-1 text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1">Add'l Charges</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={transaction.additional_charges}
                      onChange={(e) =>
                        handlePriceChange('additional_charges', parseFloat(e.target.value) || 0)
                      }
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2 py-1 text-slate-100 font-mono"
                    />
                  </div>
                </div>

                {/* Checkout Total & Currency */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-center p-2.5 rounded-lg bg-navy-900 border border-navy-800">
                  <div className="sm:col-span-2">
                    <span className="text-[11px] text-slate-400 block">Final Checkout Total</span>
                    <span className="text-base font-bold font-mono text-white">
                      {transaction.currency} {transaction.final_total.toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-400 block">Tx Currency</span>
                    <select
                      value={transaction.currency}
                      onChange={(e) =>
                        setTransaction({ ...transaction, currency: e.target.value })
                      }
                      className="w-full rounded bg-navy-950 border border-navy-700 px-2 py-1 text-xs text-slate-100 font-mono"
                    >
                      <option value="INR">INR</option>
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                      <option value="GBP">GBP</option>
                    </select>
                  </div>
                </div>

                {/* Merchant & Condition */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="sm:col-span-2">
                    <label className="block text-slate-300 font-medium mb-1">Merchant Name</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={transaction.merchant_name}
                        onChange={(e) =>
                          setTransaction({ ...transaction, merchant_name: e.target.value })
                        }
                        className="flex-1 rounded-lg bg-navy-900 border border-navy-700 px-2.5 py-1.5 text-slate-100 focus:outline-none"
                      />
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer shrink-0">
                        <input
                          type="checkbox"
                          checked={transaction.merchant_verified}
                          onChange={(e) =>
                            setTransaction({
                              ...transaction,
                              merchant_verified: e.target.checked,
                            })
                          }
                          className="rounded bg-navy-950 border-navy-700 text-emerald-500"
                        />
                        <span>Verified</span>
                      </label>
                    </div>
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Condition</label>
                    <select
                      value={transaction.product_condition}
                      onChange={(e) =>
                        setTransaction({ ...transaction, product_condition: e.target.value })
                      }
                      className="w-full rounded-lg bg-navy-900 border border-navy-700 px-2.5 py-1.5 text-slate-100 font-mono"
                    >
                      <option value="new">new</option>
                      <option value="refurbished">refurbished</option>
                      <option value="used">used</option>
                    </select>
                  </div>
                </div>

                {/* Add-ons list input */}
                <div>
                  <label className="block text-slate-300 font-medium mb-1">
                    Candidate Add-Ons (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={addOnInput}
                    onChange={(e) => setAddOnInput(e.target.value)}
                    placeholder="e.g. Extended Warranty, Carrying Case (leave blank if none)"
                    className="w-full rounded-lg bg-navy-900 border border-navy-700 px-3 py-1.5 text-slate-100 font-sans focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Evaluate Action Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-navy-950 font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-emerald-glow disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Evaluating Deterministic Rules...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  <span>Execute Deterministic Policy Check</span>
                </>
              )}
            </button>
          </form>

          {/* Right Column: Policy Engine Evaluation Results (5 Cols) */}
          <div className="lg:col-span-5 space-y-4">
            {error && (
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs">
                <p className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                  Endpoint Connection Error
                </p>
                <p className="mt-1">{error}</p>
              </div>
            )}

            {!result && !isLoading && (
              <div className="rounded-xl border border-navy-800 bg-navy-950/60 p-8 text-center space-y-3">
                <Lock className="w-8 h-8 text-slate-600 mx-auto" />
                <h3 className="text-sm font-semibold text-slate-300">
                  Awaiting Mandate Evaluation
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Configure the purchase mandate and proposed transaction on the left, or pick one of the quick test presets above, then click Execute to test the backend policy engine.
                </p>
              </div>
            )}

            {result && (
              <div className="space-y-4 animate-in fade-in duration-200">
                {/* Result Card: APPROVED or BLOCKED */}
                <div
                  className={cn(
                    'p-5 rounded-xl border relative overflow-hidden',
                    result.approved
                      ? 'bg-emerald-950/30 border-emerald-500/40 shadow-emerald-glow'
                      : 'bg-rose-950/30 border-rose-700/50 shadow-card-glow'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={cn(
                          'p-2 rounded-lg border',
                          result.approved
                            ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
                            : 'bg-rose-500/20 border-rose-500/40 text-rose-400'
                        )}
                      >
                        {result.approved ? (
                          <ShieldCheck className="w-6 h-6 text-emerald-400" />
                        ) : (
                          <ShieldX className="w-6 h-6 text-rose-400" />
                        )}
                      </div>
                      <div>
                        <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400">
                          Deterministic Policy Decision
                        </span>
                        <h3
                          className={cn(
                            'text-xl font-extrabold font-mono tracking-tight',
                            result.approved ? 'text-emerald-400' : 'text-rose-400'
                          )}
                        >
                          {result.status}
                        </h3>
                      </div>
                    </div>

                    <span
                      className={cn(
                        'px-2.5 py-1 rounded-md text-xs font-mono font-bold uppercase border',
                        result.approved
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                      )}
                    >
                      {result.approved ? '0 VIOLATIONS' : `${result.violations.length} VIOLATION(S)`}
                    </span>
                  </div>

                  {/* Human readable explanation */}
                  <div className="mt-4 p-3 rounded-lg bg-navy-950/80 border border-navy-800 text-xs text-slate-200 leading-relaxed">
                    <p className="font-semibold text-white mb-1">Engine Summary:</p>
                    <p>{result.explanation}</p>
                  </div>

                  {/* Signature */}
                  <div className="mt-3 flex items-center justify-between text-[11px] font-mono text-slate-400 pt-2 border-t border-navy-800/80">
                    <span className="flex items-center gap-1 text-slate-500">
                      <Key className="w-3 h-3 text-emerald-400" />
                      Signature:
                    </span>
                    <span className="text-emerald-400 font-semibold truncate max-w-[200px]">
                      {result.policy_signature}
                    </span>
                  </div>
                </div>

                {/* Individual Checks Breakdown */}
                <div className="space-y-2">
                  <span className="text-xs font-mono uppercase tracking-wider text-slate-400 block font-semibold">
                    Individual Check Breakdown ({result.checks.length} Rules Evaluated)
                  </span>

                  <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                    {result.checks.map((check) => (
                      <div
                        key={check.rule_id}
                        className={cn(
                          'p-3 rounded-lg border text-xs transition-colors',
                          check.passed
                            ? 'bg-navy-950/70 border-emerald-900/30'
                            : 'bg-rose-950/20 border-rose-900/50'
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <div className="mt-0.5 shrink-0">
                              {check.passed ? (
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                              ) : (
                                <XCircle className="w-3.5 h-3.5 text-rose-400" />
                              )}
                            </div>
                            <div>
                              <div className="flex items-center gap-1.5 font-bold text-slate-200">
                                <span>{check.rule_name}</span>
                                <span className="font-mono text-[10px] text-slate-400 px-1 rounded bg-navy-900">
                                  {check.rule_id}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {check.description}
                              </p>
                              <p
                                className={cn(
                                  'text-[11px] font-mono mt-1',
                                  check.passed ? 'text-emerald-400/90' : 'text-rose-400 font-medium'
                                )}
                              >
                                {check.details}
                              </p>
                            </div>
                          </div>

                          <span
                            className={cn(
                              'shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded uppercase font-semibold border',
                              check.passed
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                            )}
                          >
                            {check.passed ? 'PASS' : 'FAIL'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Human-in-the-Loop Critical Notice */}
                <div className="p-3.5 rounded-xl bg-navy-950 border border-navy-800 text-xs text-slate-400 space-y-1">
                  <div className="flex items-center gap-1.5 text-slate-300 font-bold font-mono">
                    <Info className="w-3.5 h-3.5 text-amber-400" />
                    <span>Human Approval Separation Principle</span>
                  </div>
                  <p className="text-[11px] leading-relaxed">
                    A policy-approved transaction is strictly <strong className="text-white">NOT authorized</strong> for checkout automatically. TrustGate requires explicit user signature tokens before handoff to payment gateways.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
