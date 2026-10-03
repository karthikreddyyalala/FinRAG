import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { MarkdownProse } from "@/components/markdown-prose";
import { POSTS, getPost, readPostMarkdown } from "@/lib/posts";

export function generateStaticParams() {
  return POSTS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) return {};
  return {
    title: `${post.title} | FinRAG MCP`,
    description: post.description,
    openGraph: { title: post.title, description: post.description, type: "article" },
    twitter: { card: "summary_large_image", title: post.title, description: post.description },
  };
}

export default async function BlogPost({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) notFound();

  const markdown = readPostMarkdown(slug);
  const formattedDate = new Date(post.date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <>
      <Nav />
      <main id="main" className="px-4 py-16 md:px-8">
        <article className="mx-auto max-w-[760px]">
          <Link
            href="/"
            className="cursor-pointer font-[family-name:var(--font-mono)] text-xs text-[var(--color-muted)] transition-colors duration-200 hover:text-[var(--color-text)]"
          >
            ← FinRAG MCP
          </Link>
          <p className="mt-8 font-[family-name:var(--font-mono)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
            {formattedDate} · {post.readingMinutes} min read
          </p>
          <MarkdownProse markdown={markdown} />
        </article>
      </main>
      <Footer />
    </>
  );
}
