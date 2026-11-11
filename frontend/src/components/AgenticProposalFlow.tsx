import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  Search,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Layers,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  RefreshCw,
  Info,
  X,
  Ban,
  Check,
  Globe,
  KeyRound,
  FileText,
  ArrowRight,
  UserCheck,
} from 'lucide-react';
import {
  PurchaseMandate,
  CandidateEvaluation,
  ProposalSearchResponse,
  StageProposalResponse,
  MarketplaceStatus,
  MarketplaceIntegrationState, 
} from '../types';
import { api } from '../lib/api';
import { cn, extractErrorMessage, formatCurrency } from '../lib/utils';

interface AgenticProposalFlowProps {
  mandate: PurchaseMandate | null;
  onSelectMandateTab?: () => void;
  onProposalStaged?: (staged: StageProposalResponse) => void;
  onViewAuditTimeline?: (txId: string) => void;
  onNavigateToApprovals?: () => void;
}

const DEFAULT_DEMO_MANDATE_USD: PurchaseMandate = {
  max_amount: 150.0,
  currency: 'USD',
  category: 'keyboard',
  search_query: 'Keychron K2',
  allowed_conditions: ['new'],
  require_merchant_verification: true,
  allow_add_ons: false,
  user_restrictions: ['Keychron K2', 'US domestic shipping only'],
};

const DEFAULT_DEMO_MANDATE_INR: PurchaseMandate = {
  max_amount: 60000.0,
  currency: 'INR',
  category: 'laptop',
  search_query: 'laptop',
  allowed_conditions: ['new'],
  require_merchant_verification: true,
  allow_add_ons: false,
  user_restrictions: ['new laptop only', 'verified seller'],
};

const isConditionOrRestrictionPhrase = (term: string): boolean => {
  const lower = term.toLowerCase().trim();
  const prohibited = [
    'brand new only', 'brand new', 'brand-new', 'new only', 'new', 'refurbished',
    'used', 'verified seller', 'verified seller only', 'verified sellers',
    'no refurbished', 'no accessories', 'no refurbished products', 'no add-ons',
    'in stock only', 'in-stock only', 'in stock', 'amazon india only', 'amazon us only',
  ];
  return prohibited.includes(lower) || lower.startsWith('no ') || (lower.endsWith(' only') && !lower.includes('laptop') && !lower.includes('keyboard') && !lower.includes('mouse'));
};

const getInferredQuery = (mandate: PurchaseMandate | null): string => {
  if (!mandate) return 'laptop';
  if (mandate.search_query && mandate.search_query.trim()) {
    const sq = mandate.search_query.trim();
    if (!isConditionOrRestrictionPhrase(sq)) return sq;
  }
  if (mandate.category && mandate.category.trim()) {
    const cat = mandate.category.trim();
    if (!isConditionOrRestrictionPhrase(cat)) return cat;
  }
  if (mandate.user_restrictions && mandate.user_restrictions.length > 0) {
    for (const r of mandate.user_restrictions) {
      const lower = r.toLowerCase();
      if (lower.includes('laptop') || lower.includes('notebook')) return 'laptop';
      if (lower.includes('mouse') || lower.includes('mice')) return 'wireless mouse';
      if (lower.includes('keyboard') || lower.includes('keychron')) return 'Keychron K2';
    }
  }
  return 'laptop';
};

