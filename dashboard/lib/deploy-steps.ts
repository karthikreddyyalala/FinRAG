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
    title: "Point Claude Desktop at your deployment",
    command:
      '{\n  "mcpServers": {\n    "finrag": {\n      "command": "npx",\n      "args": ["mcp-remote", "<your-function-url>/mcp"]\n    }\n  }\n}',
  },
] as const;
