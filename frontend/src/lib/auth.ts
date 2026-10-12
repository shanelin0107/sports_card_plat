// Shared by middleware (edge runtime) and route handlers (node). Web Crypto only.

export const SESSION_COOKIE = 'scp_session';

export function authEnabled(): boolean {
  return Boolean(process.env.SITE_PASSWORD);
}

export async function sessionToken(): Promise<string> {
  const material = `${process.env.SITE_PASSWORD ?? ''}:${process.env.SESSION_SECRET ?? 'change-me'}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(material));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}
