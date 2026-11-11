import React, { useState } from 'react';
import {
  Sparkles,
  ArrowRight,
  Send,
  Cpu,
  Layers,
  ShieldAlert,
  Tag,
  Store,
} from 'lucide-react';
import { AgentAnalysisResponse } from '../types';
import { formatCurrency } from '../lib/utils';

interface IntentConsoleProps {
  onAnalyze: (instruction: string, budget?: number) => void;
  analysis: AgentAnalysisResponse | null;
  isLoading: boolean;
  onProceedToPolicy: () => void;
}

const PRESET_PROMPTS = [
  {
    label: 'Mechanical Keyboard (Under $140)',
    instruction: 'Find me a wireless mechanical keyboard with tactile brown switches and US shipping under $140.',
    budget: 140,
  },
  {
    label: 'ANC Headphones (Under $175)',
    instruction: 'Recommend wireless noise-canceling headphones with 40-hour battery life under $175.',
    budget: 175,
  },
  {
    label: 'Over-Budget Test ($600 Monitor)',
    instruction: 'Find a 34-inch ultrawide curved gaming monitor with 144Hz refresh rate under $600.',
    budget: 600,
  },
];

export const IntentConsole: React.FC<IntentConsoleProps> = ({
  onAnalyze,
  analysis,
  isLoading,
  onProceedToPolicy,
}) => {
  const [instruction, setInstruction] = useState('');
  const [budgetCap, setBudgetCap] = useState<string>('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!instruction.trim()) return;
    const numericBudget = budgetCap ? parseFloat(budgetCap) : undefined;
    onAnalyze(instruction, numericBudget);
  };

  const applyPreset = (preset: typeof PRESET_PROMPTS[0]) => {
    setInstruction(preset.instruction);
    setBudgetCap(preset.budget.toString());
    onAnalyze(preset.instruction, preset.budget);
  };

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow p-5 sm:p-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-navy-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Agentic Intent Intake & Grok Reasoning
            </h2>
            <p className="text-xs text-slate-400">
              Users provide natural-language purchasing requests. Grok decomposes intent into structured constraints.
            </p>
          </div>
        </div>

        <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-navy-800 text-[11px] font-mono text-emerald-400 border border-navy-700">
          <Sparkles className="w-3 h-3" />
          Grok Propose-Only
        </span>
      </div>

      {/* Preset pills */}
      <div className="mt-4">
        <span className="text-xs text-slate-400 font-medium">Quick Test Scenarios:</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {PRESET_PROMPTS.map((preset, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => applyPreset(preset)}
              className="px-3 py-1.5 rounded-lg bg-navy-850 hover:bg-navy-800 border border-navy-700/80 text-xs text-slate-300 hover:text-emerald-300 transition-colors flex items-center gap-1.5"
            >
              <span>{preset.label}</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
            </button>
          ))}
        </div>
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="mt-5 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5">
            Natural-Language Purchasing Instruction
          </label>
          <div className="relative">
            <textarea
              rows={3}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="e.g. Find me a low-profile wireless mechanical keyboard under $150 with brown switches and US delivery..."
              className="w-full rounded-lg bg-navy-950 border border-navy-700 p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors font-sans resize-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div className="sm:col-span-1">
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Explicit Budget Cap (USD)
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500 text-xs font-mono">
                $
              </div>
              <input
                type="number"
                step="0.01"
                min="1"
                value={budgetCap}
                onChange={(e) => setBudgetCap(e.target.value)}
                placeholder="Auto-detect or enter max"
                className="w-full rounded-lg bg-navy-950 border border-navy-700 pl-7 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 font-mono"
              />
            </div>
          </div>

          <div className="sm:col-span-2 flex justify-end">
            <button
              type="submit"
              disabled={isLoading || !instruction.trim()}
              className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-navy-950 font-semibold text-sm flex items-center justify-center gap-2 transition-all shadow-emerald-glow"
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-navy-950 border-t-transparent rounded-full animate-spin" />
                  <span>Grok Parsing Intent...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Analyze with Grok</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Grok Analysis Output */}
      {analysis && (
        <div className="mt-6 pt-5 border-t border-navy-800 space-y-4 animate-in fade-in duration-300">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              Grok Decomposition Matrix
            </span>
            <span className="text-[11px] font-mono text-emerald-400 px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
              Confidence: {Math.round((analysis.proposed_product?.confidence_score || 0.95) * 100)}%
            </span>
          </div>

          {/* Reasoning summary alert */}
          <div className="p-3 rounded-lg bg-navy-950 border border-navy-800 text-xs text-slate-300">
            <p className="font-mono text-emerald-400 font-semibold mb-1">AI Reasoning Summary:</p>
            <p>{analysis.reasoning_summary}</p>
          </div>

          {/* Extracted Constraints Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800">
              <span className="text-slate-400 text-[11px] block">Extracted Budget Cap</span>
              <span className="text-white font-mono font-bold text-sm">
                {formatCurrency(analysis.extracted_constraints.max_budget)}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800">
              <span className="text-slate-400 text-[11px] block">Category Detected</span>
              <span className="text-white font-semibold truncate block">
                {analysis.extracted_constraints.allowed_categories[0] || 'General'}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800">
              <span className="text-slate-400 text-[11px] block">Destination</span>
              <span className="text-white font-mono font-semibold">
                {analysis.extracted_constraints.destination_country}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-navy-950 border border-navy-800">
              <span className="text-slate-400 text-[11px] block">Agent Privilege</span>
              <span className="text-amber-400 font-mono font-semibold text-[11px]">
                PROPOSAL_ONLY
              </span>
            </div>
          </div>

          {/* Proposed Product Card */}
          {analysis.proposed_product && (
            <div className="p-4 rounded-xl border border-navy-700 bg-navy-850/90 relative overflow-hidden">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Grok Proposed Item
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Store className="w-3 h-3 text-slate-500" />
                      {analysis.proposed_product.merchant}
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-white">
                    {analysis.proposed_product.title}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {analysis.proposed_product.description}
                  </p>
                </div>

                <div className="sm:text-right shrink-0">
                  <span className="text-xs text-slate-400 block">Unit Price</span>
                  <span className="text-lg font-bold font-mono text-emerald-400">
                    {formatCurrency(analysis.proposed_product.price)}
                  </span>
                  <span className="text-[11px] text-slate-400 block font-mono">
                    Shipping: {formatCurrency(analysis.proposed_product.shipping_cost)}
                  </span>
                </div>
              </div>

              {/* Matched specs tags */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {analysis.proposed_product.specs_matched.map((spec, sIdx) => (
                  <span
                    key={sIdx}
                    className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-navy-950 text-slate-300 border border-navy-700"
                  >
                    <Tag className="w-2.5 h-2.5 text-emerald-400" />
                    {spec}
                  </span>
                ))}
              </div>

              {/* Action: Send to Deterministic Policy Engine */}
              <div className="mt-4 pt-3 border-t border-navy-700/60 flex flex-col sm:flex-row items-center justify-between gap-3">
                <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  Proposal cannot be purchased until verified by deterministic rules.
                </span>

                <button
                  type="button"
                  onClick={onProceedToPolicy}
                  className="w-full sm:w-auto px-4 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500 text-emerald-300 hover:text-navy-950 border border-emerald-500/40 font-semibold text-xs transition-all flex items-center justify-center gap-1.5"
                >
                  <span>Evaluate Deterministic Rules</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

