/**
 * 知识库本地服务
 * 用法：node server.js [知识库目录] [端口]
 * 默认：node server.js ./notes 3000
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const crudApi = require('./crud-api');

// ── 配置 ──────────────────────────────────────────
const NOTES_DIR = path.resolve(process.argv[2] || './notes');
const PORT = parseInt(process.argv[3] || '3000', 10);
const PUBLIC_DIR = path.join(__dirname, 'public');

// ── 工具函数 ──────────────────────────────────────

function mime(ext) {
  return {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript',
    '.css':  'text/css',
    '.json': 'application/json',
    '.ico':  'image/x-icon',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.svg':  'image/svg+xml',
    '.webp': 'image/webp',
    '.bmp':  'image/bmp',
    '.tiff': 'image/tiff',
  }[ext] || 'text/plain';
}

function json(res, data, status = 200) {
  const body = JSON.stringify(data);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  res.end(body);
}

function notFound(res, msg = 'Not Found') {
  json(res, { error: msg }, 404);
}

// ── 扫描目录 ──────────────────────────────────────

function scanDir(dirPath, relBase = '') {
  const result = [];
  let entries;
  try {
    entries = fs.readdirSync(dirPath, { withFileTypes: true });
  } catch { return result; }

  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const absPath = path.join(dirPath, entry.name);
    const relPath = relBase ? `${relBase}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      result.push(...scanDir(absPath, relPath));
    } else if (/\.md(own)?$/i.test(entry.name)) {
      const stat = fs.statSync(absPath);
      result.push({
        id: Buffer.from(relPath).toString('base64url'),
        name: entry.name.replace(/\.md(own)?$/i, ''),
        filename: entry.name,
        path: relPath,
        dir: relBase || '/',
        size: stat.size,
        mtime: stat.mtimeMs,
      });
    }
  }
  return result;
}

// ── 全文搜索 ──────────────────────────────────────

function searchFiles(files, query) {
  if (!query) return [];
  const q = query.toLowerCase();
  const results = [];

  for (const f of files) {
    const absPath = path.join(NOTES_DIR, f.path);
    try {
      const content = fs.readFileSync(absPath, 'utf8');
      const lc = content.toLowerCase();
      const idx = lc.indexOf(q);
      if (idx === -1 && !f.name.toLowerCase().includes(q)) continue;

      // 提取上下文片段
      let snippet = '';
      if (idx !== -1) {
        const start = Math.max(0, idx - 60);
        const end = Math.min(content.length, idx + 120);
        snippet = (start > 0 ? '…' : '') + content.slice(start, end).replace(/\n+/g, ' ') + (end < content.length ? '…' : '');
      }

      results.push({ ...f, snippet, matchInTitle: f.name.toLowerCase().includes(q) });
    } catch { /* skip unreadable */ }
  }

  // 标题匹配优先
  results.sort((a, b) => (b.matchInTitle ? 1 : 0) - (a.matchInTitle ? 1 : 0));
  return results.slice(0, 50);
}

