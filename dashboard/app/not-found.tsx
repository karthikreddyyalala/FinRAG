import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[100dvh] flex-col items-center justify-center px-4 text-center">
      <p className="font-[family-name:var(--font-mono)] text-sm text-[var(--color-flagged)]">
        [exact page unavailable in retrieved context]
      </p>
      <h1 className="mt-4 font-[family-name:var(--font-display)] text-4xl font-extrabold tracking-tighter">
        404
      </h1>
      <p className="mt-2 max-w-[45ch] text-[var(--color-muted)]">
        This page doesn&apos;t exist, and we&apos;re not going to guess what you meant.
      </p>
      <Link
        href="/"
        className="mt-8 cursor-pointer rounded-full bg-[var(--color-grounded)] px-6 py-3 text-sm font-semibold text-[var(--color-bg)] transition-transform duration-200 active:translate-y-[1px] active:scale-[0.98]"
      >
        Back to the homepage
      </Link>
    </main>
  );
}
