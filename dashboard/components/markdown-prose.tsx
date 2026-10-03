import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Hand-mapped to the site's own tokens rather than pulling in a typography
// plugin: it's ~10 element types, and this way the article can't drift from
// the rest of the design system.
const components: Components = {
  h1: ({ children }) => (
    <h1 className="font-[family-name:var(--font-display)] text-4xl font-extrabold leading-none tracking-tighter md:text-5xl">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-16 font-[family-name:var(--font-display)] text-2xl font-bold tracking-tight md:text-3xl">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-10 text-lg font-semibold text-[var(--color-text)]">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mt-5 max-w-[68ch] leading-relaxed text-[var(--color-muted)]">{children}</p>
  ),
  strong: ({ children }) => <strong className="font-semibold text-[var(--color-text)]">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target={href?.startsWith("http") ? "_blank" : undefined}
      rel={href?.startsWith("http") ? "noopener noreferrer" : undefined}
      className="cursor-pointer text-[var(--color-grounded)] underline underline-offset-4 transition-opacity duration-200 hover:opacity-80"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mt-5 max-w-[68ch] list-disc space-y-2 pl-5 text-[var(--color-muted)]">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mt-5 max-w-[68ch] list-decimal space-y-2 pl-5 text-[var(--color-muted)]">{children}</ol>
  ),
  hr: () => <hr className="my-14 border-[var(--color-border)]" />,
  code: ({ className, children }) => {
    const isBlock = typeof className === "string" && className.startsWith("language-");
    if (isBlock) {
      return (
        <code className="block font-[family-name:var(--font-mono)] text-[13px] leading-relaxed text-[var(--color-text)]">
          {children}
        </code>
      );
    }
    return (
      <code className="rounded-md bg-[var(--color-elevated)] px-1.5 py-0.5 font-[family-name:var(--font-mono)] text-[0.85em] text-[var(--color-text)]">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="mt-6 overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-[var(--color-border)] px-3 py-2 text-left font-medium text-[var(--color-muted)]">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-[var(--color-border)] px-3 py-2 text-[var(--color-text)]">{children}</td>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mt-6 border-l-2 border-[var(--color-grounded)] pl-5 text-[var(--color-muted)]">
      {children}
    </blockquote>
  ),
};

export function MarkdownProse({ markdown }: { markdown: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </ReactMarkdown>
  );
}
