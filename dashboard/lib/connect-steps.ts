import { MCP_URL } from "@/lib/constants";

export const CONNECT_CLIENTS = [
  {
    title: "Claude (claude.ai and Claude Desktop)",
    note: "Customize > Connectors > + Add > Add custom connector. Enter a name, paste the URL, and continue. Choose No sign in if asked. On Team and Enterprise plans an Owner adds it first under Organization settings > Connectors.",
    command: MCP_URL,
  },
  {
    title: "Claude Code",
    note: "One command in your terminal.",
    command: `claude mcp add --transport http finrag ${MCP_URL}`,
  },
  {
    title: "Cursor and other MCP clients",
    note: "In Cursor, add this to .cursor/mcp.json in your project or ~/.cursor/mcp.json. Other clients that speak streamable HTTP take the same URL, though their config keys may differ.",
    command: JSON.stringify({ mcpServers: { finrag: { url: MCP_URL } } }, null, 2),
  },
] as const;

export const LIMITS = [
  "Shared limit: 30 calls a minute and 1,000 a day, counted across everyone using the server.",
  "Coverage: 71 companies. Call list_covered_companies for the exact years of each one.",
  "Evidence only: the server returns cited passages, and your own model writes the answer.",
] as const;

export const DEPLOY_PREREQUISITES =
  "You need an AWS account with the CLI configured, Node 20 or newer, Python 3.12 or newer, an OpenAI API key and a Pinecone account. Everything deploys to us-east-1.";

export const DEPLOY_STEPS = [
  {
    title: "Create the Pinecone index",
    command: "Serverless index named finrag-filings, 1536 dimensions, cosine metric\n(it must match OpenAI text-embedding-3-small)",
  },
  {
    title: "Clone and install",
    command:
      "git clone https://github.com/karthikreddyyalala/FinRAG.git && cd FinRAG\npython3 -m venv .venv && source .venv/bin/activate\npip install -r requirements.txt",
  },
  {
    title: "Rename the S3 buckets (names are global), then set SEC_USER_AGENT in pipeline/edgar_client.py to your name and email",
    command:
      "perl -pi -e 's/finrag-(raw|processed)-filings/yourname-$1-filings/g' $(git grep -lE 'finrag-(raw|processed)-filings' -- '*.py')",
  },
  {
    title: "Store your keys in SSM",
    command:
      "aws ssm put-parameter --region us-east-1 --name /finrag/openai-api-key --type SecureString --value <your-openai-key>\naws ssm put-parameter --region us-east-1 --name /finrag/pinecone-api-key --type SecureString --value <your-pinecone-key>",
  },
  {
    title: "Deploy the CDK stacks (alert_email is optional: alarm emails and a $10 monthly budget alert)",
    command:
      "npx aws-cdk bootstrap aws://<account-id>/us-east-1\nnpx aws-cdk deploy --all --require-approval never -c alert_email=you@example.com",
  },
  {
    title: "Build the corpus (takes hours, a few dollars of OpenAI embeddings), then seed the weekly refresh",
    command:
      "export OPENAI_API_KEY=<your-openai-key> PINECONE_API_KEY=<your-pinecone-key>\nPYTHONPATH=. python scripts/bootstrap_corpus.py\naws s3 sync evals/results/chunk_cache s3://yourname-processed-filings/chunk_cache/",
  },
  {
    title: "Connect with the McpEndpoint stack output",
    command: "claude mcp add --transport http finrag <McpEndpoint, already ending in /mcp>",
  },
] as const;
