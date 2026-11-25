import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('./dist/', import.meta.url)));
const types = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8',
};
const host = process.env.PROTOTYPE_HOST || '127.0.0.1';
const port = Number(process.env.PROTOTYPE_PORT || 4173);

try {
  await stat(resolve(root, 'index.html'));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
  console.error('Jalankan npm run build terlebih dahulu.');
  process.exit(1);
}

createServer(async (request, response) => {
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'HEAD'].includes(request.method)) {
    return response.writeHead(405, { Allow: 'GET, HEAD' }).end();
  }

  try {
    const url = new URL(request.url, 'http://localhost');
    const pathname = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
    const file = resolve(root, `.${pathname}`);
    const type = types[extname(file)];
    if (!file.startsWith(`${root}${sep}`) || !type) return response.writeHead(404).end();
    const info = await stat(file);
    if (!info.isFile()) return response.writeHead(404).end();

    response.writeHead(200, { 'Content-Type': type, 'Content-Length': info.size });
    if (request.method === 'HEAD') return response.end();
    const stream = createReadStream(file);
    stream.on('error', () => response.destroy());
    response.on('close', () => stream.destroy());
    stream.pipe(response);
  } catch (error) {
    response.writeHead(error instanceof URIError ? 400 : 404).end();
  }
}).listen(port, host, () => console.log(`Kartu Risiko Pi berjalan di http://${host}:${port}/`));
