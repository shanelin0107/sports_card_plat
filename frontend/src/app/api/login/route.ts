import { NextRequest, NextResponse } from 'next/server';

import { SESSION_COOKIE, safeEqual, sessionToken } from '@/lib/auth';
import { publicUrl } from '@/lib/public-url';

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const password = String(form.get('password') ?? '');
  const nextPath = String(form.get('next') ?? '/');
  const safeNext = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/';
  const expected = process.env.SITE_PASSWORD ?? '';

  if (!expected || !safeEqual(password, expected)) {
    return NextResponse.redirect(publicUrl(req, `/login?error=1&next=${encodeURIComponent(safeNext)}`), 303);
  }
  const res = NextResponse.redirect(publicUrl(req, safeNext), 303);
  res.cookies.set(SESSION_COOKIE, await sessionToken(), {
    httpOnly: true,
    sameSite: 'lax',
    secure: publicUrl(req, '/').startsWith('https://'),
    path: '/',
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
