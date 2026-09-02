'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { RefreshCw, Star, Zap, Brain, Eye, DollarSign, Search, AlertTriangle, Clock, Layers } from 'lucide-react';
import { api } from '@/lib/api';
import type { OpenRouterModel } from '@/lib/types';
import type { AISettings } from '@/lib/settings';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function OpenRouterModelSelector({ settings, onChange }: Props) {
  const [catalog, setCatalog] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string>('ALL');

  const freeOnly = settings.openRouterFreeOnly ?? true;
  const allowPaid = settings.openRouterAllowPaid ?? false;
  const pricingFilter = settings.openRouterPricingFilter ?? 'FREE';
  const selectedModel = settings.openRouterSelectedModel ?? 'auto';

  const fetchCatalog = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const params: any = {};
      // free_only controls server filtering
      const effectiveFreeOnly = !allowPaid;
      params.free_only = effectiveFreeOnly;
      if (!effectiveFreeOnly && pricingFilter) {
        params.pricing = pricingFilter;
      }
      if (refresh) params.refresh = true;
      const res = await api.getAIModels(params);
      setCatalog(res.data);
    } catch (e: any) {
      setError(e.message || 'Failed to load models');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalog(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowPaid, pricingFilter]);

  const handleRefresh = async () => {
    await fetchCatalog(true);
  };

  const handleToggleAllowPaid = (enabled: boolean) => {
    onChange({
      openRouterAllowPaid: enabled,
      openRouterFreeOnly: !enabled,
      openRouterPricingFilter: enabled ? 'ALL' : 'FREE',
    });
  };

  const handlePricingChange = (val: 'FREE' | 'PAID' | 'ALL') => {
    onChange({ openRouterPricingFilter: val });
  };

  const filteredModels: OpenRouterModel[] = useMemo(() => {
    if (!catalog?.models) return [];
    let list = catalog.models as OpenRouterModel[];
    // Apply spec §33 filter if active
    if (activeFilter !== 'ALL') {
      const f = activeFilter;
      list = list.filter((m: any) => {
        if (f === 'FREE') return m.is_free;
        if (f === 'REASONING') return m.category === 'Reasoning';
        if (f === 'FINANCE') return m.category === 'Finance';
        if (f === 'FAST') return m.category === 'Fast';
        if (f === 'RESEARCH') return m.category === 'Research';
        if (f === 'VISION') return m.supports_vision || m.category === 'Vision';
        if (f === 'CODING') return m.category === 'Coding';
        if (f === 'TOOLS') return m.supports_tools === true;
        if (f === 'STRUCTURED') return (m as any).supports_structured_outputs !== false;
        return true;
      });
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (m) =>
          m.id.toLowerCase().includes(q) ||
          m.name.toLowerCase().includes(q) ||
          m.category.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q)
      );
    }
    return list;
  }, [catalog, search, activeFilter]);

  const grouped = useMemo(() => {
    const groups: Record<string, OpenRouterModel[]> = {};
    for (const m of filteredModels) {
      const cat = m.category || 'Unknown';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(m);
    }
    // Order categories: Finance -> Reasoning -> Coding -> Vision -> Fast -> General -> Research -> Unknown
    const order = ['Finance', 'Reasoning', 'Coding', 'Vision', 'Fast', 'General', 'Research', 'Unknown'];
    const sorted: [string, OpenRouterModel[]][] = [];
    for (const cat of order) {
      if (groups[cat]) sorted.push([cat, groups[cat]]);
    }
    // add any remaining
    for (const [cat, arr] of Object.entries(groups)) {
      if (!order.includes(cat)) sorted.push([cat, arr]);
    }
    return sorted;
  }, [filteredModels]);

  const selectedModelObj = catalog?.models?.find((m: OpenRouterModel) => m.id === selectedModel);
  const defaultModel = catalog?.default_model;

  const updatedTime = catalog?.updated_at ? new Date(catalog.updated_at).toLocaleTimeString() : '—';
  const usingCached = catalog?.using_cached;

  const getCategoryIcon = (cat: string) => {
    switch (cat) {
      case 'Finance':
        return <Star className="w-3 h-3 text-amber-500" />;
      case 'Reasoning':
        return <Brain className="w-3 h-3 text-purple-500" />;
      case 'Fast':
        return <Zap className="w-3 h-3 text-yellow-500" />;
      case 'Vision':
        return <Eye className="w-3 h-3 text-blue-500" />;
      case 'Coding':
        return <Layers className="w-3 h-3 text-emerald-500" />;
      default:
        return <Layers className="w-3 h-3 text-muted-foreground" />;
    }
  };

  return (
    <div className="space-y-4 bg-card border border-border rounded-xl p-5 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-primary" />
            OpenRouter Dynamic Model Catalog
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 font-mono">DYNAMIC</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Automatically retrieved from OpenRouter&apos;s Models API. Free detection via pricing (prompt=0 & completion=0). Never hard-coded.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary border border-border rounded-lg text-xs font-medium hover:bg-secondary/80 cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Models
        </button>
      </div>

      {/* Top Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* AI Provider */}
        <div className="space-y-1">
          <label className="text-xs font-semibold text-foreground">AI Provider</label>
          <div className="w-full bg-primary/10 border border-primary/20 rounded-lg px-3 py-2 text-xs font-mono text-foreground">
            OpenRouter
          </div>
          <span className="text-[11px] text-muted-foreground">Key from Settings (sent per-request, no hardcode). Optional env fallback.</span>
        </div>

        {/* Model Mode */}
        <div className="space-y-1">
          <label className="text-xs font-semibold text-foreground">Model Mode</label>
          <div className={`w-full border rounded-lg px-3 py-2 text-xs font-semibold ${freeOnly ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700' : 'bg-amber-500/10 border-amber-500/20 text-amber-700'}`}>
            {freeOnly ? 'FREE ONLY' : `PRICING: ${pricingFilter}`}
          </div>
          <span className="text-[11px] text-muted-foreground">
            {freeOnly ? 'Paid models are hard-blocked (server validates pricing).' : 'Paid filter active — credits may be used.'}
          </span>
        </div>

        {/* Allow Paid Toggle */}
        <div className="space-y-1">
          <label className="text-xs font-semibold text-foreground flex items-center gap-1">
            Allow Paid Models
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${allowPaid ? 'bg-amber-500 text-white' : 'bg-secondary text-muted-foreground border'}`}>
              {allowPaid ? 'ON' : 'OFF'}
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer bg-secondary/50 border border-border rounded-lg px-3 py-2">
            <input
              type="checkbox"
              checked={allowPaid}
              onChange={(e) => handleToggleAllowPaid(e.target.checked)}
              className="accent-primary"
            />
            <span className="text-xs text-foreground">{allowPaid ? 'Enabled — pricing filter applies' : 'OFF — free-only protection active'}</span>
          </label>
          {allowPaid && (
            <div className="flex gap-1 mt-1">
              {(['FREE', 'PAID', 'ALL'] as const).map((pf) => (
                <button
                  key={pf}
                  type="button"
                  onClick={() => handlePricingChange(pf)}
                  className={`flex-1 py-1 px-2 rounded text-[11px] font-mono border cursor-pointer ${pricingFilter === pf ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:bg-secondary'}`}
                >
                  {pf}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Model Selector Dropdown */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">Model</label>
          <div className="flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
            <Clock className="w-3 h-3" />
            Models updated: {updatedTime}
            {usingCached && <span className="text-amber-600 ml-1">(Using cached model list)</span>}
          </div>
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setShowDropdown(!showDropdown)}
            className="w-full flex items-center justify-between bg-secondary/50 border border-border rounded-lg px-3 py-2.5 text-xs text-foreground cursor-pointer hover:bg-secondary/80"
          >
            <span className="flex items-center gap-2 truncate">
              {selectedModel === 'auto' ? (
                <>
                  <Star className="w-3.5 h-3.5 text-amber-500" />
                  <span className="font-semibold">Auto — Best Free for Trading</span>
                  {defaultModel && <span className="text-muted-foreground">({defaultModel.name})</span>}
                </>
              ) : selectedModelObj ? (
                <>
                  {getCategoryIcon(selectedModelObj.category)}
                  <span className="font-medium">{selectedModelObj.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-emerald-500/15 text-emerald-700 rounded font-mono">FREE</span>
                  {selectedModelObj.recommended_for_trading && <span className="text-[10px]">⭐</span>}
                </>
              ) : (
                <span className="truncate">{selectedModel}</span>
              )}
            </span>
            <span className="text-muted-foreground">▼</span>
          </button>

          {showDropdown && (
            <div className="absolute z-50 mt-1 w-full bg-card border border-border rounded-xl shadow-sm max-h-[520px] overflow-hidden flex flex-col">
              {/* Search + §33 Filters */}
              <div className="p-2 border-b border-border space-y-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search models..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full bg-secondary/50 border border-border rounded-lg pl-8 pr-3 py-2 text-xs focus:outline-hidden focus:border-primary"
                    autoFocus
                  />
                </div>
                {/* §33 Model Search / Filtering — only show supported */}
                {catalog?.models && (
                  <div className="flex flex-wrap gap-1">
                    {(['ALL', 'FREE', 'REASONING', 'FINANCE', 'FAST', 'RESEARCH', 'VISION', 'CODING', 'TOOLS', 'STRUCTURED'] as const).map((f) => {
                      // Compute count for filter
                      const count = (catalog.models as any[]).filter((m: any) => {
                        if (f === 'ALL') return true;
                        if (f === 'FREE') return m.is_free;
                        if (f === 'REASONING') return m.category === 'Reasoning';
                        if (f === 'FINANCE') return m.category === 'Finance';
                        if (f === 'FAST') return m.category === 'Fast';
                        if (f === 'RESEARCH') return m.category === 'Research';
                        if (f === 'VISION') return m.supports_vision || m.category === 'Vision';
                        if (f === 'CODING') return m.category === 'Coding';
                        if (f === 'TOOLS') return m.supports_tools;
                        if (f === 'STRUCTURED') return (m as any).supports_structured_outputs !== false;
                        return false;
                      }).length;
                      if (f !== 'ALL' && count === 0) return null;
                      const active = activeFilter === f;
                      return (
                        <button
                          key={f}
                          type="button"
                          onClick={() => setActiveFilter(f)}
                          className={`px-2 py-1 rounded-full text-[10px] font-mono border cursor-pointer ${active ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary border-border hover:bg-secondary/80'}`}
                        >
                          {f === 'STRUCTURED' ? 'Structured Outputs' : f === 'TOOLS' ? 'Tools' : f} {f !== 'ALL' ? `(${count})` : `(${catalog.models.length})`}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{catalog ? `${catalog.free_count} free / ${catalog.total_count} total` : 'Loading...'}{activeFilter !== 'ALL' ? ` • ${activeFilter} filtered: ${filteredModels.length}` : ''}</span>
                  {defaultModel && <span>Default: {defaultModel.name}</span>}
                </div>
              </div>

              <div className="overflow-y-auto flex-1">
                {/* Auto option always on top */}
                <button
                  type="button"
                  onClick={() => {
                    onChange({ openRouterSelectedModel: 'auto', openRouterModel: 'auto' });
                    setShowDropdown(false);
                  }}
                  className={`w-full text-left px-3 py-2.5 hover:bg-secondary/50 border-b border-border flex items-center justify-between cursor-pointer ${selectedModel === 'auto' ? 'bg-primary/10' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <Star className="w-4 h-4 text-amber-500" />
                    <div>
                      <div className="text-xs font-semibold text-foreground">Auto — Best Free for Trading</div>
                      <div className="text-[11px] text-muted-foreground">
                        {defaultModel ? `${defaultModel.name} • ${defaultModel.category} • rank ${defaultModel.trading_rank}` : 'Highest-ranked free finance/reasoning model'}
                      </div>
                    </div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 bg-primary text-primary-foreground rounded font-mono">AUTO</span>
                </button>

                {grouped.length === 0 && (
                  <div className="p-4 text-xs text-muted-foreground text-center">No models match search. Try clearing filter.</div>
                )}

                {grouped.map(([cat, models]) => (
                  <div key={cat} className="border-b border-border/50 last:border-0">
                    <div className="px-3 py-1.5 bg-secondary/30 flex items-center gap-1.5 text-[11px] font-semibold text-muted-foreground sticky top-0">
                      {getCategoryIcon(cat)}
                      {cat === 'Finance' ? '⭐ Finance' : cat === 'Reasoning' ? '🧠 Reasoning' : cat === 'Fast' ? '⚡ Fast' : cat === 'Vision' ? '👁 Vision' : cat}
                      <span className="ml-auto text-[10px] font-mono">{models.length}</span>
                    </div>
                    {models.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          onChange({ openRouterSelectedModel: m.id, openRouterModel: m.id });
                          setShowDropdown(false);
                        }}
                        className={`w-full text-left px-3 py-2 hover:bg-secondary/50 flex flex-col gap-0.5 cursor-pointer ${selectedModel === m.id ? 'bg-primary/10 border-l-2 border-primary' : 'border-l-2 border-transparent'}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-foreground truncate">{m.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-emerald-500/15 text-emerald-700 rounded font-mono border border-emerald-500/20">FREE</span>
                          {m.recommended_for_trading && <span className="text-[10px]">⭐ Recommended</span>}
                          {m.category === 'Fast' && <span className="text-[10px]">⚡</span>}
                          {m.category === 'Reasoning' && <span className="text-[10px]">🧠</span>}
                        </div>
                        <div className="text-[11px] text-muted-foreground truncate flex items-center gap-2">
                          <span className="font-mono truncate">{m.id}</span>
                          <span className="shrink-0">ctx {m.context_length.toLocaleString()}</span>
                          {m.supports_tools && <span className="text-emerald-600">tools</span>}
                        </div>
                        {m.description && <div className="text-[11px] text-muted-foreground line-clamp-1">{m.description.slice(0, 120)}</div>}
                      </button>
                    ))}
                  </div>
                ))}
              </div>

              <div className="p-2 border-t border-border bg-secondary/20 text-[11px] text-muted-foreground">
                <div className="flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  Free detection: prompt=0 & completion=0 • Never hard-coded • Updates every 5-15 min
                </div>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="text-[11px] p-2 rounded bg-destructive/10 border border-destructive/20 text-destructive flex flex-col gap-1">
            <div className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{error} — {usingCached ? 'Using cached model list' : 'Retrying will use cached list if available.'}</div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={handleRefresh} className="px-2 py-1 bg-card border border-border rounded text-[11px] font-mono hover:bg-secondary cursor-pointer">Retry Refresh</button>
              <span className="text-muted-foreground">FREE-only guard: paid models hard-blocked (prompt=0 & completion=0 required). Try Auto — Best Free.</span>
            </div>
          </div>
        )}

        {loading && <div className="text-[11px] text-muted-foreground">Loading models from OpenRouter...</div>}

        {/* Status bar */}
        {catalog && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-muted-foreground">
            <span>Provider: OpenRouter</span>
            <span>•</span>
            <span className={freeOnly ? 'text-emerald-600 font-semibold' : ''}>{freeOnly ? 'FREE ONLY' : pricingFilter}</span>
            <span>•</span>
            <span>{catalog.models.length} shown</span>
            <span>•</span>
            <span className={usingCached ? 'text-amber-600' : 'text-emerald-600'}>{usingCached ? 'Using cached model list' : 'Live catalog'}</span>
          </div>
        )}
      </div>

      {/* Selected info */}
      {selectedModel !== 'auto' && selectedModelObj && (
        <div className="bg-secondary/30 border border-border/60 rounded-lg p-3 text-xs space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground">{selectedModelObj.name}</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-700 border border-emerald-500/20">💰 Free</span>
            {selectedModelObj.recommended_for_trading && <span className="text-[10px] bg-amber-500/15 text-amber-700 px-2 py-0.5 rounded border border-amber-500/20">⭐ Recommended for Trading</span>}
            {selectedModelObj.supports_tools && <span className="text-[10px]">🧠 tools</span>}
            {selectedModelObj.category === 'Fast' && <span className="text-[10px]">⚡ Fast</span>}
          </div>
          <div className="text-[11px] text-muted-foreground font-mono break-all">{selectedModelObj.id}</div>
          <div className="text-[11px] text-muted-foreground">Category: {selectedModelObj.category} • Context: {selectedModelObj.context_length.toLocaleString()} • Rank: {selectedModelObj.trading_rank}</div>
        </div>
      )}
      {selectedModel === 'auto' && defaultModel && (
        <div className="bg-primary/10 border border-primary/20 rounded-lg p-3 text-xs">
          <div className="font-semibold text-foreground flex items-center gap-1">
            <Star className="w-3 h-3 text-amber-500" />
            Auto will use: {defaultModel.name}
          </div>
          <div className="text-[11px] text-muted-foreground">{defaultModel.id} • {defaultModel.category} • rank {defaultModel.trading_rank} • Probabilistic Outlook (not guaranteed)</div>
        </div>
      )}
    </div>
  );
}