// ── HTTP 路由 ─────────────────────────────────────

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = decodeURIComponent(parsed.pathname);

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    });
    return res.end();
  }

  // API: 文件树
  if (pathname === '/api/tree') {
    const files = scanDir(NOTES_DIR);
    return json(res, { files, root: path.basename(NOTES_DIR) });
  }

  // API: 文件内容操作 (GET, PUT, DELETE)
  if (pathname === '/api/file') {
    if (req.method === 'GET') {
      const id = parsed.query.id;
      if (!id) return notFound(res, 'Missing id');
      let relPath;
      try { relPath = Buffer.from(id, 'base64url').toString('utf8'); } catch { return notFound(res); }
      const absPath = path.resolve(path.join(NOTES_DIR, relPath));
      if (!absPath.startsWith(NOTES_DIR)) return notFound(res, 'Access denied');
      try {
        const content = fs.readFileSync(absPath, 'utf8');
        return json(res, { content, path: relPath });
      } catch { return notFound(res, 'File not found'); }
    }
    else if (req.method === 'PUT') {
      crudApi.handleUpdateFile(req, res, NOTES_DIR);
      return;
    }
    else if (req.method === 'DELETE') {
      crudApi.handleDeleteFile(req, res, NOTES_DIR);
      return;
    }
    else {
      res.writeHead(405, { 'Allow': 'GET, PUT, DELETE' });
      res.end();
      return;
    }
  }

  // API: 创建文件 (POST)
  if (pathname === '/api/files' && req.method === 'POST') {
    crudApi.handleCreateFile(req, res, NOTES_DIR);
    return;
  }

  // API: 创建目录 (POST)
  if (pathname === '/api/directories' && req.method === 'POST') {
    crudApi.handleCreateDirectory(req, res, NOTES_DIR);
    return;
  }

  // API: 全文搜索
  if (pathname === '/api/search') {
    const q = parsed.query.q || '';
    const files = scanDir(NOTES_DIR);
    return json(res, { results: searchFiles(files, q), query: q });
  }

  // API: 图片资源
  if (pathname === '/api/image') {
    const encodedPath = parsed.query.path;
    if (!encodedPath) return notFound(res, 'Missing path parameter');

    let imagePath;
    try {
      imagePath = Buffer.from(encodedPath, 'base64url').toString('utf8');
    } catch {
      return notFound(res, 'Invalid path encoding');
    }

    // 解析路径：如果是相对路径，相对于 NOTES_DIR 解析；否则使用绝对路径
    let absPath;
    if (path.isAbsolute(imagePath) || /^[a-zA-Z]:[\\/]/.test(imagePath)) {
      // Windows 绝对路径（如 D:\images\photo.png）或 Unix 绝对路径
      absPath = path.resolve(imagePath);
    } else {
      // 相对路径，相对于 NOTES_DIR
      absPath = path.resolve(path.join(NOTES_DIR, imagePath));
    }

    // 安全检查：扩展名必须是图片格式
    const ext = path.extname(absPath).toLowerCase();
    const contentType = mime(ext);
    if (contentType === 'text/plain') {
      return notFound(res, 'Unsupported image format');
    }

    // 检查文件是否存在
    try {
      fs.accessSync(absPath, fs.constants.R_OK);
    } catch {
      return notFound(res, 'Image not found');
    }

    // 读取并返回图片
    try {
      const data = fs.readFileSync(absPath);
      res.writeHead(200, {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=86400',
        'Access-Control-Allow-Origin': '*'
      });
      res.end(data);
    } catch {
      return notFound(res, 'Cannot read image');
    }
    return;
  }

  // 静态文件
  let filePath = path.join(PUBLIC_DIR, pathname === '/' ? 'index.html' : pathname);
  filePath = path.resolve(filePath);
  if (!filePath.startsWith(PUBLIC_DIR)) { res.writeHead(403); return res.end(); }

  try {
    const content = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': mime(path.extname(filePath)) });
    res.end(content);
  } catch {
    // SPA fallback
    try {
      const html = fs.readFileSync(path.join(PUBLIC_DIR, 'index.html'));
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch { res.writeHead(404); res.end('Not found'); }
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('  📚 知识库服务已启动');
  console.log(`  ➜  http://localhost:${PORT}`);
  console.log(`  📁 知识库目录：${NOTES_DIR}`);
  console.log('');
  console.log('  按 Ctrl+C 停止服务');
  console.log('');

  if (!fs.existsSync(NOTES_DIR)) {
    console.warn(`  ⚠️  目录不存在，已自动创建：${NOTES_DIR}`);
    fs.mkdirSync(NOTES_DIR, { recursive: true });
    // 创建示例文件
    fs.mkdirSync(path.join(NOTES_DIR, '示例笔记'), { recursive: true });
    fs.writeFileSync(path.join(NOTES_DIR, '示例笔记', '快速开始.md'), DEMO_MD);
  }
});

const DEMO_MD = `# 欢迎使用知识库

这是一个示例笔记，把你的 Markdown 文件放到 \`notes/\` 目录即可。

## 支持的功能

- ✅ Markdown 格式渲染
- ✅ 代码语法高亮
- ✅ 全文搜索
- ✅ 按目录分组浏览

## 代码示例

\`\`\`python
def hello():
    print("Hello, Knowledge Base!")
\`\`\`

## 目录结构建议

\`\`\`
notes/
├── 技术笔记/
│   ├── Python基础.md
│   └── Git命令.md
├── 读书摘要/
│   └── 深度工作.md
└── 日记/
    └── 2025-01.md
\`\`\`
`;
