import { Logo } from '@/components/Logo';

export const metadata = { title: 'Sign in · Slab Terminal' };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string; next?: string }> }) {
  const { error, next = '/' } = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form action="/api/login" method="post" className="panel w-full max-w-sm space-y-5 p-6">
        <Logo />
        <div>
          <h1 className="text-lg font-bold">Sign in</h1>
          <p className="mt-1 text-[13px] text-muted">This is a private collection.</p>
        </div>
        <input type="hidden" name="next" value={next} />
        <div className="space-y-1.5">
          <label htmlFor="password" className="eyebrow">
            Password
          </label>
          <input id="password" name="password" type="password" required autoFocus autoComplete="current-password" className="field" />
          {error && <p className="text-[13px] text-down">Wrong password.</p>}
        </div>
        <button className="btn-primary w-full">Enter</button>
      </form>
    </main>
  );
}
