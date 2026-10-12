import { NextResponse, type NextRequest } from 'next/server';

import { SESSION_COOKIE, authEnabled, safeEqual, sessionToken } from '@/lib/auth';
import { publicUrl } from '@/lib/public-url';

const PUBLIC = ['/login', '/api/login'];

function pass(req: NextRequest) {
  // Expose the path to server components (the root layout hides the header on /login).
  const headers = new Headers(req.headers);
  headers.set('x-pathname', req.nextUrl.pathname);
  return NextResponse.next({ request: { headers } });
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (!authEnabled() || PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return pass(req);

  const cookie = req.cookies.get(SESSION_COOKIE)?.value ?? '';
  if (cookie && safeEqual(cookie, await sessionToken())) return pass(req);

  if (pathname.startsWith('/api/')) {
    return NextResponse.json({ detail: 'Not signed in' }, { status: 401 });
  }
  const next = encodeURIComponent(pathname + req.nextUrl.search);
  return NextResponse.redirect(publicUrl(req, `/login?next=${next}`));
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|icon.svg).*)'],
};
