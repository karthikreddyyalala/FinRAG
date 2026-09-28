import { Nav } from "@/components/nav";
import { SectionRail } from "@/components/section-rail";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { MetricsBand } from "@/components/metrics-band";

export default function Home() {
  return (
    <>
      <Nav />
      <SectionRail />
      <main id="main" className="min-h-[100dvh]">
        <Hero />
        <MetricsBand />
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
