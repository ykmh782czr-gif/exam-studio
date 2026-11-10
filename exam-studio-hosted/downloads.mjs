/** Serve an oversized dataset as a stream of verified build-time asset parts. */

export function splitDownload(request, assets, manifest) {
  const url = new URL(request.url);
  const filename = url.pathname.startsWith('/files/') ? url.pathname.slice(7) : '';
  if (!Object.hasOwn(manifest, filename)) return null;
  const dataset = manifest[filename];
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  const headers = {
    'Content-Type': 'application/vnd.sqlite3',
    'Content-Disposition': 'attachment; filename="' + filename + '"',
    'Content-Length': String(dataset.bytes),
    'ETag': '"' + dataset.sha256 + '"',
  };
  if (request.method === 'HEAD') return new Response(null, { headers });

  let index = 0;
  let reader;
  let remaining = 0;
  const stream = new ReadableStream({
    async pull(controller) {
      try {
        while (true) {
          if (!reader) {
            const part = dataset.parts[index++];
            if (!part) {
              controller.close();
              return;
            }
            const response = await assets.fetch(new Request(new URL(part.path, url), { signal: request.signal }));
            if (response.status !== 200 || !response.body) throw new Error('Download part unavailable.');
            remaining = part.bytes;
            reader = response.body.getReader();
          }
          const { done, value } = await reader.read();
          if (done) {
            if (remaining !== 0) throw new Error('Download part is truncated.');
            reader.releaseLock();
            reader = undefined;
            continue;
          }
          remaining -= value.byteLength;
          if (remaining < 0) throw new Error('Download part exceeds expected length.');
          controller.enqueue(value);
          return;
        }
      } catch (error) {
        if (reader) await reader.cancel().catch(() => {});
        controller.error(error);
      }
    },
    cancel(reason) {
      return reader?.cancel(reason);
    },
  });
  return new Response(stream, { headers });
}
