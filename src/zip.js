/*
 * Lector/escritor ZIP mínimo, sin dependencias.
 * Usa las APIs nativas del navegador (DecompressionStream / CompressionStream),
 * por lo que todo el procesamiento ocurre en el propio equipo.
 * Suficiente para DOCX, XLSX, PPTX y ODT/ODS/ODP.
 */
(function (global) {
  'use strict';

  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  async function pipe(bytes, stream) {
    const out = new Response(new Blob([bytes]).stream().pipeThrough(stream));
    return new Uint8Array(await out.arrayBuffer());
  }
  const inflateRaw = (b) => pipe(b, new DecompressionStream('deflate-raw'));
  const deflateRaw = (b) => pipe(b, new CompressionStream('deflate-raw'));

  const utf8 = new TextDecoder('utf-8');
  const cp437 = (bytes) => Array.from(bytes, (b) => String.fromCharCode(b)).join('');

  /** Lee un ZIP y devuelve [{name, method, data(Uint8Array descomprimido), dosTime, dosDate, extAttr}] en orden. */
  async function readZip(buffer) {
    const u8 = new Uint8Array(buffer);
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    // Buscar el registro "End of central directory".
    let eocd = -1;
    for (let i = u8.length - 22; i >= Math.max(0, u8.length - 65557); i--) {
      if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error('El archivo no es un ZIP válido (¿documento dañado o cifrado?).');
    const count = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const entries = [];
    for (let i = 0; i < count; i++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('Directorio central ZIP corrupto.');
      const flags = dv.getUint16(p + 8, true);
      const method = dv.getUint16(p + 10, true);
      const dosTime = dv.getUint16(p + 12, true);
      const dosDate = dv.getUint16(p + 14, true);
      const compSize = dv.getUint32(p + 20, true);
      const nameLen = dv.getUint16(p + 28, true);
      const extraLen = dv.getUint16(p + 30, true);
      const commentLen = dv.getUint16(p + 32, true);
      const extAttr = dv.getUint32(p + 38, true);
      const localOff = dv.getUint32(p + 42, true);
      const nameBytes = u8.subarray(p + 46, p + 46 + nameLen);
      const name = flags & 0x800 ? utf8.decode(nameBytes) : cp437(nameBytes);
      if (flags & 0x1) throw new Error('El documento está protegido con contraseña. Quite la protección antes de anonimizarlo.');
      const lNameLen = dv.getUint16(localOff + 26, true);
      const lExtraLen = dv.getUint16(localOff + 28, true);
      const start = localOff + 30 + lNameLen + lExtraLen;
      const raw = u8.subarray(start, start + compSize);
      let data;
      if (method === 0) data = raw.slice();
      else if (method === 8) data = await inflateRaw(raw);
      else throw new Error('Método de compresión ZIP no soportado: ' + method);
      entries.push({ name, method, data, dosTime, dosDate, extAttr });
      p += 46 + nameLen + extraLen + commentLen;
    }
    return entries;
  }

  /** Escribe un ZIP a partir de entradas {name, method, data}. Conserva el orden. */
  async function writeZip(entries) {
    const enc = new TextEncoder();
    const chunks = [];
    const central = [];
    let offset = 0;
    for (const e of entries) {
      const nameBytes = enc.encode(e.name);
      const method = e.method === 0 ? 0 : 8;
      const comp = method === 0 ? e.data : await deflateRaw(e.data);
      const crc = crc32(e.data);
      const time = e.dosTime ?? 0;
      const date = e.dosDate ?? 0x21; // 1980-01-01
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true);
      lh.setUint16(4, 20, true);
      lh.setUint16(6, 0x800, true);
      lh.setUint16(8, method, true);
      lh.setUint16(10, time, true);
      lh.setUint16(12, date, true);
      lh.setUint32(14, crc, true);
      lh.setUint32(18, comp.length, true);
      lh.setUint32(22, e.data.length, true);
      lh.setUint16(26, nameBytes.length, true);
      lh.setUint16(28, 0, true);
      chunks.push(new Uint8Array(lh.buffer), nameBytes, comp);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true);
      ch.setUint16(4, 20, true);
      ch.setUint16(6, 20, true);
      ch.setUint16(8, 0x800, true);
      ch.setUint16(10, method, true);
      ch.setUint16(12, time, true);
      ch.setUint16(14, date, true);
      ch.setUint32(16, crc, true);
      ch.setUint32(20, comp.length, true);
      ch.setUint32(24, e.data.length, true);
      ch.setUint16(28, nameBytes.length, true);
      ch.setUint32(38, e.extAttr ?? 0, true);
      ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), nameBytes);
      offset += 30 + nameBytes.length + comp.length;
    }
    const cdSize = central.reduce((s, c) => s + c.length, 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true);
    end.setUint16(8, entries.length, true);
    end.setUint16(10, entries.length, true);
    end.setUint32(12, cdSize, true);
    end.setUint32(16, offset, true);
    return new Blob([...chunks, ...central, new Uint8Array(end.buffer)]);
  }

  global.MiniZip = { readZip, writeZip, crc32 };
})(typeof window !== 'undefined' ? window : globalThis);
