import { cp, mkdir } from 'node:fs/promises';

const source = new URL('./src/', import.meta.url);
const target = new URL('./dist/', import.meta.url);
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log('Prototipe offline siap di dist/.');
