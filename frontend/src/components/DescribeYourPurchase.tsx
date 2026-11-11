import React, { useState } from 'react';
import {
  Sparkles,
  ArrowRight,
  Send,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Tag,
  Edit3,
  Cpu,
  RefreshCw,
  Info,
} from 'lucide-react';
import { PurchaseMandate, IntentInterpretationResponse } from '../types';
import { api } from '../lib/api';

interface DescribeYourPurchaseProps {
  onConfirmMandate: (mandate: PurchaseMandate) => void;
}

const SAMPLE_PROMPTS = [
  {
    label: 'Brand New HP/Lenovo Laptop under ₹60,000 (16GB RAM / 512GB SSD)',
    text: 'Find me a brand new HP or Lenovo laptop under ₹60,000 on Amazon India with at least 16GB RAM, 512GB SSD, Intel Core i5 or better, sold by a verified seller, in stock only. No refurbished, no accessories.',
  },
  {
    label: 'Mechanical Keyboard under $140 (USD)',
    text: 'Find me an ergonomic mechanical keyboard under $140. Must be new condition from a verified merchant with no bundled add-ons.',
  },
  {
    label: 'Ambiguous Request (No Budget)',
    text: 'Looking for a high-end noise canceling headset for travel from an official brand.',
  },
];

