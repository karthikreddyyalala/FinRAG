import { ImageResponse } from "next/og";
import { getMetric } from "@/lib/metrics";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  const accuracy = getMetric("numerical_accuracy_financebench");
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: "#09090B",
          color: "#EDEDEF",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ fontSize: 28, color: "#8A8F98", display: "flex" }}>FinRAG MCP</div>
        <div style={{ fontSize: 64, fontWeight: 800, marginTop: 24, lineHeight: 1.1, display: "flex" }}>
          Financial answers you can check.
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 48 }}>
          <div style={{ fontSize: 72, fontWeight: 700, color: "#45C98F", display: "flex" }}>{accuracy.display}</div>
          <div style={{ fontSize: 24, color: "#8A8F98", display: "flex" }}>numerical accuracy, FinanceBench</div>
        </div>
      </div>
    ),
    { ...size }
  );
}
