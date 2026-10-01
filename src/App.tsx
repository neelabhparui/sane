import React, { useState, useEffect } from 'react';
import {
  Compass,
  Terminal,
  Zap,
  Layers,
  BookOpen,
  Code2,
  Search,
  CheckCircle2,
  FileCode2,
  Activity,
  Copy,
  Check,
  ChevronRight,
  TrendingDown,
  ArrowRight,
  Cpu,
  ShieldCheck,
  Database,
  Play,
  RotateCw,
  FolderTree,
  ExternalLink,
  Sliders,
  Sparkles,
} from 'lucide-react';

interface IndexStats {
  state?: string;
  files?: number;
  symbols?: number;
  docs?: number;
  occurrences?: number;
  resolved_edges?: number;
  languages?: Record<string, number>;
  semantic_mode?: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'flow' | 'tools' | 'graph' | 'cli' | 'docs' | 'setup' | 'code'>('flow');
  const [selectedRepo, setSelectedRepo] = useState<'tests/fixtures' | '.'>('tests/fixtures');
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Docs state
  const [docsList, setDocsList] = useState<Array<{ title: string; path: string; content: string }>>([]);
  const [selectedDocPath, setSelectedDocPath] = useState<string>('docs/ARCHITECTURE.md');
  const [loadingDocs, setLoadingDocs] = useState<boolean>(false);

  // Progressive flow state
  const [flowPreset, setFlowPreset] = useState<string>('payment');
  const [flowStep, setFlowStep] = useState<number>(1);
  const [flowLoading, setFlowLoading] = useState<boolean>(false);
  const [flowData, setFlowData] = useState<{
    query: string;
    searchRes?: any;
    skeletonRes?: any;
    symbolRes?: any;
    usagesRes?: any;
    contextRes?: any;
    benchmark?: any;
  }>({
    query: 'PaymentService.capture',
  });

  // MCP tool state
  const [activeTool, setActiveTool] = useState<string>('search_semantic');
  const [toolInputs, setToolInputs] = useState<Record<string, any>>({
    search_semantic: { query: 'capture', limit: 8 },
    get_context: { feature: 'Retry Policy', max_chars: 5000 },
    get_skeleton: { file_path: 'python/payment_service.py' },
    get_symbol_code: { symbol: 'PaymentService.capture', context_lines: 1 },
    find_usages: { symbol: 'capture', limit: 5 },
    read_lines: { file_path: 'python/payment_service.py', start: 1, end: 15 },
    get_file_tree: { dir_path: '.' },
    index_status: {},
  });
  const [toolOutput, setToolOutput] = useState<any>(null);
  const [toolLoading, setToolLoading] = useState(false);

  // CLI state
  const [cliInput, setCliInput] = useState('doctor');
  const [cliOutput, setCliOutput] = useState<{ stdout: string; stderr: string; exitCode: number; durationMs: number } | null>(null);
  const [cliLoading, setCliLoading] = useState(false);

  // Source tree state
  const [sourceFiles, setSourceFiles] = useState<Array<{ path: string; language: string; content: string }>>([]);
  const [selectedSourcePath, setSelectedSourcePath] = useState<string>('src/sane_nav/cli.py');
  const [loadingSources, setLoadingSources] = useState(false);

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Fetch status
  const fetchStatus = async () => {
    setLoadingStats(true);
    try {
      const res = await fetch(`/api/sane/status?repo=${selectedRepo}`);
      const data = await res.json();
      setStats(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [selectedRepo]);

  // Load source files when switching to code tab
  useEffect(() => {
    if (activeTab === 'code' && sourceFiles.length === 0) {
      setLoadingSources(true);
      fetch('/api/sane/source_catalog')
        .then((r) => r.json())
        .then((data) => {
          setSourceFiles(data.files || []);
        })
        .finally(() => setLoadingSources(false));
    }
  }, [activeTab]);

  // Load docs when switching to docs tab
  useEffect(() => {
    if (activeTab === 'docs' && docsList.length === 0) {
      setLoadingDocs(true);
      fetch('/api/sane/docs')
        .then((r) => r.json())
        .then((data) => {
          setDocsList(data.docs || []);
        })
        .finally(() => setLoadingDocs(false));
    }
  }, [activeTab]);

  // Run Flow preset
  const runFlowSequence = async (presetKey: string) => {
    setFlowPreset(presetKey);
    setFlowLoading(true);
    setFlowStep(1);

    let q = 'PaymentService.capture';
    let file = 'python/payment_service.py';
    let sym = 'PaymentService.capture';
    let usageSym = 'capture';
    let feat = 'Retry Policy';

    if (presetKey === 'auth') {
      q = 'rotateRefreshToken';
      file = 'java/AuthService.java';
      sym = 'AuthService.rotateRefreshToken';
      usageSym = 'rotateRefreshToken';
      feat = 'Refresh tokens';
    } else if (presetKey === 'checkout') {
      q = 'submitOrder';
      file = 'kotlin/CheckoutService.kt';
      sym = 'CheckoutService.submitOrder';
      usageSym = 'submitOrder';
      feat = 'Payments and Billing';
    }

    try {
      // 1. Search
      const sRes = await fetch('/api/sane/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, repo: selectedRepo }),
      }).then((r) => r.json());

      // 2. Skeleton
      const skelRes = await fetch('/api/sane/skeleton', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: file, repo: selectedRepo }),
      }).then((r) => r.json());