export const DescribeYourPurchase: React.FC<DescribeYourPurchaseProps> = ({
  onConfirmMandate,
}) => {
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<IntentInterpretationResponse | null>(null);

  // Editable mandate state after interpretation
  const [editableMandate, setEditableMandate] = useState<PurchaseMandate | null>(null);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [hasUserEdited, setHasUserEdited] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setIsLoading(true);
    setError(null);
    setResponse(null);
    setEditableMandate(null);
    setIsConfirmed(false);
    setHasUserEdited(false);

    try {
      const res = await api.interpretPurchaseIntent(prompt.trim());
      setResponse(res);

      if (!res.success && res.error_message) {
        setError(res.error_message);
      } else if (res.mandate) {
        setEditableMandate(res.mandate);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to connect to the intent interpretation endpoint.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const applyPreset = (sampleText: string) => {
    setPrompt(sampleText);
  };

  const handleMandateChange = (field: keyof PurchaseMandate, val: any) => {
    if (!editableMandate) return;
    setEditableMandate({ ...editableMandate, [field]: val });
    setHasUserEdited(true);
  };

  const handleConfirm = () => {
    if (!editableMandate) return;
    setIsConfirmed(true);
    onConfirmMandate(editableMandate);
  };

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-navy-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shadow-emerald-glow">
            <Sparkles className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              <span>Describe Your Purchase</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Groq AI Interpreter
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Enter your natural-language purchasing instructions. Groq extracts structured mandate bounds without authorization privileges.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto text-[11px] font-mono text-slate-400 bg-navy-950 px-2.5 py-1 rounded-md border border-navy-800">
          <Cpu className="w-3.5 h-3.5 text-emerald-400" />
          <span>Groq (OpenAI-compatible)</span>
        </div>
      </div>

      {/* Preset Pills */}
      <div>
        <span className="text-xs text-slate-400 font-medium">Quick Sample Prompts:</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {SAMPLE_PROMPTS.map((sample, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => applyPreset(sample.text)}
              className="px-3 py-1.5 rounded-lg bg-navy-950 hover:bg-navy-800 border border-navy-800 hover:border-emerald-500/40 text-xs text-slate-300 hover:text-emerald-300 transition-colors flex items-center gap-1.5"
            >
              <span>{sample.label}</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
            </button>
          ))}
        </div>
      </div>

      {/* Natural Language Input Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5">
            Your Natural-Language Purchasing Request
          </label>
          <div className="relative">
            <textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. I need a new laptop under ₹60,000. Only buy from a verified seller. No refurbished products and no accessories."
              className="w-full rounded-lg bg-navy-950 border border-navy-700 p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors resize-none font-sans"
            />
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] text-slate-500 flex items-center gap-1">
            <Info className="w-3.5 h-3.5 text-slate-400" />
            Specify budget, condition, and seller preferences. Missing budgets will prompt for clarification.
          </span>

          <button
            type="submit"
            disabled={isLoading || !prompt.trim()}
            className="px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-navy-950 font-bold text-xs flex items-center gap-2 transition-all shadow-emerald-glow"
          >
            {isLoading ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Groq Interpreting Intent...</span>
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5" />
                <span>Interpret with Groq AI</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Error / Provider Unconfigured Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-xs text-rose-200 space-y-1">
          <div className="flex items-center gap-1.5 font-bold text-rose-300">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>Interpreter Notice</span>
          </div>
          <p className="leading-relaxed">{error}</p>
          {(error.includes('AI_API_KEY') || error.includes('AI_MODEL') || error.includes('XAI_API_KEY')) && (
            <p className="text-[11px] text-slate-400 font-mono mt-1">
              Tip: Ensure <code className="text-emerald-400">AI_API_KEY=gsk_...</code> and <code className="text-emerald-400">AI_MODEL=llama-3.3-70b-versatile</code> are set in <code className="text-white">backend/.env</code>.
            </p>
          )}
        </div>
      )}

      {/* Ambiguous Request / Clarification Requirement */}
      {response && response.needs_clarification && (
        <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-700/60 text-xs text-amber-200 space-y-2">
          <div className="flex items-center gap-2 font-bold text-amber-300">
            <HelpCircle className="w-4 h-4 text-amber-400" />
            <span>Clarification Required by Policy</span>
          </div>
          <p className="text-slate-300 leading-relaxed">
            {response.clarification_prompt ||
              'A maximum budget limit is required to establish a secure mandate. Please specify your maximum spending limit and currency.'}
          </p>
          <div className="pt-2 flex items-center gap-2 text-[11px] font-mono text-amber-400">
            <span>Intent Rule:</span>
            <span className="text-slate-300">
              The AI never guesses or fabricates a spending cap when the user did not declare one.
            </span>
          </div>
        </div>
      )}

      {/* Editable Review Screen for Interpreted Mandate */}
      {editableMandate && (
        <div className="p-5 rounded-xl bg-navy-950 border border-emerald-900/50 space-y-5 animate-in fade-in duration-200">
          {/* Status Badge Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-navy-800">
            <div className="flex items-center gap-2">
              <Edit3 className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-white">
                Mandate Review & Confirmation
              </h3>
            </div>

            {/* Distinction between AI interpreted and User confirmed */}
            <div className="flex items-center gap-2">
              {isConfirmed ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  USER CONFIRMED
                </span>
              ) : hasUserEdited ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-sky-500/20 text-sky-400 border border-sky-500/40">
                  <Edit3 className="w-3.5 h-3.5 text-sky-400" />
                  USER MODIFIED (Pending Confirmation)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                  AI INTERPRETED (Review & Confirm)
                </span>
              )}
            </div>
          </div>

          {/* AI Explanation / Summary */}
          {response?.extracted_intent_summary && (
            <div className="p-3 rounded-lg bg-navy-900 border border-navy-800 text-xs text-slate-300">
              <span className="font-mono text-emerald-400 font-bold block mb-1">
                Extracted Summary:
              </span>
              <p>{response.extracted_intent_summary}</p>
            </div>
          )}

          {/* Editable Fields Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            {/* Max Budget */}
            <div>
              <label className="block text-slate-300 font-medium mb-1.5">
                Maximum Budget Limit
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-mono">
                  {editableMandate.currency === 'INR' ? '₹' : editableMandate.currency === 'EUR' ? '€' : editableMandate.currency === 'GBP' ? '£' : '$'}
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  value={editableMandate.max_amount}
                  onChange={(e) =>
                    handleMandateChange('max_amount', parseFloat(e.target.value) || 0)
                  }
                  className="w-full rounded-lg bg-navy-900 border border-navy-700 pl-8 pr-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            {/* Currency */}
            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Currency</label>
              <select
                value={editableMandate.currency}
                onChange={(e) => handleMandateChange('currency', e.target.value)}
                className="w-full rounded-lg bg-navy-900 border border-navy-700 px-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500"
              >
                <option value="INR">INR (₹ Indian Rupee)</option>
                <option value="USD">USD ($ US Dollar)</option>
                <option value="EUR">EUR (€ Euro)</option>
                <option value="GBP">GBP (£ British Pound)</option>
                <option value="CAD">CAD ($ Canadian Dollar)</option>
                <option value="AUD">AUD ($ Australian Dollar)</option>
              </select>
            </div>

            {/* Allowed Condition */}
            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Allowed Condition</label>
              <select
                value={editableMandate.allowed_conditions[0] || 'new'}
                onChange={(e) =>
                  handleMandateChange('allowed_conditions', [e.target.value])
                }
                className="w-full rounded-lg bg-navy-900 border border-navy-700 px-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500"
              >
                <option value="new">New Only</option>
                <option value="refurbished">Refurbished Only</option>
                <option value="used">Used Only</option>
              </select>
            </div>
          </div>

          {/* Toggles */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <label className="flex items-center gap-2.5 p-3 rounded-lg bg-navy-900 border border-navy-800 text-xs text-slate-300 cursor-pointer hover:border-navy-700">
              <input
                type="checkbox"
                checked={editableMandate.require_merchant_verification}
                onChange={(e) =>
                  handleMandateChange('require_merchant_verification', e.target.checked)
                }
                className="rounded bg-navy-950 border-navy-700 text-emerald-500 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-white block">Require Verified Merchant</span>
                <span className="text-[11px] text-slate-400">
                  Transactions with unverified sellers will be blocked by policy.
                </span>
              </div>
            </label>

            <label className="flex items-center gap-2.5 p-3 rounded-lg bg-navy-900 border border-navy-800 text-xs text-slate-300 cursor-pointer hover:border-navy-700">
              <input
                type="checkbox"
                checked={editableMandate.allow_add_ons}
                onChange={(e) => handleMandateChange('allow_add_ons', e.target.checked)}
                className="rounded bg-navy-950 border-navy-700 text-emerald-500 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-white block">Allow Add-Ons & Warranties</span>
                <span className="text-[11px] text-slate-400">
                  If unchecked, unexpected accessory charges are strictly blocked.
                </span>
              </div>
            </label>
          </div>

          {/* Hardware & Product Specifications Identified */}
          {(editableMandate.min_ram_gb || editableMandate.min_storage_gb || editableMandate.processor_requirement || editableMandate.category || editableMandate.brand_preference || editableMandate.marketplace) && (
            <div className="p-3.5 rounded-lg bg-navy-900/80 border border-navy-800 space-y-2">
              <span className="text-[11px] font-mono text-emerald-400 uppercase tracking-wider block font-bold">
                Deterministic Hardware & Policy Guardrails:
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                {editableMandate.category && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Category</span>
                    <span className="font-semibold text-white">{editableMandate.category}</span>
                  </div>
                )}
                {editableMandate.brand_preference && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Brand</span>
                    <span className="font-semibold text-white">{editableMandate.brand_preference}</span>
                  </div>
                )}
                {editableMandate.min_ram_gb && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Min RAM</span>
                    <span className="font-semibold text-emerald-300 font-mono">{editableMandate.min_ram_gb} GB</span>
                  </div>
                )}
                {editableMandate.min_storage_gb && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Min Storage</span>
                    <span className="font-semibold text-emerald-300 font-mono">
                      {editableMandate.min_storage_gb} GB {editableMandate.storage_type || ''}
                    </span>
                  </div>
                )}
                {editableMandate.processor_requirement && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Processor</span>
                    <span className="font-semibold text-white">{editableMandate.processor_requirement}</span>
                  </div>
                )}
                {editableMandate.marketplace && (
                  <div className="p-2 rounded bg-navy-950 border border-navy-800">
                    <span className="text-slate-400 block text-[10px]">Marketplace</span>
                    <span className="font-semibold text-white">{editableMandate.marketplace}</span>
                  </div>
                )}
                <div className="p-2 rounded bg-navy-950 border border-navy-800">
                  <span className="text-slate-400 block text-[10px]">Availability</span>
                  <span className="font-semibold text-emerald-400">
                    {editableMandate.in_stock_required ? 'In-Stock Only' : 'Any'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* User Restrictions Tags */}
          {editableMandate.user_restrictions && editableMandate.user_restrictions.length > 0 && (
            <div>
              <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block mb-1.5">
                Identified User Restrictions:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {editableMandate.user_restrictions.map((restr, rIdx) => (
                  <span
                    key={rIdx}
                    className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-navy-900 text-slate-300 border border-navy-700"
                  >
                    <Tag className="w-2.5 h-2.5 text-emerald-400" />
                    {restr}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Confirmation & Handoff Action */}
          <div className="pt-3 border-t border-navy-800 flex flex-col sm:flex-row items-center justify-between gap-3">
            <span className="text-xs text-slate-400">
              Review and adjust constraints as needed. Click confirm to load into the Policy Simulator.
            </span>

            <button
              type="button"
              onClick={handleConfirm}
              className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-navy-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-emerald-glow"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Confirm & Load into Policy Simulator</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

