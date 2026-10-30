export const MCP_URL =
  "https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp";

export const GITHUB_URL = "https://github.com/karthikreddyyalala/FinRAG";

// Absolute (/#id) rather than bare (#id) so the nav still works from the
// blog pages, where those sections don't exist on the current route.
export const NAV_LINKS = [
  { href: "/#connect", label: "Connect" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#verifier", label: "The verifier" },
  { href: "/#tools", label: "Tools" },
  { href: "/#results", label: "Results" },
  { href: "/#incidents", label: "Incidents" },
  { href: "/blog/bugs-that-looked-like-answers", label: "Writing" },
] as const;
