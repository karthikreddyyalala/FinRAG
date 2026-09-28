import { Nav } from "@/components/nav";
import { SectionRail } from "@/components/section-rail";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { MetricsBand } from "@/components/metrics-band";
import { Problem } from "@/components/problem";
import { HowItWorks } from "@/components/how-it-works";
import { VerifierDemo } from "@/components/verifier-demo";
import { ToolsBento } from "@/components/tools-bento";
import { IncidentLog } from "@/components/incident-log";
import { StackGrid } from "@/components/stack-grid";
import { DeploySteps } from "@/components/deploy-steps";
import { ResultsSection } from "@/components/results-section";
import { CostLatency } from "@/components/cost-latency";

export default function Home() {
  return (
    <>
      <Nav />
      <SectionRail />
      <main id="main" className="min-h-[100dvh]">
        <Hero />
        <MetricsBand />
        <Problem />
        <div id="how-it-works">
          <HowItWorks />
        </div>
        <VerifierDemo />
        <ToolsBento />
        <ResultsSection />
        <CostLatency />
        <IncidentLog />
        <StackGrid />
        <DeploySteps />
      </main>
      <Footer />
    </>
  );
}
