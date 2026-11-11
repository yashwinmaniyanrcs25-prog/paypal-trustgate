import React from 'react';
import { ShieldCheck, Lock, Activity } from 'lucide-react';
import { SystemHealth } from '../types';

interface NavbarProps {
  health: SystemHealth | null;
}

export const Navbar: React.FC<NavbarProps> = ({ health }) => {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-navy-800 bg-navy-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-navy-900 border border-emerald-500/40 text-emerald-400 shadow-emerald-glow">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                PayPal
              </span>
              <span className="font-semibold text-lg text-emerald-400 tracking-tight">
                TrustGate
              </span>
              <span className="text-[10px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                v0.1
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium hidden sm:block">
              AI Payment Security Perimeter for Agentic Commerce
            </p>
          </div>
        </div>

        {/* Security badges & Environment */}
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-navy-900/90 border border-navy-700/60 text-xs font-mono">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Core Invariant:</span>
            <span className="text-emerald-400 font-semibold">Zero Autonomous AI Charge</span>
          </div>

          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-xs">
            <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span className="text-slate-300 font-medium hidden sm:inline">Engine:</span>
            <span className="font-semibold text-emerald-400 uppercase tracking-wider text-[11px]">
              {health?.security_policy.deterministic_guardrails || 'ENFORCED'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-navy-900 border border-navy-700/80 text-xs">
            <span className="h-2 w-2 rounded-full bg-paypal-blue"></span>
            <span className="font-mono text-slate-300 font-medium text-[11px]">
              PayPal Sandbox
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};

