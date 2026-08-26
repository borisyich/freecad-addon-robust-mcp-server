# Agent guidance architecture

The project uses one engineering Skill bundle and thin delivery layers. The goal
is to keep workflow policy out of MCP initialization and tool metadata.

## Source of truth

```text
.agents/skills/freecad-engineering/
├── SKILL.md                 # router + common contract
├── references/              # one workflow file per target task
└── agents/openai.yaml       # routing metadata
```

## What the MCP server sends at initialization

With this repository's current `mcp>=1.25,<2` protocol path, the MCP `initialize`
response contains only the short `MCP_INSTRUCTIONS` string from
`src/freecad_mcp/server.py`. It points to the engineering Skill and the final
validator; it does not embed the Skill or any reference file. Revisit this
section when migrating to a newer MCP protocol/SDK discovery model.

Prompts and resources are registered capabilities. Their contents are returned
only when a client explicitly reads/invokes them. Likewise, tool schemas are
returned through `tools/list`; many clients choose to load that list early, but
that is client behavior rather than part of the Skill payload.

## Delivery layers

1. **`MCP_INSTRUCTIONS`** — minimal protocol-level router.
2. **`AGENTS.md`** — minimal repository-aware router.
3. **Skill metadata** — allows implicit task routing where supported.
4. **`freecad://skills/freecad-engineering`** — same canonical `SKILL.md` through MCP.
5. **Skill reference resources** — loaded only for the selected task.
6. **Prompts** — compact compatibility routers; no duplicate engineering policy.
7. **Tool schemas** — authoritative operation contracts.
8. **`freecad://capabilities`** — compact discovery index, not a second tool manual.

## Selective loading

For a CAD task:

1. read/activate `freecad://skills/freecad-engineering`;
2. classify the task using its router;
3. read only the selected reference file(s);
4. inspect exact tool schemas only when needed.

Do not preload the complete Skill bundle, all prompts, the capability index, and
all workflow resources at once. They overlap by purpose and waste context.

## Compatibility prompts/resources

Legacy prompt names and workflow resources remain registered so existing clients
do not break, but they now route to the canonical Skill instead of carrying
large standalone guides.

## Tool-registry budget

The server keeps tool descriptions to the concise purpose paragraph, removes
cosmetic schema titles, and leaves exact typed arguments in JSON Schema. This is
important because clients often load `tools/list` eagerly and the tool registry
is typically a larger startup-context cost than `MCP_INSTRUCTIONS` itself.
