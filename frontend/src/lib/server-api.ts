import 'server-only';

// Server components talk to FastAPI directly. API_BASE_URL is a *server* variable:
// in Docker it is http://backend:8000, on Vercel it is the Render URL.
const API_BASE = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, {
      cache: 'no-store',
      headers: process.env.API_KEY ? { 'X-API-Key': process.env.API_KEY } : {},
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_BASE}`, 503);
  }
  if (!res.ok) throw new ApiError(`${path} → HTTP ${res.status}`, res.status);
  return res.json() as Promise<T>;
}

/** Fetch that resolves to null instead of throwing, so one failing panel doesn't blank the page. */
export async function apiTry<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch {
    return null;
  }
}

export function apiBaseForProxy(): string {
  return API_BASE;
}
