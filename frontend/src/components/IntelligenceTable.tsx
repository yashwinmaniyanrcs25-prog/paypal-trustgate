import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Filter,
  X,
} from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatTimestamp, cn } from '../lib/utils';

type SortKey = 'created_at' | 'amount' | 'status' | 'product_name';
type SortDir = 'asc' | 'desc';
type StatusFilter = 'ALL' | 'STAGED' | 'HUMAN_APPROVED' | 'ORDER_CREATED' | 'CAPTURED' | 'CANCELLED' | 'HUMAN_REJECTED' | 'EXPIRED' | 'ORDER_CREATION_FAILED' | 'CAPTURE_FAILED';

interface Transaction {
  transaction_id: string;
  product_name: string;
  amount: number;
  currency: string;
  merchant_name?: string;
  policy_approved?: boolean;
  status: string;
  created_at: string;
  paypal_order_id?: string | null;
  capture_id?: string | null;
  updated_at?: string;
}

const STATUS_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  STAGED: { label: 'Staged', color: 'text-sky-400 bg-sky-500/10 border-sky-500/20', icon: Clock },
  HUMAN_APPROVED: { label: 'Approved', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', icon: CheckCircle2 },
  HUMAN_REJECTED: { label: 'Rejected', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20', icon: XCircle },
  ORDER_CREATED: { label: 'Checkout', color: 'text-violet-400 bg-violet-500/10 border-violet-500/20', icon: Clock },
  ORDER_CREATION_FAILED: { label: 'Order Failed', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20', icon: AlertTriangle },
  CAPTURED: { label: 'Captured', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', icon: CheckCircle2 },
  CAPTURE_FAILED: { label: 'Capture Failed', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20', icon: AlertTriangle },
  CANCELLED: { label: 'Cancelled', color: 'text-slate-400 bg-slate-500/10 border-slate-500/20', icon: XCircle },
  EXPIRED: { label: 'Expired', color: 'text-slate-400 bg-slate-500/10 border-slate-500/20', icon: Clock },
};

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const meta = STATUS_META[status] || { label: status, color: 'text-slate-400 bg-navy-800 border-navy-700', icon: Clock };
  const Icon = meta.icon;
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono font-semibold uppercase tracking-wider', meta.color)}>
      <Icon className="w-2.5 h-2.5" />
      {meta.label}
    </span>
  );
};

const PAGE_SIZE = 10;

interface IntelligenceTableProps {
  onSelectTransaction?: (txId: string) => void;
}

export const IntelligenceTable: React.FC<IntelligenceTableProps> = ({ onSelectTransaction }) => {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sort/filter/page
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [page, setPage] = useState(0);

  const fetchTransactions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getPersistedTransactions(100);
      setTransactions(res.transactions || []);
    } catch (e: any) {
      setError(e?.message || 'Failed to load transactions');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // Derived filtered & sorted data
  const processed = useMemo(() => {
    let data = [...transactions];

    // Search filter
    if (search.trim()) {
      const q = search.toLowerCase();
      data = data.filter(
        (t) =>
          t.transaction_id.toLowerCase().includes(q) ||
          t.product_name.toLowerCase().includes(q) ||
          (t.merchant_name || '').toLowerCase().includes(q) ||
          (t.paypal_order_id || '').toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter !== 'ALL') {
      data = data.filter((t) => t.status === statusFilter);
    }

    // Sort
    data.sort((a, b) => {
      let va: any = a[sortKey];
      let vb: any = b[sortKey];
      if (sortKey === 'amount') {
        va = Number(va);
        vb = Number(vb);
      } else {
        va = String(va ?? '');
        vb = String(vb ?? '');
      }
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return data;
  }, [transactions, search, statusFilter, sortKey, sortDir]);

  const totalPages = Math.ceil(processed.length / PAGE_SIZE);
  const paged = processed.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
    setPage(0);
  };

  const SortIcon: React.FC<{ col: SortKey }> = ({ col }) => {
    if (sortKey !== col) return <ArrowUpDown className="w-3 h-3 text-slate-600" />;
    return sortDir === 'asc' ? (
      <ArrowUp className="w-3 h-3 text-emerald-400" />
    ) : (
      <ArrowDown className="w-3 h-3 text-emerald-400" />
    );
  };

  const statuses: StatusFilter[] = [
    'ALL', 'STAGED', 'HUMAN_APPROVED', 'ORDER_CREATED', 'CAPTURED',
    'HUMAN_REJECTED', 'CANCELLED', 'ORDER_CREATION_FAILED', 'CAPTURE_FAILED', 'EXPIRED',
  ];

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900/90 shadow-card-glow overflow-hidden">
      {/* Table Header Controls */}
      <div className="p-4 border-b border-navy-800 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Transaction Intelligence Explorer</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {processed.length} transactions · Sortable · Filterable · Click to inspect
            </p>
          </div>
          <button
            onClick={fetchTransactions}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-navy-700 bg-navy-950 text-xs font-mono text-slate-400 hover:text-emerald-400 hover:border-navy-600 transition-all disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3 h-3', isLoading && 'animate-spin')} />
            Refresh
          </button>
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search by ID, product, merchant, order…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              className="w-full pl-8 pr-8 py-2 text-xs font-mono bg-navy-950 border border-navy-800 rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Status filter */}
          <div className="relative">
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setPage(0); }}
              className="pl-8 pr-8 py-2 text-xs font-mono bg-navy-950 border border-navy-800 rounded-lg text-slate-200 focus:outline-none focus:border-emerald-500/50 appearance-none cursor-pointer"
            >
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {s === 'ALL' ? 'All Statuses' : STATUS_META[s]?.label || s}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-navy-800 bg-navy-950/60">
              <th className="px-4 py-3 text-left">
                <button
                  onClick={() => handleSort('created_at')}
                  className="flex items-center gap-1 text-slate-500 hover:text-slate-200 uppercase tracking-wider text-[10px] font-semibold"
                >
                  Timestamp <SortIcon col="created_at" />
                </button>
              </th>
              <th className="px-4 py-3 text-left">
                <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                  Transaction ID
                </span>
              </th>
              <th className="px-4 py-3 text-left">
                <button
                  onClick={() => handleSort('product_name')}
                  className="flex items-center gap-1 text-slate-500 hover:text-slate-200 uppercase tracking-wider text-[10px] font-semibold"
                >
                  Product <SortIcon col="product_name" />
                </button>
              </th>
              <th className="px-4 py-3 text-right">
                <button
                  onClick={() => handleSort('amount')}
                  className="flex items-center gap-1 ml-auto text-slate-500 hover:text-slate-200 uppercase tracking-wider text-[10px] font-semibold"
                >
                  Amount <SortIcon col="amount" />
                </button>
              </th>
              <th className="px-4 py-3 text-left">
                <button
                  onClick={() => handleSort('status')}
                  className="flex items-center gap-1 text-slate-500 hover:text-slate-200 uppercase tracking-wider text-[10px] font-semibold"
                >
                  Status <SortIcon col="status" />
                </button>
              </th>
              <th className="px-4 py-3 text-left">
                <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                  PayPal Order
                </span>
              </th>
              <th className="px-4 py-3 text-left">
                <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                  Capture ID
                </span>
              </th>
              <th className="px-4 py-3 text-center">
                <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                  Inspect
                </span>
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-navy-800/60">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  {Array.from({ length: 8 }).map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-3 rounded bg-navy-800" style={{ width: `${60 + Math.random() * 30}%` }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center">
                  <div className="flex flex-col items-center gap-2 text-rose-400">
                    <AlertTriangle className="w-6 h-6" />
                    <span>{error}</span>
                    <button
                      onClick={fetchTransactions}
                      className="text-xs text-slate-400 hover:text-white underline"
                    >
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            ) : paged.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-14 text-center">
                  <div className="flex flex-col items-center gap-2 text-slate-600">
                    <Search className="w-8 h-8" />
                    <p className="text-sm">No transactions found</p>
                    <p className="text-xs">
                      {search || statusFilter !== 'ALL'
                        ? 'Try adjusting your search or filter.'
                        : 'Stage a proposal in the Agentic Proposal Flow to begin.'}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              paged.map((tx) => (
                <tr
                  key={tx.transaction_id}
                  className="hover:bg-navy-800/40 transition-colors group"
                >
                  <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-[10px]">
                    {formatTimestamp(tx.created_at)}
                    <div className="text-[9px] text-slate-700 mt-0.5">
                      {new Date(tx.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-slate-300 font-bold" title={tx.transaction_id}>
                      {tx.transaction_id.slice(0, 14)}…
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-slate-200 font-semibold truncate max-w-[180px]" title={tx.product_name}>
                      {tx.product_name}
                    </div>
                    {tx.merchant_name && (
                      <div className="text-slate-600 text-[10px] mt-0.5 truncate max-w-[180px]">
                        {tx.merchant_name}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <span className="text-emerald-400 font-bold">
                      {formatCurrency(tx.amount, tx.currency)}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <StatusBadge status={tx.status} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {tx.paypal_order_id ? (
                      <span
                        className="text-violet-400 font-mono text-[10px]"
                        title={tx.paypal_order_id}
                      >
                        {tx.paypal_order_id.slice(0, 12)}…
                      </span>
                    ) : (
                      <span className="text-slate-700">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {tx.capture_id ? (
                      <span
                        className="text-emerald-400 font-mono text-[10px]"
                        title={tx.capture_id}
                      >
                        {tx.capture_id.slice(0, 12)}…
                      </span>
                    ) : (
                      <span className="text-slate-700">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {onSelectTransaction && (
                      <button
                        onClick={() => onSelectTransaction(tx.transaction_id)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded border border-navy-700 bg-navy-950 text-slate-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all text-[10px]"
                        title="Open forensic detail view"
                      >
                        <ExternalLink className="w-3 h-3" />
                        View
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!isLoading && processed.length > PAGE_SIZE && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-navy-800 bg-navy-950/40 text-xs font-mono text-slate-500">
          <span>
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, processed.length)} of{' '}
            {processed.length}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1 rounded border border-navy-700 bg-navy-900 hover:border-navy-600 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            {Array.from({ length: totalPages }).map((_, i) => (
              <button
                key={i}
                onClick={() => setPage(i)}
                className={cn(
                  'w-6 h-6 rounded border text-[10px] transition-all',
                  i === page
                    ? 'bg-emerald-500 border-emerald-600 text-navy-950 font-bold'
                    : 'border-navy-700 bg-navy-900 hover:border-navy-600 text-slate-400'
                )}
              >
                {i + 1}
              </button>
            ))}
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded border border-navy-700 bg-navy-900 hover:border-navy-600 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

