import { MCP_URL } from "@/lib/constants";

export const CONNECT_CLIENTS = [
  {
    title: "Claude (claude.ai and Claude Desktop)",
    note: "Customize > Connectors > + Add > Add custom connector. Enter a name, paste the URL, and continue. Choose No sign in if asked.",
    command: MCP_URL,
  },
  {
    title: "Claude Code",
    note: "One command in your terminal.",
    command: `claude mcp add --transport http finrag ${MCP_URL}`,
  },
  {
    title: "Cursor and other MCP clients",
    note: "Add this to the client's MCP config file.",
    command: JSON.stringify({ mcpServers: { finrag: { url: MCP_URL } } }, null, 2),
  },
] as const;

export const LIMITS = [
  "Shared limit: 30 calls a minute and 1,000 a day, counted across everyone using the server.",
  "Coverage: 71 companies. Call list_covered_companies for the exact years of each one.",
  "Evidence only: the server returns cited passages, and your own model writes the answer.",
] as const;

export const DEPLOY_STEPS = [
  {
    title: "Clone the repo",
    command: "git clone https://github.com/karthikreddyyalala/FinRAG.git\ncd FinRAG",
  },
  {
    title: "Set your own SSM parameters",
    command:
      "aws ssm put-parameter --name /finrag/openai-api-key --type SecureString --value <your-key>\naws ssm put-parameter --name /finrag/pinecone-api-key --type SecureString --value <your-key>",
  },
  {
    title: "Deploy the CDK stacks",
    command: 'PYTHONPATH=. npx aws-cdk deploy --all --app "python3 infra/app.py" --require-approval never',
  },
  {
    title: "Bootstrap the corpus",
    command: "python3 scripts/bootstrap_corpus.py",
  },
  {
    title: "Connect with your URL",
    command: "claude mcp add --transport http finrag <your-function-url>/mcp",
  },
] as const;