export const AgenticProposalFlow: React.FC<AgenticProposalFlowProps> = ({
  mandate: initialMandate,
  onSelectMandateTab,
  onProposalStaged,
  onViewAuditTimeline,
  onNavigateToApprovals,
}) => {
  // Selected Marketplace & Region
  const [selectedMarketplace, setSelectedMarketplace] = useState<'channel3' | 'amazon' | 'demo'>('demo');
  const [selectedRegion, setSelectedRegion] = useState<string>(
    initialMandate?.currency === 'USD' ? 'amazon.com' : 'amazon.in'
  );
  const [marketplaces, setMarketplaces] = useState<MarketplaceStatus[]>([]);
  const [isFetchingStatus, setIsFetchingStatus] = useState<boolean>(false);

  // Active Mandate
  const [activeMandate, setActiveMandate] = useState<PurchaseMandate>(
    initialMandate || DEFAULT_DEMO_MANDATE_INR
  );

  const [query, setQuery] = useState<string>(
    getInferredQuery(initialMandate || DEFAULT_DEMO_MANDATE_INR)
  );
  const [filterMode, setFilterMode] = useState<'all' | 'eligible' | 'unverified' | 'blocked'>('all');

  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [searchResponse, setSearchResponse] = useState<ProposalSearchResponse | null>(null);

  // Expanded card IDs for seeing the 7 policy checks
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});

  // Staged Proposal review modal
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateEvaluation | null>(null);
  const [stagedProposal, setStagedProposal] = useState<StageProposalResponse | null>(null);
  const [isStaging, setIsStaging] = useState(false);
  const [stageError, setStageError] = useState<string | null>(null);

  // Execute candidate search (resets pagination to page 1)
  const handleSearch = async (
    overrideQuery?: string,
    overrideMarketplace?: 'channel3' | 'amazon' | 'demo',
    overrideRegion?: string,
    overrideMandate?: PurchaseMandate
  ) => {
    const q = (overrideQuery !== undefined ? overrideQuery : query).trim();
    setQuery(q);
    const mkt = overrideMarketplace !== undefined ? overrideMarketplace : selectedMarketplace;
    const reg = overrideRegion !== undefined ? overrideRegion : selectedRegion;
    const mand = overrideMandate !== undefined ? overrideMandate : activeMandate;

    setIsLoading(true);
    setError(null);
    setPage(1);
    try {
      const res = await api.searchProposals({
        mandate: mand,
        query: q,
        marketplaceId: mkt,
        region: reg,
        page: 1,
        limit: 10,
      });
      setSearchResponse(res);
      if (res.query) {
        setQuery(res.query);
      }

      // Auto-expand first approved candidate for demonstration clarity
      const newExpanded: Record<string, boolean> = {};
      if (res.candidates.length > 0) {
        newExpanded[res.candidates[0].product.product_id] = true;
      }
      setExpandedCards(newExpanded);
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, 'Failed to search candidate products.');
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Load next page of results
  const handleLoadMore = async () => {
    if (!searchResponse || isLoadingMore) return;
    const nextPage = page + 1;
    setIsLoadingMore(true);
    try {
      const res = await api.searchProposals({
        mandate: activeMandate,
        query: query.trim(),
        marketplaceId: selectedMarketplace,
        region: selectedRegion,
        page: nextPage,
        limit: 10,
        page_token: searchResponse.next_page_token,
      });

      // Append deduplicated candidates
      const existingIds = new Set(searchResponse.candidates.map((c) => c.product.product_id));
      const freshCandidates = res.candidates.filter((c) => !existingIds.has(c.product.product_id));
      const mergedCandidates = [...searchResponse.candidates, ...freshCandidates];

      setSearchResponse({
        ...res,
        candidates: mergedCandidates,
        discovered_count: (searchResponse.discovered_count || searchResponse.total_count) + (res.discovered_count || res.candidates.length),
        enriched_count: (searchResponse.enriched_count || 0) + (res.enriched_count || 0),
        eligible_count: mergedCandidates.filter((c) => c.status === 'APPROVED' || c.approved).length,
        unverified_count: mergedCandidates.filter((c) => c.status === 'NEEDS_VERIFICATION').length,
        compliant_count: mergedCandidates.filter((c) => c.status === 'APPROVED' || c.approved).length,
        blocked_count: mergedCandidates.filter((c) => c.status === 'BLOCKED' || (!c.approved && c.status !== 'NEEDS_VERIFICATION')).length,
        total_count: mergedCandidates.length,
      });
      setPage(nextPage);
    } catch (err: unknown) {
      console.warn('Failed to load more products:', err);
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Sync if initialMandate changes from parent
  useEffect(() => {
    if (initialMandate) {
      setActiveMandate(initialMandate);
      const q = getInferredQuery(initialMandate);
      setQuery(q);
      const targetReg = initialMandate.currency.toUpperCase() === 'INR' ? 'amazon.in' : 'amazon.com';
      setSelectedRegion(targetReg);
      handleSearch(q, selectedMarketplace, targetReg, initialMandate);
    }
  }, [initialMandate]);

  // Fetch Marketplace Integration Statuses from backend
  const fetchMarketplaceStatuses = async () => {
    setIsFetchingStatus(true);
    try {
      const list = await api.getMarketplaces(selectedRegion);
      setMarketplaces(list);
    } catch (err) {
      console.warn('Failed to fetch marketplace statuses:', err);
    } finally {
      setIsFetchingStatus(false);
    }
  };

  useEffect(() => {
    fetchMarketplaceStatuses();
  }, [selectedRegion]);

  // Run initial search on mount
  useEffect(() => {
    handleSearch(query, selectedMarketplace, selectedRegion, activeMandate);
  }, [selectedMarketplace]);

  const toggleCardExpand = (productId: string) => {
    setExpandedCards((prev) => ({
      ...prev,
      [productId]: !prev[productId],
    }));
  };

  const handleSelectCandidate = async (candidate: CandidateEvaluation) => {
    if (!candidate.can_select || !candidate.approved) {
      return;
    }

    setSelectedCandidate(candidate);
    setIsStaging(true);
    setStageError(null);
    setStagedProposal(null);

    try {
      const staged = await api.stageProposal({
        mandate: activeMandate,
        candidate: candidate.product,
      });
      setStagedProposal(staged);
      if (onProposalStaged) {
        onProposalStaged(staged);
      }
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, 'Failed to stage candidate proposal.');
      setStageError(msg);
    } finally {
      setIsStaging(false);
    }
  };

  const closeReviewModal = () => {
    setSelectedCandidate(null);
    setStagedProposal(null);
    setStageError(null);
  };

  const getStatusBadge = (state?: MarketplaceIntegrationState) => {
    switch (state) {
      case 'Connected':
        return {
          bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
          dot: 'bg-emerald-400',
          label: 'Connected',
        };
      case 'Access Pending':
        return {
          bg: 'bg-sky-500/10 border-sky-500/30 text-sky-400',
          dot: 'bg-sky-400',
          label: 'Access Pending',
        };
      case 'Credentials Missing':
        return {
          bg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
          dot: 'bg-amber-400',
          label: 'Credentials Missing',
        };
      case 'Error':
        return {
          bg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
          dot: 'bg-rose-400',
          label: 'Error',
        };
      case 'Not Configured':
      default:
        return {
          bg: 'bg-slate-500/10 border-slate-500/30 text-slate-400',
          dot: 'bg-slate-400',
          label: 'Not Configured',
        };
    }
  };

  const ch3Status = marketplaces.find((m) => m.marketplace_id === 'channel3');
  const ch3Badge = getStatusBadge(ch3Status?.state || 'Connected');

  const amznStatus = marketplaces.find((m) => m.marketplace_id === 'amazon');
  const amznBadge = getStatusBadge(amznStatus?.state);

  // Filter candidates based on selected filterMode
  const filteredCandidates = (searchResponse?.candidates || []).filter((cand) => {
    if (filterMode === 'eligible') return cand.status === 'APPROVED' || cand.approved;
    if (filterMode === 'unverified') return cand.status === 'NEEDS_VERIFICATION';
    if (filterMode === 'blocked') return cand.status === 'BLOCKED' || (!cand.approved && cand.status !== 'NEEDS_VERIFICATION');
    return true;
  });

  const isAmazonDisconnected =
    selectedMarketplace === 'amazon' && amznStatus?.state !== 'Connected';
  const isChannel3Disconnected =
    selectedMarketplace === 'channel3' && ch3Status?.state !== 'Connected' && ch3Status !== undefined;

  return (
    <div className="space-y-6">
      {/* Mandate Summary Header Bar */}
      <div className="rounded-2xl border border-navy-800 bg-navy-900/80 p-5 shadow-card-glow backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-navy-800/80 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold">
                  Active TrustGate Mandate
                </span>
                {!initialMandate && (
                  <span className="px-2 py-0.5 rounded-full bg-navy-800 text-[10px] font-mono text-slate-400">
                    Default Test Bounds
                  </span>
                )}
              </div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Budget Cap:{' '}
                <span className="text-emerald-400">
                  {formatCurrency(activeMandate.max_amount, activeMandate.currency)}
                </span>
              </h2>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {onSelectMandateTab && (
              <button
                type="button"
                onClick={onSelectMandateTab}
                className="px-3 py-1.5 rounded-lg bg-navy-800 hover:bg-navy-700 border border-navy-700 text-xs font-mono text-slate-300 hover:text-white transition-all flex items-center gap-1.5"
              >
                <span>Edit in Tab 1</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setActiveMandate(DEFAULT_DEMO_MANDATE_USD);
                setSelectedRegion('amazon.com');
                setSelectedMarketplace('demo');
                setQuery('Keychron K2');
                handleSearch('Keychron K2', 'demo', 'amazon.com', DEFAULT_DEMO_MANDATE_USD);
              }}
              className="px-3 py-1.5 rounded-lg bg-navy-800/60 hover:bg-navy-800 border border-navy-800 text-xs font-mono text-slate-400 hover:text-slate-200 transition-all"
            >
              $150 USD Keychron Preset
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveMandate(DEFAULT_DEMO_MANDATE_INR);
                setSelectedRegion('amazon.in');
                setSelectedMarketplace('demo');
                setQuery('laptop');
                handleSearch('laptop', 'demo', 'amazon.in', DEFAULT_DEMO_MANDATE_INR);
              }}
              className="px-3 py-1.5 rounded-lg bg-navy-800/60 hover:bg-navy-800 border border-navy-800 text-xs font-mono text-slate-400 hover:text-slate-200 transition-all"
            >
              ₹60,000 INR (amazon.in)
            </button>
          </div>
        </div>

        {/* Mandate Constraints Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-navy-950/60 border border-navy-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">Permitted Condition</span>
            <span className="text-slate-200 font-semibold">
              {activeMandate.allowed_conditions.join(', ').toUpperCase()}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-navy-950/60 border border-navy-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">Merchant Verification</span>
            <span
              className={cn(
                'font-semibold flex items-center gap-1',
                activeMandate.require_merchant_verification ? 'text-emerald-400' : 'text-slate-400'
              )}
            >
              {activeMandate.require_merchant_verification ? (
                <>
                  <Check className="w-3 h-3" /> Mandatory
                </>
              ) : (
                'Optional'
              )}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-navy-950/60 border border-navy-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">Add-Ons & Extras</span>
            <span
              className={cn(
                'font-semibold',
                activeMandate.allow_add_ons ? 'text-amber-400' : 'text-slate-300'
              )}
            >
              {activeMandate.allow_add_ons ? 'Allowed' : 'Prohibited (Strict)'}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-navy-950/60 border border-navy-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">User Restrictions</span>
            <span className="text-slate-300 truncate block">
              {activeMandate.user_restrictions && activeMandate.user_restrictions.length > 0
                ? activeMandate.user_restrictions.join('; ')
                : 'None'}
            </span>
          </div>
        </div>
      </div>

      {/* Marketplace Selector & Region Architecture Header */}
      <div className="rounded-2xl border border-navy-800 bg-navy-900/60 p-5 space-y-4 shadow-card-glow">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-navy-800/60 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold">
                Marketplace Provider Architecture
              </span>
              <span className="px-2 py-0.5 rounded-full bg-navy-950 text-[10px] font-mono text-slate-400 border border-navy-800">
                Official API Adapters
              </span>
            </div>
            <h3 className="text-base font-bold text-white mt-1">
              Select Commerce Marketplace & Region
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              TrustGate integrates through official marketplace provider adapters. No unofficial web scraping or phantom data.
            </p>
          </div>

          {/* Marketplace Selector Tabs */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Channel3 Marketplace Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedMarketplace('channel3');
                handleSearch(query, 'channel3', 'global');
              }}
              className={cn(
                'px-4 py-2.5 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2.5 border',
                selectedMarketplace === 'channel3'
                  ? 'bg-navy-800 text-white border-emerald-500/50 shadow-emerald-glow/20'
                  : 'bg-navy-950 text-slate-400 hover:text-white border-navy-800'
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight">Channel3</span>
                <span className="text-[10px] font-normal text-slate-400">Universal Graph</span>
              </div>
              <span
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] border font-mono',
                  ch3Badge.bg
                )}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full', ch3Badge.dot)} />
                {ch3Badge.label}
              </span>
            </button>

            {/* Amazon Marketplace Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedMarketplace('amazon');
                handleSearch(query, 'amazon', selectedRegion);
              }}
              className={cn(
                'px-4 py-2.5 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2.5 border',
                selectedMarketplace === 'amazon'
                  ? 'bg-navy-800 text-white border-emerald-500/50 shadow-emerald-glow/20'
                  : 'bg-navy-950 text-slate-400 hover:text-white border-navy-800'
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight">Amazon</span>
                <span className="text-[10px] font-normal text-slate-400">Creators API</span>
              </div>
              <span
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] border font-mono',
                  amznBadge.bg
                )}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full', amznBadge.dot)} />
                {amznBadge.label}
              </span>
            </button>

            {/* Demo Catalog Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedMarketplace('demo');
                handleSearch(query, 'demo', selectedRegion === 'amazon.in' ? 'demo_in' : 'demo_us');
              }}
              className={cn(
                'px-4 py-2.5 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2.5 border',
                selectedMarketplace === 'demo'
                  ? 'bg-navy-800 text-white border-emerald-500/50 shadow-emerald-glow/20'
                  : 'bg-navy-950 text-slate-400 hover:text-white border-navy-800'
              )}
            >
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>TrustGate Demo Fixtures</span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono">
                7 Rules Active
              </span>
            </button>
          </div>
        </div>

        {/* Region Selector Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-2">
            <Globe className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400 font-semibold">Marketplace Region:</span>
            <div className="inline-flex rounded-lg bg-navy-950 p-1 border border-navy-800">
              <button
                type="button"
                onClick={() => {
                  setSelectedRegion('amazon.in');
                  let newMandate = activeMandate;
                  if (activeMandate.currency !== 'INR') {
                    const newAmount = activeMandate.max_amount <= 150 ? 60000 : Math.round(activeMandate.max_amount * 83);
                    newMandate = {
                      ...activeMandate,
                      currency: 'INR',
                      max_amount: newAmount,
                    };
                    setActiveMandate(newMandate);
                  }
                  handleSearch(query, selectedMarketplace, 'amazon.in', newMandate);
                }}
                className={cn(
                  'px-3 py-1 rounded-md transition-all font-semibold',
                  selectedRegion === 'amazon.in'
                    ? 'bg-emerald-500 text-navy-950 font-bold shadow-emerald-glow'
                    : 'text-slate-400 hover:text-white'
                )}
              >
                Amazon India (amazon.in - INR ₹)
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedRegion('amazon.com');
                  let newMandate = activeMandate;
                  if (activeMandate.currency !== 'USD') {
                    const newAmount = activeMandate.max_amount >= 60000 ? 720 : Math.round(activeMandate.max_amount / 83);
                    newMandate = {
                      ...activeMandate,
                      currency: 'USD',
                      max_amount: newAmount,
                    };
                    setActiveMandate(newMandate);
                  }
                  handleSearch(query, selectedMarketplace, 'amazon.com', newMandate);
                }}
                className={cn(
                  'px-3 py-1 rounded-md transition-all font-semibold',
                  selectedRegion === 'amazon.com'
                    ? 'bg-emerald-500 text-navy-950 font-bold shadow-emerald-glow'
                    : 'text-slate-400 hover:text-white'
                )}
              >
                Amazon US (amazon.com - USD $)
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 text-slate-400 text-[11px]">
            <span>Freshness:</span>
            <span className="text-slate-200">
              {searchResponse?.data_freshness || 'Verified Provider'}
            </span>
            <button
              type="button"
              onClick={fetchMarketplaceStatuses}
              disabled={isFetchingStatus}
              className="p-1 text-slate-400 hover:text-white transition-all ml-1"
              title="Refresh integration status"
            >
              <RefreshCw className={cn('w-3 h-3', isFetchingStatus && 'animate-spin')} />
            </button>
          </div>
        </div>

        {/* Informative Status Card When Channel3 is NOT Connected */}
        {selectedMarketplace === 'channel3' && isChannel3Disconnected && (
          <div className="rounded-xl border border-amber-500/40 bg-gradient-to-r from-amber-950/40 via-navy-950/80 to-navy-950/80 p-4 space-y-3 font-mono text-xs">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 shrink-0">
                  <KeyRound className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-amber-300">
                      Channel3 Universal Graph Status: {ch3Status?.state || 'Not Connected'}
                    </span>
                    <span className="px-2 py-0.2 rounded bg-amber-500/10 text-amber-400 text-[10px] border border-amber-500/20">
                      API Key Required
                    </span>
                  </div>
                  <p className="text-slate-300 text-[11px] mt-0.5 leading-relaxed">
                    {ch3Status?.message ||
                      'Channel3 API key is not configured in backend/.env. Set CHANNEL3_API_KEY to search live items across Target, Best Buy, and Walmart.'}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  setSelectedMarketplace('demo');
                  handleSearch(query, 'demo', 'demo_us');
                }}
                className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-[11px] shrink-0 shadow-emerald-glow transition-all flex items-center gap-1"
              >
                <span>Switch to Demo Fixtures</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}

        {/* Informative Status Card When Amazon is NOT Connected */}
        {selectedMarketplace === 'amazon' && isAmazonDisconnected && (
          <div className="rounded-xl border border-amber-500/40 bg-gradient-to-r from-amber-950/40 via-navy-950/80 to-navy-950/80 p-4 space-y-3 font-mono text-xs">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 shrink-0">
                  <KeyRound className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-amber-300">
                      Amazon Creators API Integration Status: {amznStatus?.state || 'Not Configured'}
                    </span>
                    <span className="px-2 py-0.2 rounded bg-amber-500/10 text-amber-400 text-[10px] border border-amber-500/20">
                      Access Required
                    </span>
                  </div>
                  <p className="text-slate-300 text-[11px] mt-0.5 leading-relaxed">
                    {amznStatus?.message ||
                      'Amazon Creators API credentials are not configured on the backend. No unofficial scraping, page harvesting, or synthetic Amazon products are generated.'}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  setSelectedMarketplace('demo');
                  handleSearch(query, 'demo', selectedRegion === 'amazon.in' ? 'demo_in' : 'demo_us');
                }}
                className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-[11px] shrink-0 shadow-emerald-glow transition-all flex items-center gap-1"
              >
                <span>Switch to Demo Fixtures</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {/* Setup Guidance Box */}
            <div className="p-3 rounded-lg bg-navy-950/90 border border-navy-800 space-y-1.5 text-[11px]">
              <div className="flex items-center gap-1.5 text-slate-200 font-bold">
                <FileText className="w-3.5 h-3.5 text-amber-400" />
                <span>Backend Configuration Setup (.env):</span>
              </div>
              <p className="text-slate-400 leading-relaxed">
                Add your official Amazon Creators API credentials to{' '}
                <code className="text-emerald-400 font-bold">backend/.env</code>:
              </p>
              <pre className="p-2 rounded bg-navy-900 border border-navy-800/80 text-[10px] text-slate-300 overflow-x-auto">
                {`AMAZON_CREDENTIAL_ID=your_amazon_credential_id\nAMAZON_CREDENTIAL_SECRET=your_amazon_credential_secret\nAMAZON_CREDENTIAL_VERSION=2.1\nAMAZON_PARTNER_TAG=your_partner_tag\nAMAZON_MARKETPLACE=${selectedRegion === 'amazon.in' ? 'www.amazon.in' : 'www.amazon.com'}`}
              </pre>
              <div className="text-[10px] text-slate-500 pt-1 flex items-center gap-1">
                <Info className="w-3 h-3 text-slate-400 shrink-0" />
                <span>
                  Licensing notice: Product data is subject to Amazon's Operating Agreement. Intended use must be checked against Amazon's current API license.
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Legal Disclaimer Box */}
        {selectedMarketplace === 'amazon' && (
          <div className="p-3 rounded-xl bg-navy-950/60 border border-navy-800/80 text-[11px] font-mono text-slate-400 flex items-start gap-2">
            <Info className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="text-slate-300 font-semibold block">
                Amazon Creators API Policy & Licensing Notice:
              </span>
              <p className="leading-relaxed">
                {amznStatus?.legal_disclaimer ||
                  "Amazon Creators API Integration. Product data, pricing, and availability are subject to Amazon's Operating Agreement and Creators API License. Intended use must be checked against Amazon's current API license and any required written approval. TrustGate strictly prohibits web scraping, unauthorized data extraction, or automated transactions without explicit Amazon authorization."}
              </p>
            </div>
          </div>
        )}

        {/* Search Query Input Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSearch(query);
            }}
            className="flex-1 flex items-center gap-2"
          >
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${selectedMarketplace === 'amazon' ? 'Amazon ' + selectedRegion : 'demo catalog'} (e.g. laptop, mechanical keyboard)...`}
                className="w-full bg-navy-950 border border-navy-700/80 rounded-xl pl-10 pr-4 py-2.5 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-navy-950 font-mono font-bold text-xs rounded-xl flex items-center gap-2 shadow-emerald-glow transition-all"
            >
              {isLoading ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              <span>Discover & Evaluate</span>
            </button>
          </form>

          {/* Filter Pills */}
          {searchResponse && searchResponse.total_count > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setFilterMode('all')}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-mono transition-all',
                  filterMode === 'all'
                    ? 'bg-navy-800 text-white font-bold border border-navy-700'
                    : 'text-slate-500 hover:text-slate-300'
                )}
              >
                All ({searchResponse.total_count})
              </button>
              <button
                type="button"
                onClick={() => setFilterMode('eligible')}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-mono transition-all flex items-center gap-1',
                  filterMode === 'eligible'
                    ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40'
                    : 'text-emerald-500/70 hover:text-emerald-400'
                )}
              >
                <Check className="w-3 h-3" /> Eligible ({searchResponse.eligible_count ?? searchResponse.compliant_count})
              </button>
              <button
                type="button"
                onClick={() => setFilterMode('unverified')}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-mono transition-all flex items-center gap-1',
                  filterMode === 'unverified'
                    ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                    : 'text-amber-500/70 hover:text-amber-400'
                )}
              >
                <AlertTriangle className="w-3 h-3" /> Needs Verification ({searchResponse.unverified_count ?? 0})
              </button>
              <button
                type="button"
                onClick={() => setFilterMode('blocked')}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-mono transition-all flex items-center gap-1',
                  filterMode === 'blocked'
                    ? 'bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40'
                    : 'text-rose-500/70 hover:text-rose-400'
                )}
              >
                <Ban className="w-3 h-3" /> Blocked ({searchResponse.blocked_count})
              </button>
            </div>
          )}
        </div>

        {/* Discovery & Metadata Enrichment Telemetry Banner */}
        {searchResponse && searchResponse.total_count > 0 && (
          <div className="pt-2 border-t border-navy-800/60 flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-slate-400">
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                Discovered: <strong className="text-white">{searchResponse.discovered_count || searchResponse.total_count}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                Enriched: <strong className="text-sky-300">{searchResponse.enriched_count || 0}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Eligible: <strong className="text-emerald-300">{searchResponse.eligible_count ?? searchResponse.compliant_count}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Needs Verification: <strong className="text-amber-300">{searchResponse.unverified_count || 0}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                Blocked: <strong className="text-rose-300">{searchResponse.blocked_count}</strong>
              </span>
            </div>
            {searchResponse.page && searchResponse.page > 1 && (
              <span className="text-[10px] text-slate-500">
                Page {searchResponse.page} of {searchResponse.total_pages || searchResponse.page}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{extractErrorMessage(error, 'An unexpected error occurred during product discovery.')}</span>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div
              key={idx}
              className="rounded-2xl border border-navy-800 bg-navy-900/40 p-5 space-y-4 animate-pulse"
            >
              <div className="h-40 bg-navy-950 rounded-xl" />
              <div className="h-4 bg-navy-800 rounded w-3/4" />
              <div className="h-3 bg-navy-800 rounded w-1/2" />
              <div className="h-8 bg-navy-950 rounded-xl" />
            </div>
          ))}
        </div>
      )}

      {/* Unconfigured Amazon State: Clear explanation of zero synthetic data */}
      {!isLoading && selectedMarketplace === 'amazon' && isAmazonDisconnected && (
        <div className="p-10 text-center rounded-2xl border border-navy-800 bg-navy-900/40 space-y-3 font-mono">
          <KeyRound className="w-8 h-8 text-amber-400 mx-auto" />
          <h3 className="text-sm font-bold text-white">
            0 Live Amazon Products (Access State: {amznStatus?.state || 'Not Configured'})
          </h3>
          <p className="text-xs text-slate-400 max-w-lg mx-auto leading-relaxed">
            TrustGate never generates fabricated Amazon items or parses unapproved web pages.
            To test candidate evaluation and the 7 TrustGate policy invariants, switch to the{' '}
            <strong className="text-emerald-400">TrustGate Demo Fixtures</strong> marketplace.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={() => {
                setSelectedMarketplace('demo');
                handleSearch(query, 'demo', selectedRegion === 'amazon.in' ? 'demo_in' : 'demo_us');
              }}
              className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-xs shadow-emerald-glow transition-all"
            >
              Switch to TrustGate Demo Catalog
            </button>
          </div>
        </div>
      )}

      {/* Unconfigured Channel3 State */}
      {!isLoading && selectedMarketplace === 'channel3' && isChannel3Disconnected && (
        <div className="p-10 text-center rounded-2xl border border-navy-800 bg-navy-900/40 space-y-3 font-mono">
          <KeyRound className="w-8 h-8 text-amber-400 mx-auto" />
          <h3 className="text-sm font-bold text-white">
            0 Live Channel3 Products (Access State: {ch3Status?.state || 'Not Configured'})
          </h3>
          <p className="text-xs text-slate-400 max-w-lg mx-auto leading-relaxed">
            Channel3 API credentials are required to query the universal product graph.
            To test candidate evaluation and TrustGate policy invariants, switch to the{' '}
            <strong className="text-emerald-400">TrustGate Demo Fixtures</strong> marketplace.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={() => {
                setSelectedMarketplace('demo');
                handleSearch(query, 'demo', 'demo_us');
              }}
              className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-xs shadow-emerald-glow transition-all"
            >
              Switch to TrustGate Demo Catalog
            </button>
          </div>
        </div>
      )}

      {/* Candidates Grid (When Connected Amazon, Channel3, or Demo) */}
      {!isLoading && searchResponse && (
        (selectedMarketplace === 'amazon' && !isAmazonDisconnected) ||
        (selectedMarketplace === 'channel3' && !isChannel3Disconnected) ||
        selectedMarketplace === 'demo'
      ) && (
        <>
          {filteredCandidates.length === 0 ? (
            <div className="p-12 text-center rounded-2xl border border-navy-800 bg-navy-900/40 space-y-3">
              <Info className="w-8 h-8 text-slate-500 mx-auto" />
              <h3 className="text-sm font-bold text-slate-300 font-mono">No Candidates Found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                No items matched the filter criteria for &quot;{query}&quot;. Try selecting &quot;All&quot; or searching another term.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredCandidates.map((cand) => {
                const isExpanded = !!expandedCards[cand.product.product_id];
                const budgetDiff = cand.budget_remaining;
                const isUnderBudget = budgetDiff >= 0;

                return (
                  <div
                    key={cand.product.product_id}
                    className={cn(
                      'rounded-2xl border transition-all duration-300 flex flex-col justify-between overflow-hidden',
                      cand.approved
                        ? 'border-emerald-500/40 bg-gradient-to-b from-navy-900/90 to-emerald-950/20 shadow-emerald-glow/20 hover:border-emerald-500/60'
                        : cand.status === 'NEEDS_VERIFICATION'
                        ? 'border-amber-500/40 bg-gradient-to-b from-navy-900/80 to-amber-950/20 hover:border-amber-500/50'
                        : 'border-rose-500/30 bg-gradient-to-b from-navy-900/80 to-rose-950/20 hover:border-rose-500/50'
                    )}
                  >
                    {/* Card Top: Image & Policy Status Badge */}
                    <div>
                      <div className="relative h-44 w-full bg-navy-950 overflow-hidden border-b border-navy-800/80">
                        {cand.product.image_url ? (
                          <img
                            src={cand.product.image_url}
                            alt={cand.product.name}
                            className="w-full h-full object-cover object-center opacity-85 hover:scale-105 transition-all duration-300"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-slate-600 font-mono text-xs">
                            No Preview Available
                          </div>
                        )}

                        {/* Top-Right Policy Engine Verdict Badge */}
                        <div className="absolute top-3 right-3">
                          {cand.approved ? (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500 text-navy-950 shadow-emerald-glow">
                              <ShieldCheck className="w-3.5 h-3.5" />
                              ELIGIBLE (APPROVED)
                            </span>
                          ) : cand.status === 'NEEDS_VERIFICATION' ? (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold bg-amber-500 text-navy-950 shadow-amber-glow">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              NEEDS VERIFICATION
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold bg-rose-500 text-white shadow-rose-glow">
                              <ShieldAlert className="w-3.5 h-3.5" />
                              BLOCKED
                            </span>
                          )}
                        </div>

                        {/* Top-Left Data Source Tag */}
                        <div className="absolute top-3 left-3 flex items-center gap-1.5 flex-wrap max-w-[70%]">
                          {cand.product.marketplace_id === 'channel3' || cand.product.data_source === 'channel3_api' ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] font-mono bg-emerald-950/90 backdrop-blur-md text-emerald-300 border border-emerald-500/50 font-bold shadow-emerald-glow/20">
                              <Sparkles className="w-3 h-3 text-emerald-400" />
                              Channel3 Live
                            </span>
                          ) : cand.product.marketplace_id === 'amazon' ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono bg-navy-950/80 backdrop-blur-md text-slate-300 border border-navy-700/60">
                              Amazon ({cand.product.region || 'Official'})
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono bg-amber-950/80 backdrop-blur-md text-amber-300 border border-amber-700/60 font-semibold">
                              Demo Fixture
                            </span>
                          )}
                          {cand.product.availability && (
                            <span className={cn(
                              "inline-flex items-center px-2 py-0.5 rounded text-[9px] font-mono font-bold border",
                              cand.product.availability.toLowerCase().includes("out")
                                ? "bg-rose-950/90 text-rose-300 border-rose-700"
                                : "bg-emerald-950/90 text-emerald-300 border-emerald-700"
                            )}>
                              {cand.product.availability.toLowerCase().includes("out") ? "Out of Stock" : "In Stock"}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Card Body */}
                      <div className="p-5 space-y-3">
                        {/* Title and Category */}
                        <div>
                          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                            {cand.product.category}
                          </span>
                          <h3 className="text-sm font-bold text-white line-clamp-1">
                            {cand.product.name}
                          </h3>
                          <p className="text-xs text-slate-400 line-clamp-2 mt-1">
                            {cand.product.description}
                          </p>
                        </div>

                        {/* Hardware Specifications Chips */}
                        {(cand.product.ram_gb || cand.product.storage_gb || cand.product.processor || cand.product.screen_size || cand.product.brand) && (
                          <div className="flex flex-wrap gap-1.5 pt-0.5 text-[10px] font-mono">
                            {cand.product.brand && (
                              <span className="px-2 py-0.5 rounded bg-navy-950 border border-navy-700/80 text-slate-300 font-semibold">
                                {cand.product.brand}
                              </span>
                            )}
                            {cand.product.ram_gb && (
                              <span className="px-2 py-0.5 rounded bg-navy-950 border border-emerald-500/30 text-emerald-300 font-semibold">
                                {cand.product.ram_gb} GB RAM
                              </span>
                            )}
                            {cand.product.storage_gb && (
                              <span className="px-2 py-0.5 rounded bg-navy-950 border border-emerald-500/30 text-emerald-300 font-semibold">
                                {cand.product.storage_gb} GB {cand.product.storage_type || 'Storage'}
                              </span>
                            )}
                            {cand.product.processor && (
                              <span className="px-2 py-0.5 rounded bg-navy-950 border border-sky-500/30 text-sky-300 font-semibold">
                                {cand.product.processor}
                              </span>
                            )}
                            {cand.product.screen_size && (
                              <span className="px-2 py-0.5 rounded bg-navy-950 border border-navy-700/80 text-slate-400">
                                {cand.product.screen_size}
                              </span>
                            )}
                          </div>
                        )}

                        {/* Price & Budget Delta */}
                        <div className="p-3 rounded-xl bg-navy-950/80 border border-navy-800 flex items-center justify-between">
                          <div>
                            <span className="text-[10px] font-mono uppercase text-slate-500 block">
                              Proposed Price
                            </span>
                            <span className="text-base font-bold font-mono text-white">
                              {formatCurrency(cand.product.price, cand.currency || cand.product.currency)}
                            </span>
                          </div>

                          <div className="text-right">
                            <span className="text-[10px] font-mono uppercase text-slate-500 block">
                              Budget Remaining
                            </span>
                            <span
                              className={cn(
                                'text-xs font-bold font-mono',
                                isUnderBudget ? 'text-emerald-400' : 'text-rose-400'
                              )}
                            >
                              {isUnderBudget
                                ? `+${formatCurrency(budgetDiff, cand.currency || cand.product.currency)} under limit`
                                : `-${formatCurrency(Math.abs(budgetDiff), cand.currency || cand.product.currency)} OVER BUDGET`}
                            </span>
                          </div>
                        </div>

                        {/* Attributes: Condition & Merchant */}
                        <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                          <div className="p-2 rounded-lg bg-navy-950/50 border border-navy-800">
                            <span className="text-slate-500 block text-[9px] uppercase">
                              Condition
                            </span>
                            <span
                              className={cn(
                                'font-semibold',
                                cand.product.condition === 'new'
                                  ? 'text-slate-200'
                                  : 'text-amber-400'
                              )}
                            >
                              {cand.product.condition.toUpperCase()}
                            </span>
                          </div>

                          <div className="p-2 rounded-lg bg-navy-950/50 border border-navy-800">
                            <span className="text-slate-500 block text-[9px] uppercase">
                              Merchant
                            </span>
                            <span
                              className={cn(
                                'font-semibold truncate block',
                                cand.product.merchant_verified
                                  ? 'text-emerald-400'
                                  : 'text-rose-400'
                              )}
                              title={cand.product.merchant_name}
                            >
                              {cand.product.merchant_verified ? '✓ Verified' : '✗ Unverified'}
                            </span>
                          </div>
                        </div>

                        {/* Direct Retailer Link if available */}
                        {cand.product.purchase_url && (
                          <div className="flex items-center justify-between p-2 rounded-lg bg-navy-950/40 border border-navy-800 text-[11px] font-mono">
                            <span className="text-slate-400 truncate text-[10px]">
                              Domain: <strong className="text-slate-200">{cand.product.retailer || cand.product.merchant_name}</strong>
                            </span>
                            <a
                              href={cand.product.purchase_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300 transition-colors shrink-0 font-semibold"
                            >
                              <span>Direct Link</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                        )}

                        {/* Unverified Specifications Notice if NEEDS_VERIFICATION */}
                        {cand.status === 'NEEDS_VERIFICATION' && (
                          <div className="p-2.5 rounded-lg bg-amber-950/50 border border-amber-500/30 text-amber-300 text-xs font-mono space-y-1">
                            <div className="flex items-center gap-1.5 font-bold text-amber-400 text-[11px]">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              <span>Specifications Needing Verification:</span>
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-[10px] text-amber-300/90">
                              {(cand.unverified_reasons && cand.unverified_reasons.length > 0
                                ? cand.unverified_reasons
                                : ['Required hardware specifications (RAM/storage/processor) could not be confirmed in listing.']
                              ).map((reason, i) => (
                                <li key={i}>{reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Blocked Violations Notice if BLOCKED */}
                        {cand.status === 'BLOCKED' && !cand.approved && cand.policy_result.violations.length > 0 && (
                          <div className="p-2.5 rounded-lg bg-rose-950/50 border border-rose-500/30 text-rose-300 text-xs font-mono space-y-1">
                            <div className="flex items-center gap-1.5 font-bold text-rose-400 text-[11px]">
                              <ShieldAlert className="w-3.5 h-3.5" />
                              <span>Violations Detected:</span>
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-[10px] text-rose-300/90">
                              {cand.policy_result.violations.map((v, i) => (
                                <li key={i}>
                                  <strong className="text-rose-200">{v.rule_id}:</strong> {v.message}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Expandable 7 Invariant Policy Breakdown */}
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={() => toggleCardExpand(cand.product.product_id)}
                            className="w-full py-1 text-slate-400 hover:text-slate-200 text-[11px] font-mono flex items-center justify-between border-t border-navy-800/80 pt-2 transition-all"
                          >
                            <span>Inspect 7 Policy Checks</span>
                            {isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </button>

                          {isExpanded && (
                            <div className="space-y-1.5 pt-2 text-[10px] font-mono animate-in fade-in duration-200">
                              {cand.policy_result.checks.map((chk) => (
                                <div
                                  key={chk.rule_id}
                                  className={cn(
                                    'p-1.5 rounded flex items-center justify-between',
                                    chk.passed
                                      ? 'bg-emerald-950/30 text-emerald-300 border border-emerald-500/20'
                                      : 'bg-rose-950/40 text-rose-300 border border-rose-500/30'
                                  )}
                                >
                                  <div className="flex items-center gap-1.5">
                                    {chk.passed ? (
                                      <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                                    ) : (
                                      <Ban className="w-3 h-3 text-rose-400 shrink-0" />
                                    )}
                                    <span>
                                      <strong>{chk.rule_id}:</strong> {chk.rule_name}
                                    </span>
                                  </div>
                                  <span className="font-bold">
                                    {chk.passed ? 'PASSED' : 'FAILED'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Card Footer: Action Button */}
                    <div className="p-5 pt-0">
                      {cand.can_select ? (
                        <button
                          type="button"
                          onClick={() => handleSelectCandidate(cand)}
                          disabled={isStaging}
                          className="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-mono font-bold text-xs flex items-center justify-center gap-2 shadow-emerald-glow transition-all disabled:opacity-50"
                        >
                          {isStaging && selectedCandidate?.product.product_id === cand.product.product_id ? (
                            <>
                              <RefreshCw className="w-4 h-4 animate-spin" />
                              <span>Staging Proposal...</span>
                            </>
                          ) : (
                            <>
                              <ShieldCheck className="w-4 h-4" />
                              <span>Select Proposal for Review</span>
                            </>
                          )}
                        </button>
                      ) : cand.status === 'NEEDS_VERIFICATION' ? (
                        <button
                          type="button"
                          disabled
                          className="w-full py-2.5 px-4 rounded-xl bg-amber-950/60 border border-amber-500/40 text-amber-300 font-mono text-xs flex items-center justify-center gap-2 opacity-85 cursor-not-allowed"
                          title="Cannot stage proposal: Hardware specifications could not be verified against mandate."
                        >
                          <Lock className="w-3.5 h-3.5 text-amber-400" />
                          <span>Selection Blocked: Specs Unverified</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled
                          className="w-full py-2.5 px-4 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-300 font-mono text-xs flex items-center justify-center gap-2 opacity-80 cursor-not-allowed"
                          title={cand.selection_blocked_reason || 'Blocked by policy gate'}
                        >
                          <Lock className="w-3.5 h-3.5 text-rose-400" />
                          <span>Selection Blocked by Policy</span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Load More Candidates Button */}
          {searchResponse.has_more && filteredCandidates.length > 0 && (
            <div className="flex justify-center pt-4">
              <button
                type="button"
                onClick={handleLoadMore}
                disabled={isLoadingMore}
                className="px-6 py-3 rounded-xl bg-navy-800 hover:bg-navy-700 text-white font-mono font-bold text-xs flex items-center gap-2 border border-navy-700 shadow-card-glow hover:border-emerald-500/50 transition-all disabled:opacity-50"
              >
                {isLoadingMore ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                    <span>Loading Next Page...</span>
                  </>
                ) : (
                  <>
                    <Layers className="w-4 h-4 text-emerald-400" />
                    <span>Load More Candidate Products</span>
                  </>
                )}
              </button>
            </div>
          )}
        </>
      )}

      {/* Review & Staging Modal / Drawer */}
      {selectedCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-2xl rounded-2xl border border-emerald-500/50 bg-navy-900 p-6 shadow-card-glow space-y-6">
            <div className="flex items-center justify-between border-b border-navy-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white font-mono">
                    Candidate Proposal Staged for Human Review
                  </h3>
                  <span className="text-xs font-mono text-slate-400">
                    TrustGate Deterministic Policy Evaluation: APPROVED
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={closeReviewModal}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Invariant Alert Banner */}
            <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/40 text-xs font-mono text-amber-300 space-y-2">
              <div className="flex items-center gap-2 font-bold text-amber-200">
                <Lock className="w-4 h-4 text-amber-400 shrink-0" />
                <span>Zero Autonomous Payment Execution Invariant</span>
              </div>
              <p className="text-amber-300/90 leading-relaxed">
                Candidate approval by the TrustGate policy engine confirms rule compliance only.
                Selecting this proposal <strong className="text-white">DOES NOT</strong> authorize,
                stage, or execute a transaction. The AI has zero payment privilege. Explicit
                human authorization is mandatory before any checkout process can begin.
              </p>
              {selectedCandidate.product.is_demo_data && (
                <p className="text-rose-300 font-bold text-[11px] pt-1">
                  Notice: This is a demonstration fixture and is barred from proceeding to any real payment processing.
                </p>
              )}
            </div>

            {/* Selected Item Summary */}
            <div className="p-4 rounded-xl bg-navy-950 border border-navy-800 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Selected Product:</span>
                <span className="text-white font-bold">{selectedCandidate.product.name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Marketplace Source:</span>
                <span className="text-slate-300">
                  {selectedCandidate.product.data_source}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Selling Merchant:</span>
                <span className="text-emerald-400 font-semibold">
                  {selectedCandidate.product.merchant_name} (Verified)
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Proposed Total:</span>
                <span className="text-emerald-300 font-bold text-sm">
                  {formatCurrency(selectedCandidate.product.price, selectedCandidate.currency || selectedCandidate.product.currency)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Mandate Budget Cap:</span>
                <span className="text-slate-300">
                  {formatCurrency(activeMandate.max_amount, activeMandate.currency)}
                </span>
              </div>
              <div className="flex items-center justify-between border-t border-navy-800 pt-2">
                <span className="text-slate-400">Remaining Budget:</span>
                <span className="text-emerald-400 font-bold">
                  +{formatCurrency(selectedCandidate.budget_remaining, selectedCandidate.currency || selectedCandidate.product.currency)}
                </span>
              </div>
              {stagedProposal && (
                <div className="flex items-center justify-between border-t border-navy-800 pt-2 text-[11px]">
                  <span className="text-slate-500">Staged Proposal ID:</span>
                  <div className="flex items-center gap-2">
                    <code className="text-slate-300">{stagedProposal.staged_proposal_id}</code>
                    {onViewAuditTimeline && (
                      <button
                        type="button"
                        onClick={() => {
                          closeReviewModal();
                          onViewAuditTimeline(stagedProposal.staged_proposal_id);
                        }}
                        className="text-emerald-400 hover:text-emerald-300 text-[10px] underline ml-2"
                      >
                        Inspect Audit Chain
                      </button>
                    )}
                  </div>
                </div>
              )}
              {selectedCandidate.product.purchase_url && (
                <div className="flex items-center justify-between border-t border-navy-800 pt-2 text-[11px]">
                  <span className="text-slate-500">Retailer Purchase Link:</span>
                  <a
                    href={selectedCandidate.product.purchase_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 font-semibold"
                  >
                    <span>{selectedCandidate.product.retailer || 'View Listing'}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              )}
            </div>

            {stagedProposal && (
              <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-500/30 text-xs font-mono text-amber-300 space-y-1">
                <div className="flex items-center gap-2 font-bold">
                  <ShieldCheck className="w-4 h-4 text-amber-400" />
                  <span>Invariant TG-007: Human Authorization Gate Required</span>
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  This candidate has been staged in the persistent SQLite ledger as <strong className="text-white">{stagedProposal.staged_proposal_id}</strong>.
                  Autonomous payments are strictly blocked. Please proceed to the Human Approval Center to review budget caps, verify policy signatures, and authorize checkout.
                </p>
              </div>
            )}

            {stageError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-500/40 text-xs font-mono text-rose-300">
                {extractErrorMessage(stageError, 'Failed to stage candidate proposal.')}
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <span className="text-[11px] font-mono text-slate-500">
                {selectedCandidate.product.is_demo_data
                  ? 'Demonstration Mode • No Real Charges'
                  : 'Authentic Live Candidate • Staged for Operator Review'}
              </span>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={closeReviewModal}
                  className="px-4 py-2 rounded-xl bg-navy-800 hover:bg-navy-700 text-xs font-mono text-slate-300 transition-all"
                >
                  Close & Choose Another
                </button>
                {onNavigateToApprovals ? (
                  <button
                    type="button"
                    onClick={() => {
                      closeReviewModal();
                      onNavigateToApprovals();
                    }}
                    disabled={isStaging || !stagedProposal}
                    className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-navy-950 font-mono font-bold text-xs flex items-center gap-2 shadow-emerald-glow transition-all"
                  >
                    <UserCheck className="w-4 h-4" />
                    <span>Proceed to Human Approval Center</span>
                  </button>
                ) : (
                  <div
                    data-testid="missing-nav-guard"
                    className="px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center gap-2"
                  >
                    <Lock className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>Approval Center navigation required. Direct checkout is disabled.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
