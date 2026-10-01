import express, { Request, Response } from 'express';
import { createServer as createViteServer } from 'vite';
import { exec, spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { promisify } from 'util';

const execAsync = promisify(exec);

const app = express();
const PORT = 3000;

app.use(express.json());

// Helper to run python MCP tool queries
async function runPythonTool(toolName: string, args: Record<string, any>, repoRoot = '.'): Promise<any> {
  const pythonScript = `
import json, sys
from pathlib import Path
from sane_nav.mcp.tools import McpToolService

repo = Path(${JSON.stringify(repoRoot)}).resolve()
service = McpToolService(repo)
args = json.loads(${JSON.stringify(JSON.stringify(args))})

tool = ${JSON.stringify(toolName)}
if tool == "status":
    res = service.index_status()
elif tool == "search":
    res = service.search_semantic(**args)
elif tool == "context":
    res = service.get_context(**args)
elif tool == "skeleton":
    res = service.get_skeleton(**args)
elif tool == "symbol":
    res = service.get_symbol_code(**args)
elif tool == "usages":
    res = service.find_usages(**args)
elif tool == "read_lines":
    res = service.read_lines(**args)
elif tool == "tree":
    res = service.get_file_tree(**args)
else:
    res = {"error": f"Unknown tool: {tool}"}

print(json.dumps(res))
`;

  try {
    const { stdout, stderr } = await execAsync(`python3 -c '${pythonScript.replace(/'/g, "'\\''")}'`, {
      cwd: '/app/applet',
      env: { ...process.env, PYTHONPATH: '/app/applet/src' },
      maxBuffer: 10 * 1024 * 1024,
    });
    return JSON.parse(stdout.trim());
  } catch (err: any) {
    return {
      error: err.message,
      stderr: err.stderr,
    };
  }
}

// API: Status
app.get('/api/sane/status', async (req: Request, res: Response) => {
  const repo = (req.query.repo as string) || '.';
  const status = await runPythonTool('status', {}, repo);
  res.json(status);
});

// API: Search
app.post('/api/sane/search', async (req: Request, res: Response) => {
  const { query, limit = 8, path_prefix, kinds, repo = '.' } = req.body;
  const result = await runPythonTool('search', { query, limit, path_prefix, kinds }, repo);
  res.json(result);
});

// API: Context
app.post('/api/sane/context', async (req: Request, res: Response) => {
  const { feature, path_prefix, max_chars = 10000, repo = '.' } = req.body;
  const result = await runPythonTool('context', { feature, path_prefix, max_chars }, repo);
  res.json(result);
});

// API: Skeleton
app.post('/api/sane/skeleton', async (req: Request, res: Response) => {
  const { file_path, max_chars = 12000, repo = '.' } = req.body;
  const result = await runPythonTool('skeleton', { file_path, max_chars }, repo);
  res.json(result);
});

// API: Symbol code
app.post('/api/sane/symbol', async (req: Request, res: Response) => {
  const { symbol, context_lines = 0, repo = '.' } = req.body;
  const result = await runPythonTool('symbol', { symbol, context_lines }, repo);
  res.json(result);
});

// API: Usages
app.post('/api/sane/usages', async (req: Request, res: Response) => {
  const { symbol, limit = 10, include_probable = true, repo = '.' } = req.body;
  const result = await runPythonTool('usages', { symbol, limit, include_probable }, repo);
  res.json(result);
});

// API: Read lines
app.post('/api/sane/read_lines', async (req: Request, res: Response) => {
  const { file_path, start, end, repo = '.' } = req.body;
  const result = await runPythonTool('read_lines', { file_path, start, end }, repo);
  res.json(result);
});

// API: File tree
app.get('/api/sane/tree', async (req: Request, res: Response) => {
  const repo = (req.query.repo as string) || '.';
  const dir_path = (req.query.dir as string) || '.';
  const result = await runPythonTool('tree', { dir_path }, repo);
  res.json(result);
});

// API: CLI execution
app.post('/api/sane/cli', async (req: Request, res: Response) => {
  const { command, repo = '.' } = req.body;
  const startTime = Date.now();

  try {
    const fullCmd = `sane ${command} --repo ${repo}`;
    const { stdout, stderr } = await execAsync(fullCmd, {
      cwd: '/app/applet',
      env: { ...process.env, PYTHONPATH: '/app/applet/src' },
      timeout: 15000,
    });
    res.json({
      stdout,
      stderr,
      exitCode: 0,
      durationMs: Date.now() - startTime,
    });
  } catch (err: any) {
    res.json({
      stdout: err.stdout || '',
      stderr: err.stderr || err.message,
      exitCode: err.code || 1,
      durationMs: Date.now() - startTime,
    });
  }
});

// API: Token Economics Benchmark
app.post('/api/sane/benchmark', async (req: Request, res: Response) => {
  const { query = 'PaymentService.capture', repo = 'tests/fixtures' } = req.body;
  const startTime = Date.now();

  // 1. Simulate Naive Agent:
  // Step 1: grep -r 'capture' across repo -> reads all files where match occurs
  // Step 2: reads entire payment_service.py (54 lines) + CheckoutService.kt (24 lines) + AuthService.java (32 lines)
  const naiveFiles = ['python/payment_service.py', 'kotlin/CheckoutService.kt', 'java/AuthService.java'];
  let naiveContentLength = 0;
  for (const f of naiveFiles) {
    const p = path.join('/app/applet', repo, f);
    if (fs.existsSync(p)) {
      naiveContentLength += fs.readFileSync(p, 'utf-8').length;
    }
  }
  // grep output overhead
  naiveContentLength += 800;
  const naiveTokens = Math.round(naiveContentLength / 4);

  // 2. S.A.N.E. Progressive Disclosure:
  // Step 1: search_semantic("PaymentService.capture") -> ~400 chars
  // Step 2: get_symbol_code("PaymentService.capture") -> ~250 chars
  // Step 3: find_usages("capture") -> ~300 chars
  const saneSearch = await runPythonTool('search', { query, limit: 3 }, repo);
  const saneSymbol = await runPythonTool('symbol', { symbol: query }, repo);
  const saneUsages = await runPythonTool('usages', { symbol: 'capture', limit: 3 }, repo);

  const saneChars =
    JSON.stringify(saneSearch).length +
    JSON.stringify(saneSymbol).length +
    JSON.stringify(saneUsages).length;
  const saneTokens = Math.round(saneChars / 4);

  const savedTokens = Math.max(0, naiveTokens - saneTokens);
  const percentSaved = Math.round((savedTokens / naiveTokens) * 100);

  res.json({
    benchmarkTimeMs: Date.now() - startTime,
    naive: {
      toolCalls: 4,
      totalChars: naiveContentLength,
      estimatedTokens: naiveTokens,
      description: 'Grep repository + 3 full file reads',
    },
    sane: {
      toolCalls: 3,
      totalChars: saneChars,
      estimatedTokens: saneTokens,
      description: 'search_semantic → get_symbol_code → find_usages',
    },
    savings: {
      tokensSaved: savedTokens,
      percentReduction: percentSaved,
    },
    mcpResults: {
      search: saneSearch,
      symbol: saneSymbol,
      usages: saneUsages,
    },
  });
});

// API: Documentation Catalog
app.get('/api/sane/docs', (req: Request, res: Response) => {
  const docFiles = [
    { title: 'System Architecture', path: 'docs/ARCHITECTURE.md' },
    { title: 'Progressive Disclosure & Token Economics', path: 'docs/PROGRESSIVE_DISCLOSURE.md' },
    { title: 'MCP Protocol Specification', path: 'docs/MCP_SPECIFICATION.md' },
    { title: 'Symbol Resolution & Graph', path: 'docs/RESOLVER_AND_GRAPH.md' },
    { title: 'Language Adapters Guide', path: 'docs/LANGUAGE_ADAPTERS.md' },
    { title: 'CLI Manual & Configuration', path: 'docs/CLI_REFERENCE.md' },
    { title: 'Benchmarking & Quality SLOs', path: 'docs/BENCHMARKS.md' },
    { title: 'AI Agent Guidelines', path: 'AGENTS.md' },
    { title: 'README Overview', path: 'README.md' },
  ];

  const docs = docFiles.map((d) => {
    const full = path.join('/app/applet', d.path);
    const content = fs.existsSync(full) ? fs.readFileSync(full, 'utf-8') : '';
    return {
      title: d.title,
      path: d.path,
      content,
    };
  });

  res.json({ docs });
});

// API: Source tree for visual code explorer
app.get('/api/sane/source_catalog', (req: Request, res: Response) => {
  const basePath = '/app/applet';
  const targetDirs = ['src/sane_nav', 'tests'];
  const rootFiles = ['pyproject.toml', 'README.md', 'CHANGELOG.md', 'LICENSE'];

  const catalog: Array<{ path: string; language: string; content: string }> = [];

  function scan(dir: string) {
    const full = path.join(basePath, dir);
    if (!fs.existsSync(full)) return;
    const entries = fs.readdirSync(full, { withFileTypes: true });
    for (const e of entries) {
      const rel = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!e.name.startsWith('.') && e.name !== '__pycache__') {
          scan(rel);
        }
      } else if (e.isFile()) {
        if (rel.endsWith('.py') || rel.endsWith('.sql') || rel.endsWith('.toml') || rel.endsWith('.md')) {
          const content = fs.readFileSync(path.join(basePath, rel), 'utf-8');
          let lang = 'python';
          if (rel.endsWith('.sql')) lang = 'sql';
          if (rel.endsWith('.toml')) lang = 'toml';
          if (rel.endsWith('.md')) lang = 'markdown';
          catalog.push({ path: rel, language: lang, content });
        }
      }
    }
  }

  for (const d of targetDirs) scan(d);
  for (const f of rootFiles) {
    const full = path.join(basePath, f);
    if (fs.existsSync(full)) {
      const content = fs.readFileSync(full, 'utf-8');
      catalog.push({ path: f, language: f.endsWith('.md') ? 'markdown' : 'toml', content });
    }
  }

  res.json({ files: catalog });
});

async function startServer() {
  const isProd = process.env.NODE_ENV === 'production';

  if (!isProd) {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`S.A.N.E. Studio Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer();
