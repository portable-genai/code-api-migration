# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository (H5, the Code and API Migration Copilot) as a common base for deterministic
repository and API migration analysis. Each file is written for a specific audience; skim the
one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec and security review | what the service ingests, server-side identity, the exposure guard, redaction, the audit chain and its anchor, secrets, supply chain, what is deliberately out of scope |
| [portability-faq.md](portability-faq.md) | Architecture, cloud and exit planning | the no-lock-in claim and its one recorded exemption, the three profiles, the executable portability check, the on-premises exit, residency |
| [features-faq.md](features-faq.md) | Product, engineering and delivery | what the copilot produces, which engines produce it, the fact that no model is in the path, and where this repo's responsibility stops |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rebranding, taking upstream fixes, adding a pack, adding a port, versioning, whether the demo rots |
| [compliance-faq.md](compliance-faq.md) | Compliance, model risk and second line | maker-checker, PII posture, auditability, the eval gate, deploy-time residency, and what is still owed |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the GRC
catalog. Where a concern belongs to another repo (the guardrail gateway Hrz1, the governed
knowledge base Hrz2, the agent registry Hrz3, the AI-quality gate Hrz4, observability and the
shared WORM audit sink Hrz5, the human-review console Hrz7), the FAQ points at it and explains
the boundary rather than duplicating it. See [features-faq.md](features-faq.md) for the full
"what this repo owns vs what it integrates" map.
