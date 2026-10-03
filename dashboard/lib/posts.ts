import { readFileSync } from "node:fs";
import { join } from "node:path";

export type Post = {
  slug: string;
  title: string;
  description: string;
  date: string;
  readingMinutes: number;
};

export const POSTS: Post[] = [
  {
    slug: "bugs-that-looked-like-answers",
    title: "Bugs that looked like answers",
    description:
      "Five real bugs in a financial RAG system that never crashed, never errored, and produced confident, well-cited, wrong answers the whole time.",
    date: "2026-10-03",
    readingMinutes: 8,
  },
];

export function getPost(slug: string): Post | undefined {
  return POSTS.find((p) => p.slug === slug);
}

/** Server-only: reads the post body from content/blog at build time. */
export function readPostMarkdown(slug: string): string {
  return readFileSync(join(process.cwd(), "content", "blog", `${slug}.md`), "utf-8");
}
