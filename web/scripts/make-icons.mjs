// Generates the PWA icons with built-in modules only (raw PNG via zlib).
// Run: node scripts/make-icons.mjs
import { deflateSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const out = path.join(path.dirname(fileURLToPath(import.meta.url)), "../public/icons");
mkdirSync(out, { recursive: true });

const NAV = [0x0b, 0x39, 0x54];
const A = [0x6c, 0x5c, 0xe7]; // relationship violet
const B = [0x2b, 0xa5, 0x7a]; // match green

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf) {
  let c = 0xffffffff;
  for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

/** A navy square with a centred gradient mark. `mark` is the mark's share of the width. */
function png(size, mark) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  const side = size * mark;
  const from = (size - side) / 2;
  const radius = side * 0.18;
  for (let y = 0; y < size; y++) {
    const row = y * (size * 4 + 1);
    raw[row] = 0;
    for (let x = 0; x < size; x++) {
      let color = NAV;
      const inX = x >= from && x < from + side;
      const inY = y >= from && y < from + side;
      if (inX && inY) {
        const cx = Math.min(x - from, from + side - 1 - x);
        const cy = Math.min(y - from, from + side - 1 - y);
        const corner = cx < radius && cy < radius ? Math.hypot(radius - cx, radius - cy) > radius : false;
        if (!corner) {
          const t = ((x - from) + (y - from)) / (2 * side);
          color = A.map((v, i) => Math.round(v + (B[i] - v) * t));
        }
      }
      const i = row + 1 + x * 4;
      raw[i] = color[0];
      raw[i + 1] = color[1];
      raw[i + 2] = color[2];
      raw[i + 3] = 255;
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8; // bit depth
  header[9] = 6; // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const files = [
  ["icon-192.png", 192, 0.5],
  ["icon-512.png", 512, 0.5],
  ["maskable-512.png", 512, 0.4], // keeps the mark inside the 80% safe zone
  ["apple-touch-icon.png", 180, 0.5],
];
for (const [name, size, mark] of files) {
  writeFileSync(path.join(out, name), png(size, mark));
  console.log("wrote", name);
}