      // 3. Symbol code
      const symRes = await fetch('/api/sane/symbol', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, repo: selectedRepo }),
      }).then((r) => r.json());

      // 4. Usages
      const usgRes = await fetch('/api/sane/usages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: usageSym, repo: selectedRepo }),
      }).then((r) => r.json());

      // 5. Context
      const ctxRes = await fetch('/api/sane/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature: feat, repo: selectedRepo }),
      }).then((r) => r.json());

      // Benchmark
      const benchRes = await fetch('/api/sane/benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: sym, repo: selectedRepo }),
      }).then((r) => r.json());

      setFlowData({
        query: q,
        searchRes: sRes,
        skeletonRes: skelRes,
        symbolRes: symRes,
        usagesRes: usgRes,
        contextRes: ctxRes,
        benchmark: benchRes,
      });
      setFlowStep(5);
    } catch (e) {
      console.error(e);
    } finally {
      setFlowLoading(false);
    }
  };

  useEffect(() => {
    runFlowSequence('payment');
  }, [selectedRepo]);

  // Execute MCP Tool
  const handleExecuteTool = async () => {
    setToolLoading(true);
    setToolOutput(null);
    try {
      let endpoint = `/api/sane/${activeTool}`;
      let body: any = { ...toolInputs[activeTool], repo: selectedRepo };

      if (activeTool === 'search_semantic') endpoint = '/api/sane/search';
      if (activeTool === 'get_context') endpoint = '/api/sane/context';
      if (activeTool === 'get_skeleton') endpoint = '/api/sane/skeleton';
      if (activeTool === 'get_symbol_code') endpoint = '/api/sane/symbol';
      if (activeTool === 'find_usages') endpoint = '/api/sane/usages';
      if (activeTool === 'read_lines') endpoint = '/api/sane/read_lines';
      if (activeTool === 'get_file_tree') endpoint = `/api/sane/tree?repo=${selectedRepo}`;
      if (activeTool === 'index_status') endpoint = `/api/sane/status?repo=${selectedRepo}`;

      let res;
      if (activeTool === 'get_file_tree' || activeTool === 'index_status') {
        res = await fetch(endpoint).then((r) => r.json());
      } else {
        res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }).then((r) => r.json());
      }
      setToolOutput(res);
    } catch (e: any) {
      setToolOutput({ error: e.message });
    } finally {
      setToolLoading(false);
    }
  };

  // Run CLI
  const handleRunCli = async (cmdToRun?: string) => {
    const cmd = cmdToRun || cliInput;
    setCliLoading(true);
    try {
      const res = await fetch('/api/sane/cli', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd, repo: selectedRepo }),
      }).then((r) => r.json());
      setCliOutput(res);
    } catch (e: any) {
      setCliOutput({ stdout: '', stderr: e.message, exitCode: 1, durationMs: 0 });
    } finally {
      setCliLoading(false);
    }
  };

  const selectedFileObj = sourceFiles.find((f) => f.path === selectedSourcePath) || sourceFiles[0];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50 px-6 py-3.5">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          {/* Logo & Meta */}
          <div className="flex items-center space-x-3.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-600 to-pink-500 p-0.5 shadow-lg shadow-indigo-500/20">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <Compass className="w-5 h-5 text-indigo-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold tracking-wider text-lg bg-gradient-to-r from-indigo-300 via-purple-200 to-pink-300 bg-clip-text text-transparent">
                  S.A.N.E.
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  v0.1.0
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  MCP Ready
                </span>
              </div>
              <p className="text-xs text-slate-400 font-medium hidden sm:block">
                Semantic Agent Navigation Engine • Progressive Code Disclosure
              </p>
            </div>
          </div>

          {/* Repo switcher & Status indicators */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs">
              <button
                onClick={() => setSelectedRepo('tests/fixtures')}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  selectedRepo === 'tests/fixtures'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Sample Multi-Lang Repo
              </button>
              <button
                onClick={() => setSelectedRepo('.')}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  selectedRepo === '.'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                sane-nav Engine Repo
              </button>
            </div>

            <div className="hidden lg:flex items-center space-x-2 border-l border-slate-800 pl-3 text-xs text-slate-400">
              <span className="flex items-center gap-1.5 bg-slate-900 border border-slate-800/80 px-2.5 py-1.5 rounded-md">
                <Database className="w-3.5 h-3.5 text-indigo-400" />
                <span className="font-mono text-slate-300 font-semibold">{stats?.files ?? 0}</span> files
              </span>
              <span className="flex items-center gap-1.5 bg-slate-900 border border-slate-800/80 px-2.5 py-1.5 rounded-md">
                <FileCode2 className="w-3.5 h-3.5 text-purple-400" />
                <span className="font-mono text-slate-300 font-semibold">{stats?.symbols ?? 0}</span> symbols
              </span>
              <span className="flex items-center gap-1.5 bg-slate-900 border border-slate-800/80 px-2.5 py-1.5 rounded-md">
                <Activity className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-mono text-slate-300 font-semibold">{stats?.resolved_edges ?? 0}</span> edges
              </span>
            </div>

            <button
              onClick={() => handleRunCli('doctor')}
              title="Run System Diagnostics"
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 rounded-lg flex items-center gap-1.5 transition"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Doctor
            </button>
          </div>
        </div>
      </header>

      {/* Navigation Bar */}
      <nav className="border-b border-slate-800/80 bg-slate-900/40 px-6">
        <div className="max-w-7xl mx-auto flex space-x-1 sm:space-x-4 overflow-x-auto py-2">
          {[
            { id: 'flow', label: 'Progressive Disclosure & Economics', icon: Zap },
            { id: 'tools', label: 'MCP Tools Live Console', icon: Sliders },
            { id: 'graph', label: 'Doc-to-Code Graph', icon: Layers },
            { id: 'cli', label: 'Interactive CLI Terminal', icon: Terminal },
            { id: 'docs', label: 'Architecture & Documentation', icon: BookOpen },
            { id: 'setup', label: 'Agent Setup (Claude / Cursor / VS Code)', icon: Code2 },
            { id: 'code', label: 'Python Source Inspector', icon: FileCode2 },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                  active
                    ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? 'text-indigo-400' : 'text-slate-500'}`} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {/* ================= TAB 1: PROGRESSIVE DISCLOSURE & TOKEN ECONOMICS ================= */}
        {activeTab === 'flow' && (
          <div className="space-y-6">
            {/* Hero Banner with Insight */}
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-950/60 via-purple-950/40 to-slate-900 border border-indigo-500/20 p-6 sm:p-8">
              <div className="max-w-3xl space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                  <Sparkles className="w-3.5 h-3.5" />
                  The Human-IDE Analogy for AI Coding Agents
                </div>
                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
                  Stop Flooding Context. Navigate Like a Senior Engineer.
                </h1>
                <p className="text-sm text-slate-300 leading-relaxed">
                  When a human developer works on a task, they don’t read all 900 lines of 5 files. They locate the symbol,
                  inspect its signature and docstring, read only the target method body, and trace exact callers.
                  S.A.N.E. brings this exact progressive escalation hierarchy to Claude Code, Cursor, and Copilot.
                </p>
              </div>

              {/* Live Savings Stat Callout */}
              {flowData.benchmark && (
                <div className="mt-6 pt-6 border-t border-indigo-500/20 grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                    <div className="text-xs text-slate-400 flex items-center gap-1.5">
                      <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
                      Token Reduction
                    </div>
                    <div className="text-2xl font-black text-emerald-400 mt-1">
                      -{flowData.benchmark.savings.percentReduction}%
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {flowData.benchmark.savings.tokensSaved} tokens preserved
                    </div>
                  </div>

                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                    <div className="text-xs text-slate-400">S.A.N.E. Consumption</div>
                    <div className="text-2xl font-black text-indigo-300 mt-1">
                      {flowData.benchmark.sane.estimatedTokens}{' '}
                      <span className="text-xs font-normal text-slate-400">tokens</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">3 bounded MCP calls</div>
                  </div>

                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                    <div className="text-xs text-slate-400">Naive Agent Consumption</div>
                    <div className="text-2xl font-black text-rose-400 mt-1">
                      {flowData.benchmark.naive.estimatedTokens}{' '}
                      <span className="text-xs font-normal text-slate-400">tokens</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">Grep + 3 raw file reads</div>
                  </div>

                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                    <div className="text-xs text-slate-400">Resolution Speed</div>
                    <div className="text-2xl font-black text-purple-300 mt-1">
                      {flowData.benchmark.benchmarkTimeMs}{' '}
                      <span className="text-xs font-normal text-slate-400">ms</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">Local SQLite WAL + FTS5</div>
                  </div>
                </div>
              )}
            </div>

            {/* Presets Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/50 border border-slate-800 p-3 rounded-xl">
              <div className="flex items-center space-x-2 text-xs font-medium text-slate-400">
                <span>Select Scenario:</span>
                <button
                  onClick={() => runFlowSequence('payment')}
                  className={`px-3 py-1.5 rounded-lg border transition ${
                    flowPreset === 'payment'
                      ? 'bg-indigo-600 text-white border-indigo-500'
                      : 'bg-slate-800 border-slate-700 hover:text-white'
                  }`}
                >
                  Payment Capture & Retries (Python & Kotlin)
                </button>
                <button
                  onClick={() => runFlowSequence('auth')}
                  className={`px-3 py-1.5 rounded-lg border transition ${
                    flowPreset === 'auth'
                      ? 'bg-indigo-600 text-white border-indigo-500'
                      : 'bg-slate-800 border-slate-700 hover:text-white'
                  }`}
                >
                  Auth Refresh Tokens (Java & Docs)
                </button>
                <button
                  onClick={() => runFlowSequence('checkout')}
                  className={`px-3 py-1.5 rounded-lg border transition ${
                    flowPreset === 'checkout'
                      ? 'bg-indigo-600 text-white border-indigo-500'
                      : 'bg-slate-800 border-slate-700 hover:text-white'
                  }`}
                >
                  Checkout Coordination (Kotlin)
                </button>
              </div>

              <button
                onClick={() => runFlowSequence(flowPreset)}
                disabled={flowLoading}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-200 rounded-lg flex items-center gap-1.5 transition"
              >
                <RotateCw className={`w-3.5 h-3.5 ${flowLoading ? 'animate-spin' : ''}`} />
                Re-run Simulation
              </button>
            </div>

            {/* Step-by-Step Progressive Disclosure Stepper */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
              {[
                { step: 1, title: '1. Concept Search', desc: 'search_semantic()', icon: Search },
                { step: 2, title: '2. Feature Context', desc: 'get_context()', icon: BookOpen },
                { step: 3, title: '3. Redacted Skeleton', desc: 'get_skeleton()', icon: FileCode2 },
                { step: 4, title: '4. Symbol Extraction', desc: 'get_symbol_code()', icon: Code2 },
                { step: 5, title: '5. Call Usages', desc: 'find_usages()', icon: ArrowRight },
              ].map((s) => {
                const Icon = s.icon;
                const isSelected = flowStep === s.step;
                return (
                  <button
                    key={s.step}
                    onClick={() => setFlowStep(s.step)}
                    className={`text-left p-3.5 rounded-xl border transition flex flex-col justify-between ${
                      isSelected
                        ? 'bg-indigo-600/10 border-indigo-500 text-white shadow-md shadow-indigo-500/10'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between w-full mb-2">
                      <span className="font-mono text-[11px] font-bold text-indigo-400">STEP {s.step}</span>
                      <Icon className={`w-4 h-4 ${isSelected ? 'text-indigo-400' : 'text-slate-500'}`} />
                    </div>
                    <div className="font-semibold text-xs text-slate-200">{s.title}</div>
                    <div className="font-mono text-[11px] text-slate-500 mt-0.5">{s.desc}</div>
                  </button>
                );
              })}
            </div>

            {/* Step Viewer Panel */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
              {/* Step Header */}
              <div className="bg-slate-950 px-6 py-3.5 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center space-x-2.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>
                  <span className="text-xs font-mono font-bold text-slate-300">
                    {flowStep === 1 && `search_semantic(query="${flowData.query}")`}
                    {flowStep === 2 && `get_context(feature="...")`}
                    {flowStep === 3 && `get_skeleton(file_path="...")`}
                    {flowStep === 4 && `get_symbol_code(symbol="${flowData.query}")`}
                    {flowStep === 5 && `find_usages(symbol="capture")`}
                  </span>
                </div>
                <div className="text-xs text-slate-400">
                  Step {flowStep} of 5
                </div>
              </div>

              {/* Step Content */}
              <div className="p-6">
                {flowStep === 1 && (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400">
                      The agent begins by searching for candidates. S.A.N.E. combines exact names, identifier tokenization,
                      and SQLite FTS5 rank scores:
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {(flowData.searchRes?.results || []).map((r: any, idx: number) => (
                        <div
                          key={idx}
                          className="bg-slate-950 border border-slate-800 rounded-lg p-3.5 space-y-1.5 hover:border-slate-700 transition"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-indigo-300">{r.name || r.title}</span>
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-400">
                              {r.kind}
                            </span>
                          </div>
                          {r.signature && (
                            <div className="font-mono text-xs text-slate-300 truncate bg-slate-900/60 px-2 py-1 rounded">
                              {r.signature}
                            </div>
                          )}
                          <div className="flex items-center justify-between text-[11px] text-slate-500">
                            <span>
                              {r.file}:{r.lines?.[0]}
                            </span>
                            <span className="font-mono text-indigo-400/80">score: {r.match?.score}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {flowStep === 2 && (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400">
                      `get_context()` extracts relevant documentation sections and automatically bridges them to code symbols:
                    </p>
                    <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-slate-300 whitespace-pre-wrap max-h-96 overflow-y-auto leading-relaxed">
                      {flowData.contextRes?.content || 'Loading feature context...'}
                    </pre>
                  </div>
                )}

                {flowStep === 3 && (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400">
                      `get_skeleton()` reveals the structural contract of a file without flooding tokens with 500 lines of body logic:
                    </p>
                    <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-slate-300 whitespace-pre-wrap max-h-96 overflow-y-auto leading-relaxed">
                      {flowData.skeletonRes?.skeleton || 'Loading skeleton...'}
                    </pre>
                  </div>
                )}

                {flowStep === 4 && (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400">
                      `get_symbol_code()` returns the exact implementation lines with 100% precision and line numbers:
                    </p>
                    <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-emerald-300 whitespace-pre-wrap max-h-96 overflow-y-auto leading-relaxed">
                      {flowData.symbolRes?.code || 'Loading symbol code...'}
                    </pre>
                  </div>
                )}

                {flowStep === 5 && (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400">
                      `find_usages()` traces call sites across Kotlin, Java, and Python with AST-aware line context and resolution confidence:
                    </p>
                    <div className="space-y-3">
                      {(flowData.usagesRes?.exact_usages || [])
                        .concat(flowData.usagesRes?.probable_usages || [])
                        .map((u: any, idx: number) => (
                          <div key={idx} className="bg-slate-950 border border-slate-800 rounded-lg p-3.5 space-y-2">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-mono text-indigo-300 font-semibold">
                                {u.file}:{u.line}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                                {u.resolution} (conf: {u.confidence})
                              </span>
                            </div>
                            <pre className="bg-slate-900/60 p-2.5 rounded font-mono text-xs text-slate-300 whitespace-pre-wrap">
                              {u.snippet}
                            </pre>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Step Navigation Controls */}
              <div className="bg-slate-950 px-6 py-3 border-t border-slate-800 flex items-center justify-between">
                <button
                  disabled={flowStep <= 1}
                  onClick={() => setFlowStep((s) => Math.max(1, s - 1))}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition"
                >
                  Previous Step
                </button>
                <div className="flex items-center space-x-1.5">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <button
                      key={i}
                      onClick={() => setFlowStep(i)}
                      className={`w-2.5 h-2.5 rounded-full transition ${
                        flowStep === i ? 'bg-indigo-500 scale-125' : 'bg-slate-700 hover:bg-slate-600'
                      }`}
                    />
                  ))}
                </div>
                <button
                  disabled={flowStep >= 5}
                  onClick={() => setFlowStep((s) => Math.min(5, s + 1))}
                  className="px-3.5 py-1.5 rounded-lg border border-indigo-600 bg-indigo-600 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40 transition"
                >
                  Next Step
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 2: LIVE MCP TOOLS CONSOLE ================= */}
        {activeTab === 'tools' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Tool selector */}
            <div className="lg:col-span-4 space-y-3">
              <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider mb-2">Available MCP Tools</h2>
              {[
                { name: 'search_semantic', desc: 'Hybrid lexical & conceptual symbol search' },
                { name: 'get_context', desc: 'Deterministic feature doc-to-code stitching' },
                { name: 'get_skeleton', desc: 'Byte-redacted structural file view' },
                { name: 'get_symbol_code', desc: 'Exact symbol declaration and body' },
                { name: 'find_usages', desc: 'Cross-reference call sites with confidence' },
                { name: 'read_lines', desc: 'Bounded line reader for configs' },
                { name: 'get_file_tree', desc: 'Bounded repository directory structure' },
                { name: 'index_status', desc: 'Health, symbol counts & engine state' },
              ].map((t) => (
                <button
                  key={t.name}
                  onClick={() => {
                    setActiveTool(t.name);
                    setToolOutput(null);
                  }}
                  className={`w-full text-left p-3 rounded-xl border transition ${
                    activeTool === t.name
                      ? 'bg-indigo-600/15 border-indigo-500 text-white shadow-sm'
                      : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                  }`}
                >
                  <div className="font-mono text-xs font-bold text-indigo-400">{t.name}()</div>
                  <div className="text-[11px] text-slate-500 mt-1">{t.desc}</div>
                </button>
              ))}
            </div>

            {/* Tool Tester & Execution */}
            <div className="lg:col-span-8 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div>
                    <span className="font-mono text-sm font-bold text-indigo-400">{activeTool}()</span>
                    <span className="text-xs text-slate-400 ml-2">MCP Tool Execution</span>
                  </div>
                  <button
                    onClick={handleExecuteTool}
                    disabled={toolLoading}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                  >
                    <Play className={`w-3.5 h-3.5 ${toolLoading ? 'animate-spin' : ''}`} />
                    {toolLoading ? 'Executing...' : 'Call Tool'}
                  </button>
                </div>

                {/* Form fields based on tool */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  {activeTool === 'search_semantic' && (
                    <>
                      <div className="space-y-1">
                        <label className="text-slate-400 font-medium">Query String</label>
                        <input
                          type="text"
                          value={toolInputs.search_semantic.query}
                          onChange={(e) =>
                            setToolInputs({
                              ...toolInputs,
                              search_semantic: { ...toolInputs.search_semantic, query: e.target.value },
                            })
                          }
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-slate-400 font-medium">Limit (Max 20)</label>
                        <input
                          type="number"
                          value={toolInputs.search_semantic.limit}
                          onChange={(e) =>
                            setToolInputs({
                              ...toolInputs,
                              search_semantic: { ...toolInputs.search_semantic, limit: parseInt(e.target.value) || 8 },
                            })
                          }
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                        />
                      </div>
                    </>
                  )}

                  {activeTool === 'get_context' && (
                    <div className="col-span-2 space-y-1">
                      <label className="text-slate-400 font-medium">Feature / Architecture Topic</label>
                      <input
                        type="text"
                        value={toolInputs.get_context.feature}
                        onChange={(e) =>
                          setToolInputs({
                            ...toolInputs,
                            get_context: { ...toolInputs.get_context, feature: e.target.value },
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                      />
                    </div>
                  )}

                  {activeTool === 'get_skeleton' && (
                    <div className="col-span-2 space-y-1">
                      <label className="text-slate-400 font-medium">File Path</label>
                      <input
                        type="text"
                        value={toolInputs.get_skeleton.file_path}
                        onChange={(e) =>
                          setToolInputs({
                            ...toolInputs,
                            get_skeleton: { ...toolInputs.get_skeleton, file_path: e.target.value },
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                      />
                    </div>
                  )}

                  {activeTool === 'get_symbol_code' && (
                    <div className="col-span-2 space-y-1">
                      <label className="text-slate-400 font-medium">Symbol Identifier or Name</label>
                      <input
                        type="text"
                        value={toolInputs.get_symbol_code.symbol}
                        onChange={(e) =>
                          setToolInputs({
                            ...toolInputs,
                            get_symbol_code: { ...toolInputs.get_symbol_code, symbol: e.target.value },
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                      />
                    </div>
                  )}

                  {activeTool === 'find_usages' && (
                    <div className="col-span-2 space-y-1">
                      <label className="text-slate-400 font-medium">Target Symbol Name</label>
                      <input
                        type="text"
                        value={toolInputs.find_usages.symbol}
                        onChange={(e) =>
                          setToolInputs({
                            ...toolInputs,
                            find_usages: { ...toolInputs.find_usages, symbol: e.target.value },
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono text-xs focus:border-indigo-500 outline-none"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Output Viewer */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <div className="bg-slate-950 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between text-xs">
                  <span className="font-mono text-slate-400">Response Output</span>
                  {toolOutput && (
                    <button
                      onClick={() => handleCopy(JSON.stringify(toolOutput, null, 2), 'toolOutput')}
                      className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[11px]"
                    >
                      {copiedKey === 'toolOutput' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      Copy JSON
                    </button>
                  )}
                </div>
                <div className="p-4">
                  {toolOutput ? (
                    <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-slate-300 max-h-[500px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                      {JSON.stringify(toolOutput, null, 2)}
                    </pre>
                  ) : (
                    <div className="text-center py-12 text-slate-500 text-xs">
                      Click "Call Tool" above to execute this MCP operation and inspect real-time results.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 3: DOC-TO-CODE GRAPH ================= */}
        {activeTab === 'graph' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-base font-bold text-white mb-1">Documentation-to-Code Semantic Bridges</h2>
              <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
                Unlike traditional RAG that slices arbitrary chunks, S.A.N.E. maps markdown document headings to concrete code symbols.
                When prose mentions a class like <code className="text-indigo-300">PaymentRetryCoordinator</code>, S.A.N.E. links the documentation
                directly to the implementation and its call graph.
              </p>

              <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Node 1: Docs */}
                <div className="bg-slate-950 border border-indigo-500/30 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-400 flex items-center gap-1.5">
                      <BookOpen className="w-4 h-4" />
                      Markdown Section
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">docs/architecture.md</span>
                  </div>
                  <div className="font-semibold text-sm text-slate-200">Retry Policy</div>
                  <div className="text-xs text-slate-400 bg-slate-900 p-2.5 rounded border border-slate-800 italic">
                    "Payment retry behaviour is coordinated by PaymentRetryCoordinator. Transient network errors..."
                  </div>
                  <div className="text-[11px] font-mono text-indigo-300 flex items-center gap-1">
                    <ArrowRight className="w-3.5 h-3.5" />
                    Mentions: PaymentRetryCoordinator
                  </div>
                </div>

                {/* Node 2: Target Symbol */}
                <div className="bg-slate-950 border border-purple-500/30 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                      <Code2 className="w-4 h-4" />
                      Core Symbol (Python)
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">src/payment_service.py</span>
                  </div>
                  <div className="font-semibold text-sm text-slate-200">PaymentRetryCoordinator</div>
                  <div className="font-mono text-xs text-slate-300 bg-slate-900 p-2.5 rounded border border-slate-800 space-y-1">
                    <div>def should_retry(attempt, error_code)</div>
                    <div>async def schedule_retry(token_id)</div>
                  </div>
                  <div className="text-[11px] font-mono text-purple-300 flex items-center gap-1">
                    <ArrowRight className="w-3.5 h-3.5" />
                    Called by: PaymentService.capture
                  </div>
                </div>

                {/* Node 3: Cross-Language Caller */}
                <div className="bg-slate-950 border border-emerald-500/30 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                      <Layers className="w-4 h-4" />
                      Caller Site (Kotlin)
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">CheckoutService.kt:17</span>
                  </div>
                  <div className="font-semibold text-sm text-slate-200">CheckoutService.submitOrder()</div>
                  <div className="font-mono text-xs text-slate-300 bg-slate-900 p-2.5 rounded border border-slate-800">
                    <div>&gt; paymentProcessor.capture(token, total)</div>
                  </div>
                  <div className="text-[11px] font-mono text-emerald-300 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Resolution: class-scoped (0.95 conf)
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 4: INTERACTIVE CLI TERMINAL ================= */}
        {activeTab === 'cli' && (
          <div className="space-y-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-indigo-400" />
                    S.A.N.E. Terminal Console
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Execute real <code className="text-indigo-300 font-mono">sane</code> commands directly against the engine.
                  </p>
                </div>

                {/* Quick command buttons */}
                <div className="flex flex-wrap gap-2">
                  {['doctor', 'status', 'search "PaymentService"', 'usages "capture"', 'setup claude'].map((cmd) => (
                    <button
                      key={cmd}
                      onClick={() => {
                        setCliInput(cmd);
                        handleRunCli(cmd);
                      }}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-mono text-slate-300 rounded-md transition"
                    >
                      sane {cmd}
                    </button>
                  ))}
                </div>
              </div>

              {/* Input row */}
              <div className="flex items-center space-x-2">
                <span className="font-mono text-indigo-400 text-sm font-bold pl-2">$ sane</span>
                <input
                  type="text"
                  value={cliInput}
                  onChange={(e) => setCliInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleRunCli()}
                  placeholder="doctor, status, search <query>, skeleton <file>, symbol <name>, usages <name>"
                  className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:border-indigo-500 outline-none"
                />
                <button
                  onClick={() => handleRunCli()}
                  disabled={cliLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50"
                >
                  {cliLoading ? 'Running...' : 'Run'}
                </button>
              </div>
            </div>

            {/* Terminal Window */}
            <div className="bg-black border border-slate-800 rounded-xl overflow-hidden font-mono text-xs shadow-2xl">
              <div className="bg-slate-950 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-slate-400">
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-full bg-rose-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-amber-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-emerald-500/80"></div>
                  <span className="text-[11px] text-slate-500 ml-2">bash - sane CLI</span>
                </div>
                {cliOutput && (
                  <span className="text-[11px] text-slate-400">
                    Exit: {cliOutput.exitCode} • {cliOutput.durationMs}ms
                  </span>
                )}
              </div>
              <div className="p-5 max-h-[500px] overflow-y-auto space-y-2 text-slate-300 whitespace-pre-wrap leading-relaxed">
                {cliOutput ? (
                  <>
                    <div className="text-slate-500">$ sane {cliInput} --repo {selectedRepo}</div>
                    {cliOutput.stdout && <div className="text-emerald-400">{cliOutput.stdout}</div>}
                    {cliOutput.stderr && <div className="text-amber-400">{cliOutput.stderr}</div>}
                  </>
                ) : (
                  <div className="text-slate-600">
                    S.A.N.E. CLI ready. Type a command or click a quick shortcut above to run.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB: ARCHITECTURE & DOCUMENTATION VIEWER ================= */}
        {activeTab === 'docs' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Doc Index */}
            <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-xl p-4 max-h-[650px] overflow-y-auto space-y-1 text-xs">
              <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px] mb-3 flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                Documentation Guides
              </h3>
              {loadingDocs ? (
                <div className="text-slate-500 p-4 text-center">Loading documentation...</div>
              ) : (
                docsList.map((d) => (
                  <button
                    key={d.path}
                    onClick={() => setSelectedDocPath(d.path)}
                    className={`w-full text-left px-3.5 py-2.5 rounded-lg font-medium text-xs transition flex items-center justify-between ${
                      selectedDocPath === d.path
                        ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    <span className="truncate">{d.title}</span>
                    <span className="text-[10px] font-mono text-slate-500 ml-2">{d.path.split('/')[0]}</span>
                  </button>
                ))
              )}
            </div>

            {/* Markdown Reader */}
            <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col">
              <div className="bg-slate-950 px-5 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>
                  <span className="font-mono text-slate-200 font-bold">{selectedDocPath}</span>
                </div>
                {docsList.find((d) => d.path === selectedDocPath) && (
                  <button
                    onClick={() =>
                      handleCopy(docsList.find((d) => d.path === selectedDocPath)?.content || '', 'docContent')
                    }
                    className="text-slate-400 hover:text-slate-200 flex items-center gap-1.5 text-xs transition"
                  >
                    {copiedKey === 'docContent' ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                    Copy Markdown
                  </button>
                )}
              </div>
              <div className="p-6 flex-1 bg-slate-950/60 max-h-[650px] overflow-y-auto">
                <pre className="font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed select-text">
                  {docsList.find((d) => d.path === selectedDocPath)?.content || 'Select a document to read.'}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 5: AGENT SETUP & MCP CONFIGS ================= */}
        {activeTab === 'setup' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
              <div>
                <h2 className="text-lg font-bold text-white">Coding Agent Integrations</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Configure S.A.N.E. as a local stdio MCP server for your favorite agentic IDEs.
                </p>
              </div>

              {/* Claude Code */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="w-3 h-3 rounded-full bg-orange-500"></span>
                    <span className="font-bold text-sm text-white">Claude Code</span>
                  </div>
                  <button
                    onClick={() => handleCopy(`claude mcp add sane -- sane serve --repo .`, 'claude')}
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 rounded-md flex items-center gap-1.5 transition"
                  >
                    {copiedKey === 'claude' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy Command
                  </button>
                </div>
                <pre className="bg-slate-900 p-3 rounded font-mono text-xs text-slate-300">
                  claude mcp add sane -- sane serve --repo .
                </pre>
              </div>

              {/* Cursor */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                    <span className="font-bold text-sm text-white">Cursor (.cursor/mcp.json)</span>
                  </div>
                  <button
                    onClick={() =>
                      handleCopy(
                        JSON.stringify(
                          {
                            mcpServers: {
                              sane: {
                                command: 'sane',
                                args: ['serve', '--repo', '.'],
                              },
                            },
                          },
                          null,
                          2
                        ),
                        'cursor'
                      )
                    }
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 rounded-md flex items-center gap-1.5 transition"
                  >
                    {copiedKey === 'cursor' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy JSON
                  </button>
                </div>
                <pre className="bg-slate-900 p-3 rounded font-mono text-xs text-slate-300">
{`{
  "mcpServers": {
    "sane": {
      "command": "sane",
      "args": ["serve", "--repo", "."]
    }
  }
}`}
                </pre>
              </div>

              {/* Recommended Agent Rules */}
              <div className="bg-slate-950 border border-indigo-500/20 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm text-indigo-300">Recommended Agent Instructions (AGENTS.md)</span>
                  <button
                    onClick={() =>
                      handleCopy(
                        `## Code Navigation Instructions\nUse S.A.N.E. for exploring this codebase:\n1. search_semantic for a new concept or feature.\n2. get_context when feature-level documentation is needed.\n3. get_skeleton before reading an unfamiliar source file.\n4. get_symbol_code to view exact implementations.\n5. find_usages to trace call sites.\n6. read_lines only for non-code or configuration files.\n\nDo NOT read entire source files merely to discover their structure.`,
                        'agentRule'
                      )
                    }
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 rounded-md flex items-center gap-1.5 transition"
                  >
                    {copiedKey === 'agentRule' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy Prompt
                  </button>
                </div>
                <pre className="bg-slate-900 p-3 rounded font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
{`## Code Navigation Instructions
Use S.A.N.E. for exploring this codebase:
1. search_semantic for a new concept or feature.
2. get_context when feature-level documentation is needed.
3. get_skeleton before reading an unfamiliar source file.
4. get_symbol_code to view exact implementations.
5. find_usages to trace call sites.
6. read_lines only for non-code or configuration files.

Do NOT read entire source files merely to discover their structure.`}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 6: SOURCE CODE INSPECTOR ================= */}
        {activeTab === 'code' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* File List */}
            <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-xl p-4 max-h-[600px] overflow-y-auto space-y-1 text-xs">
              <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px] mb-3">Package Files</h3>
              {loadingSources ? (
                <div className="text-slate-500 p-4 text-center">Loading codebase...</div>
              ) : (
                sourceFiles.map((f) => (
                  <button
                    key={f.path}
                    onClick={() => setSelectedSourcePath(f.path)}
                    className={`w-full text-left px-3 py-2 rounded-lg font-mono text-xs transition flex items-center justify-between ${
                      selectedSourcePath === f.path
                        ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    <span className="truncate">{f.path}</span>
                    <span className="text-[10px] text-slate-500 uppercase">{f.language}</span>
                  </button>
                ))
              )}
            </div>

            {/* Code Viewer */}
            <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col">
              <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
                <span className="font-mono text-slate-200 font-bold">{selectedSourcePath}</span>
                {selectedFileObj && (
                  <button
                    onClick={() => handleCopy(selectedFileObj.content, 'sourceCode')}
                    className="text-slate-400 hover:text-slate-200 flex items-center gap-1.5 text-xs"
                  >
                    {copiedKey === 'sourceCode' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy Source
                  </button>
                )}
              </div>
              <div className="p-4 flex-1">
                <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-slate-300 max-h-[550px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {selectedFileObj?.content || 'Select a file to inspect.'}
                </pre>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/60 py-4 px-6 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4 text-xs text-slate-500">
          <div>
            S.A.N.E. (Semantic Agent Navigation Engine) • Open Source Under Apache-2.0
          </div>
          <div className="flex items-center space-x-4">
            <span>Python 3.10+</span>
            <span>SQLite WAL</span>
            <span>FTS5 Lexical Search</span>
            <span>Model Context Protocol 2024-11-05</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
