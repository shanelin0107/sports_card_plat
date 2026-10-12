import { NextRequest, NextResponse } from 'next/server';

import { apiBaseForProxy } from '@/lib/server-api';

// Thin authenticated proxy: browser -> Next.js (session cookie checked by middleware)
// -> FastAPI (X-API-Key added here). Only /api/v1/* is reachable.
async function forward(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (path.some((p) => p === '..' || p.includes('/'))) {
    return NextResponse.json({ detail: 'Bad path' }, { status: 400 });
  }
  const target = `${apiBaseForProxy()}/api/v1/${path.map(encodeURIComponent).join('/')}${req.nextUrl.search}`;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.API_KEY) headers['X-API-Key'] = process.env.API_KEY;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : await req.text(),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ detail: 'API unreachable' }, { status: 503 });
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
      ...(upstream.headers.get('Cache-Control') ? { 'Cache-Control': upstream.headers.get('Cache-Control')! } : {}),
    },
  });
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
