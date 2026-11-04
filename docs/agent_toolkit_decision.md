# Decision: PayPal agent tooling for the front-desk agent

**Decision: do not use it.** The agent's free tools go through `HoldDesk` (the N1 adapter behind
the `PaymentProvider` port); gated tools go through `AgentGate`. Checked 2026-11-04.

## What exists (read from the package indexes)

| Package | Version | What it is | Source |
|---|---|---|---|
| `@paypal/agent-toolkit` (npm, TypeScript) | 1.11.0 | Function-calling tools for OpenAI Agents SDK, LangChain, Vercel AI SDK and MCP | https://registry.npmjs.org/@paypal/agent-toolkit |
| `paypal-agent-toolkit` (PyPI) | 1.11.0 | Python port for OpenAI, LangChain and CrewAI | https://pypi.org/pypi/paypal-agent-toolkit/json |
| `@paypal/mcp` (npm) | 1.8.1 | MCP server (`npx -y @paypal/mcp --tools=all`), auth by `PAYPAL_ACCESS_TOKEN` | https://registry.npmjs.org/@paypal/mcp |
| Source repository | | | https://github.com/paypal/agent-toolkit |

Tool surface (from the READMEs): invoices, `create_order`, `get_order`, `pay_order`,
`create_refund` / `get_refund` (TypeScript version), disputes, shipment tracking, catalog,
subscriptions, transaction reporting.

## Why it does not fit

1. **Wrong money lifecycle.** Our stories need Orders v2 with intent AUTHORIZE, then authorize,
   capture, reauthorize and void. The toolkit lists no authorize, reauthorize, capture or void
   tool; `pay_order` pays an order directly, which is exactly the "agent moves money" path the
   mandate gate exists to remove.
2. **It bundles money movement with the free tools.** `pay_order` and `create_refund` are
   callable tools. Using the toolkit would hand the model a way around the gate, and filtering
   them out leaves only `create_order`/`get_order`, which `HoldDesk` already covers.
3. **No idempotency control.** Our contract requires every capture/refund/void to carry the
   mandate's `jti` as `PayPal-Request-Id`; the toolkit does not expose that.
4. **Dependency weight and conflicts.** The Python package pins `openai-agents==0.0.2`,
   `langchain==0.3.23` and `crewai-tools==0.13.2` (PyPI `requires_dist`), none of which we use.
   The npm packages need Node, a second runtime, for a Python project.
5. **Auth model.** `@paypal/mcp` takes an access token; N1 gets one from `PAYPAL_CLIENT_ID` /
   `PAYPAL_CLIENT_SECRET` itself, as the contract says.

## What we keep from it

It is a useful reference for tool names and PayPal's agent guidance. If the coordinator wants a
"built on PayPal's toolkit" angle for the submission, the only safe use is read-only: expose
`get_order` as a free tool through an adapter, never `pay_order` or `create_refund`.
Not done: it adds a dependency for no behavior the demo needs.
