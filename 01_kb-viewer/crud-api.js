/**
 * CRUD API 处理模块
 * 提供文件创建、更新、删除和目录创建功能
 */

const fs = require('fs');
const path = require('path');

// ── 工具函数 ──────────────────────────────────────

/**
 * 发送JSON响应
 */
function json(res, data, status = 200) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
  });
  res.end(body);
}

/**
 * 发送错误响应
 */
function error(res, message, status = 400) {
  json(res, { error: message }, status);
}

/**
 * 安全检查：确保路径在notes目录内
 */
function isPathSafe(filePath, notesDir) {
  const resolved = path.resolve(filePath);
  const resolvedNotesDir = path.resolve(notesDir);
  // return resolved.startsWith(resolvedNotesDir);
  // 使用 path.sep 确保精确匹配目录边界
  return resolved === resolvedNotesDir ||
           resolved.startsWith(resolvedNotesDir + path.sep);
}

/**
 * 验证文件名
 */
function isValidFilename(filename) {
  // 不允许的字符和路径遍历
  if (!filename || filename.length === 0) return false;
  if (filename.includes('..')) return false;
  if (/[<>:"|?*]/.test(filename)) return false; // Windows不合法字符
  if (filename.startsWith('.')) return false; // 隐藏文件
  return true;
}

/**
 * 验证目录名
 */
function isValidDirname(dirname) {
  return isValidFilename(dirname);
}

// ── 文件操作处理函数 ──────────────────────────────

/**
 * 处理文件创建 (POST /api/files)
 */
async function handleCreateFile(req, res, notesDir) {
  try {
    // 读取请求体
    let body = '';
    for await (const chunk of req) {
      body += chunk;
    }

    const data = JSON.parse(body);
    const { path: filePath, content } = data;

    // 参数验证
    if (!filePath || !content) {
      return error(res, '缺少必要参数: path 或 content');
    }

    // 安全检查
    const fullPath = path.resolve(path.join(notesDir, filePath));
    if (!isPathSafe(fullPath, notesDir)) {
      return error(res, '路径不安全');
    }

    // 验证文件名
    const dir = path.dirname(fullPath);
    const filename = path.basename(fullPath);

    if (!isValidFilename(filename)) {
      return error(res, '文件名不合法');
    }

    // 确保目录存在
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch (err) {
      return error(res, `无法创建目录: ${err.message}`);
    }

    // 检查文件是否已存在
    if (fs.existsSync(fullPath)) {
      return error(res, '文件已存在', 409);
    }

    // 写入文件
    fs.writeFileSync(fullPath, content, 'utf8');

    // 获取文件状态
    const stat = fs.statSync(fullPath);
    const relativePath = path.relative(notesDir, fullPath);

    // 返回创建的文件信息
    json(res, {
      id: Buffer.from(relativePath).toString('base64url'),
      name: filename.replace(/\.md(own)?$/i, ''),
      filename: filename,
      path: relativePath.replace(/\\/g, '/'),
      dir: path.dirname(relativePath).replace(/\\/g, '/') || '/',
      size: stat.size,
      mtime: stat.mtimeMs,
      message: '文件创建成功'
    }, 201);

  } catch (err) {
    console.error('创建文件错误:', err);
    if (err instanceof SyntaxError) {
      return error(res, '无效的JSON数据');
    }
    return error(res, `服务器错误: ${err.message}`, 500);
  }
}

/**
 * 处理文件更新 (PUT /api/file)
 */
async function handleUpdateFile(req, res, notesDir) {
  try {
    // 读取请求体
    let body = '';
    for await (const chunk of req) {
      body += chunk;
    }

    const data = JSON.parse(body);
    const { id, content } = data;

    // 参数验证
    if (!id || content === undefined) {
      return error(res, '缺少必要参数: id 或 content');
    }

    // 解码文件路径
    let relPath;
    try {
      relPath = Buffer.from(id, 'base64url').toString('utf8');
    } catch (err) {
      return error(res, '无效的文件ID');
    }

    const fullPath = path.resolve(path.join(notesDir, relPath));

    // 安全检查
    if (!isPathSafe(fullPath, notesDir)) {
      return error(res, '路径不安全');
    }

    // 检查文件是否存在
    if (!fs.existsSync(fullPath)) {
      return error(res, '文件不存在', 404);
    }

    // 备份原文件内容（可选）
    const backupContent = fs.readFileSync(fullPath, 'utf8');

    // 写入新内容
    fs.writeFileSync(fullPath, content, 'utf8');

    // 获取更新后的文件状态
    const stat = fs.statSync(fullPath);
    const filename = path.basename(fullPath);

    // 返回更新后的文件信息
    json(res, {
      id: id,
      name: filename.replace(/\.md(own)?$/i, ''),
      filename: filename,
      path: relPath.replace(/\\/g, '/'),
      dir: path.dirname(relPath).replace(/\\/g, '/') || '/',
      size: stat.size,
      mtime: stat.mtimeMs,
      message: '文件更新成功'
    });

  } catch (err) {
    console.error('更新文件错误:', err);
    if (err instanceof SyntaxError) {
      return error(res, '无效的JSON数据');
    }
    return error(res, `服务器错误: ${err.message}`, 500);
  }
}

/**
 * 处理文件删除 (DELETE /api/file)
 */
async function handleDeleteFile(req, res, notesDir) {
  try {
    // 从查询参数获取ID
    const url = require('url');
    const parsed = url.parse(req.url, true);
    const id = parsed.query.id;

    // 参数验证
    if (!id) {
      return error(res, '缺少必要参数: id');
    }

    // 解码文件路径
    let relPath;
    try {
      relPath = Buffer.from(id, 'base64url').toString('utf8');
    } catch (err) {
      return error(res, '无效的文件ID');
    }

    const fullPath = path.resolve(path.join(notesDir, relPath));

    // 安全检查
    if (!isPathSafe(fullPath, notesDir)) {
      return error(res, '路径不安全');
    }

    // 检查文件是否存在
    if (!fs.existsSync(fullPath)) {
      return error(res, '文件不存在', 404);
    }

    // 删除文件
    fs.unlinkSync(fullPath);

    // 返回成功响应
    json(res, {
      id: id,
      path: relPath.replace(/\\/g, '/'),
      message: '文件删除成功'
    });

  } catch (err) {
    console.error('删除文件错误:', err);
    return error(res, `服务器错误: ${err.message}`, 500);
  }
}

/**
 * 处理目录创建 (POST /api/directories)
 */
async function handleCreateDirectory(req, res, notesDir) {
  try {
    // 读取请求体
    let body = '';
    for await (const chunk of req) {
      body += chunk;
    }

    const data = JSON.parse(body);
    const { path: dirPath } = data;

    // 参数验证
    if (!dirPath) {
      return error(res, '缺少必要参数: path');
    }

    // 安全检查
    const fullPath = path.resolve(path.join(notesDir, dirPath));
    if (!isPathSafe(fullPath, notesDir)) {
      return error(res, '路径不安全');
    }

    // 验证目录名
    const dirname = path.basename(fullPath);
    if (!isValidDirname(dirname)) {
      return error(res, '目录名不合法');
    }

    // 检查目录是否已存在
    if (fs.existsSync(fullPath)) {
      // 如果是目录，返回已存在
      if (fs.statSync(fullPath).isDirectory()) {
        return error(res, '目录已存在', 409);
      }
      // 如果是文件，返回冲突
      return error(res, '同名文件已存在', 409);
    }

    // 创建目录
    fs.mkdirSync(fullPath, { recursive: true });

    // 返回创建的目录信息
    const relativePath = path.relative(notesDir, fullPath);

    json(res, {
      path: relativePath.replace(/\\/g, '/'),
      message: '目录创建成功'
    }, 201);

  } catch (err) {
    console.error('创建目录错误:', err);
    if (err instanceof SyntaxError) {
      return error(res, '无效的JSON数据');
    }
    return error(res, `服务器错误: ${err.message}`, 500);
  }
}

const Busboy = require('busboy');

// async function handleUploadImage(req, res, notesDir, imagesDir) {
//   try {
//     if (!fs.existsSync(imagesDir)) {
//       fs.mkdirSync(imagesDir, { recursive: true });
//     }

//     // 用 busboy 解析，彻底解决二进制问题
//     const bb = Busboy({ headers: req.headers });

//     let filename = null;
//     let fileBuffer = null;
//     let altText = '';
//     let relativeTo = '';
//     const fields = {};

//     await new Promise((resolve, reject) => {
//       bb.on('file', (fieldname, stream, info) => {
//         if (fieldname !== 'image') return stream.resume();
//         filename = info.filename;
//         const chunks = [];
//         stream.on('data', chunk => chunks.push(chunk));
//         stream.on('end', () => { fileBuffer = Buffer.concat(chunks); });
//       });

//       bb.on('field', (name, val) => {
//         if (name === 'alt') altText = val;
//         if (name === 'relativeTo') relativeTo = val;
//       });

//       bb.on('finish', resolve);
//       bb.on('error', reject);
//       req.pipe(bb);
//     });

//     // 后续验证和保存逻辑保持不变
//     if (!filename || !fileBuffer) {
//       return error(res, '请选择要上传的图片文件');
//     }

//     const allowedExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
//     const ext = path.extname(filename).toLowerCase();
//     if (!allowedExtensions.includes(ext)) {
//       return error(res, `不支持的文件类型`);
//     }

//     const safeName = filename.replace(/[^\w.\u4e00-\u9fa5-]/g, '_');
//     const timestamp = Date.now();
//     const random = Math.random().toString(36).substring(2, 8);
//     const finalFilename = `${timestamp}_${random}_${safeName}`;
//     const savePath = path.join(imagesDir, finalFilename);

//     fs.writeFileSync(savePath, fileBuffer);

//     const fullPath = `images/${finalFilename}`;
//     json(res, {
//       success: true,
//       filename: finalFilename,
//       url: `/api/image?path=${Buffer.from(fullPath).toString('base64url')}`,
//       message: '图片上传成功'
//     });

//   } catch (err) {
//     console.error('图片上传错误:', err);
//     return error(res, `上传失败: ${err.message}`, 500);
//   }
// }

async function handleUploadImage(req, res, notesDir, imagesDir) {
  try {
    if (!fs.existsSync(imagesDir)) {
      fs.mkdirSync(imagesDir, { recursive: true });
    }

    const MAX_SIZE = 20 * 1024 * 1024; // 20MB

    // ← 加 limits 配置
    const bb = Busboy({ 
      headers: req.headers,
      limits: {
        fileSize: MAX_SIZE,  // 单文件最大 20MB
        files: 1,            // 最多 1 个文件
        fields: 10           // 最多 10 个文本字段
      }
    });

    let filename = null;
    let fileBuffer = null;
    let altText = '';
    let relativeTo = '';
    let fileTooLarge = false;  // ← 超限标志

    await new Promise((resolve, reject) => {
      bb.on('file', (fieldname, stream, info) => {
        if (fieldname !== 'image') return stream.resume();
        filename = info.filename;
        const chunks = [];

        stream.on('data', chunk => chunks.push(chunk));
        
        // ← 监听超限事件
        stream.on('limit', () => {
          fileTooLarge = true;
          stream.resume(); // 必须消费掉剩余数据，否则连接卡住
        });

        stream.on('end', () => {
          if (!fileTooLarge) {
            fileBuffer = Buffer.concat(chunks);
          }
        });
      });

      bb.on('field', (name, val) => {
        if (name === 'alt') altText = val;
        if (name === 'relativeTo') relativeTo = val;
      });

      bb.on('finish', resolve);
      bb.on('error', reject);
      req.pipe(bb);
    });

    // ← 超限提前返回
    if (fileTooLarge) {
      return error(res, `文件太大，最大支持 ${MAX_SIZE / 1024 / 1024}MB`, 413);
    }

    if (!filename || !fileBuffer) {
      return error(res, '请选择要上传的图片文件');
    }

    const allowedExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
    const ext = path.extname(filename).toLowerCase();
    if (!allowedExtensions.includes(ext)) {
      return error(res, `不支持的文件类型，仅支持: ${allowedExtensions.join(', ')}`);
    }

    const safeName = filename.replace(/[^\w.\u4e00-\u9fa5-]/g, '_');
    const timestamp = Date.now();
    const random = Math.random().toString(36).substring(2, 8);
    const finalFilename = `${timestamp}_${random}_${safeName}`;
    const savePath = path.join(imagesDir, finalFilename);

    fs.writeFileSync(savePath, fileBuffer);

    const fullPath = `images/${finalFilename}`;
    json(res, {
      success: true,
      filename: finalFilename,
      url: `/api/image?path=${Buffer.from(fullPath).toString('base64url')}`,
      message: '图片上传成功'
    });

  } catch (err) {
    console.error('图片上传错误:', err);
    return error(res, `上传失败: ${err.message}`, 500);
  }
}
// ── 导出模块 ──────────────────────────────────────

module.exports = {
  handleCreateFile,
  handleUpdateFile,
  handleDeleteFile,
  handleCreateDirectory,
  handleUploadImage,
  isPathSafe,
  isValidFilename,
  isValidDirname
};