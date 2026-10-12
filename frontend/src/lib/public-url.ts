import type { NextRequest } from 'next/server';

// Build redirects from the Host the browser used: behind a proxy (Docker, standalone)
// req.url can carry the internal bind address (0.0.0.0), which the browser can't reach.
export function publicUrl(req: NextRequest, path: string) {
  const host = req.headers.get('x-forwarded-host') ?? req.headers.get('host') ?? req.nextUrl.host;
  const proto = req.headers.get('x-forwarded-proto') ?? req.nextUrl.protocol.replace(':', '');
  return `${proto}://${host}${path}`;
}
