# Legacy Product Agent Pointer

Pipeline v2 is `ACTIVE`. Product work is now routed by the controller through the Product, UX,
Design Review and live Browser Product QA stages declared in the task profile.

- Canon: [process/PIPELINE-RU.md](process/PIPELINE-RU.md)
- Machine contract: [pipeline/pipeline.yml](../pipeline/pipeline.yml)
- Agent entrypoint: [../AGENTS.md](../AGENTS.md)

The former Product-agent instructions are retired as a standalone gate. A Product verdict is valid
only as a controller receipt bound to the task inputs and cannot be reused after dependent code,
contract or case changes.
