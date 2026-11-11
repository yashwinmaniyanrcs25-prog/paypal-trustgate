import React from 'react';
import { LucideIcon } from 'lucide-react';
import { cn } from '../lib/utils';

interface StatusCardProps {
  title: string;
  value: string;
  subtitle: string;
  icon: LucideIcon;
  badgeText?: string;
  badgeType?: 'success' | 'warning' | 'info' | 'neutral';
  highlight?: boolean;
}

export const StatusCard: React.FC<StatusCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  badgeText,
  badgeType = 'neutral',
  highlight = false,
}) => {
  const badgeStyles = {
    success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    info: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
    neutral: 'bg-navy-800 text-slate-300 border-navy-700',
  };

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl border p-5 transition-all duration-200',
        'bg-navy-900/90 border-navy-800 shadow-card-glow hover:border-navy-700',
        highlight && 'border-emerald-500/30 bg-gradient-to-br from-navy-900 via-navy-900 to-emerald-950/20 shadow-emerald-glow'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            {title}
          </p>
          <h3 className="mt-1 text-xl font-bold tracking-tight text-white font-mono">
            {value}
          </h3>
        </div>
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border',
            highlight
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
              : 'bg-navy-800/80 border-navy-700 text-slate-300'
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-xs">
        <span className="text-slate-400 truncate pr-2">{subtitle}</span>
        {badgeText && (
          <span
            className={cn(
              'shrink-0 px-2 py-0.5 rounded text-[10px] font-mono font-medium border uppercase tracking-wider',
              badgeStyles[badgeType]
            )}
          >
            {badgeText}
          </span>
        )}
      </div>

      {highlight && (
        <div className="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-500 to-transparent opacity-80" />
      )}
    </div>
  );
};

