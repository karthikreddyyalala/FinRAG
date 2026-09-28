import { Nav } from "@/components/nav";
import { SectionRail } from "@/components/section-rail";
import { Footer } from "@/components/footer";
import { Cited } from "@/components/cited";

export default function Home() {
  return (
    <>
      <Nav />
      <SectionRail />
      <main id="main" className="min-h-[100dvh] px-4 py-16 md:px-8">
        <h1 className="font-[family-name:var(--font-display)] text-4xl md:text-6xl tracking-tighter leading-none font-extrabold">
          FinRAG MCP
        </h1>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Nav, section rail, and footer shell — content sections build out next.
        </p>
        <p className="mt-4">
          Numerical accuracy: <Cited metric="numerical_accuracy_financebench" />
        </p>
        <div id="how-it-works" className="h-[60vh]" />
        <div id="verifier" className="h-[60vh]" />
        <div id="tools" className="h-[60vh]" />
        <div id="results" className="h-[60vh]" />
        <div id="incidents" className="h-[60vh]" />
        <div id="deploy" className="h-[60vh]" />
      </main>
      <Footer />
    </>
  );
}
