# Progressive Disclosure & Token Economics in S.A.N.E.

## 1. The Context Waste Crisis in AI Coding

In modern software development with AI agents (such as Claude Code, Cursor, Copilot, and Windsurf), agents waste between **60% and 80%** of their total context window merely searching for where code is located.

### 1.1 The Naive Exploration Sequence
Consider a task: *"Fix timeout retry behavior when capturing payments."*

1. **Step 1 (Broad search)**: The agent runs `grep -rn "retry" .` → Returns 240 matches across 35 files.
2. **Step 2 (File reading)**: The agent picks the first match in `PaymentGateway.py` and reads the entire file (800 lines = ~2,000 tokens).
3. **Step 3 (Wrong file realization)**: The file only defines the interface. The agent greps again for `"capture"` → 85 matches.
4. **Step 4 (Second file read)**: Reads `PaymentService.py` (950 lines = ~2,400 tokens).
5. **Step 5 (Caller tracing)**: Wants to know who calls `capture()`. Greps again and reads `CheckoutService.kt` (600 lines = ~1,500 tokens).

**Total Context Consumed Before Editing:** Over **9,000 tokens** across 6 tool roundtrips, with high risk of context degradation and catastrophic forgetting.

---

## 2. The S.A.N.E. Progressive Disclosure Model

Human software engineers using modern IDEs (IntelliJ, VS Code) never read entire files to find a method. They navigate through a disciplined escalation hierarchy:

```text
Level 0: Search Concept
   │  "Where is retry logic handled?"
   ▼
Level 1: Semantic & Lexical Candidates
   │  Returns symbol names, file paths, and signatures only. (~300 tokens)
   ▼
Level 2: Structural File Skeleton
   │  All method bodies redacted. See imports, class outline, method signatures. (~400 tokens)
   ▼
Level 3: Exact Symbol Code
   │  Target method implementation only (lines 49-54). (~150 tokens)
   ▼
Level 4: AST-Aware Usage Snippets
   │  Focused call site previews with confidence scoring. (~250 tokens)
```

**Total Context Consumed:** **~1,100 tokens** (an **87% reduction**).

---

## 3. Mathematical Comparison of Token Economics

| Metric | Naive Agent (Grep + Whole Files) | S.A.N.E. Progressive Disclosure | Improvement |
|---|---|---|---|
| **Discovery Tool Calls** | 5 – 8 calls | 2 – 3 calls | **60% fewer roundtrips** |
| **Tokens Consumed** | 8,000 – 15,000 tokens | 800 – 1,800 tokens | **85% reduction** |
| **Context Window Fill** | 12% – 25% of 64k window | < 2% of 64k window | **Preserves reasoning headroom** |
| **Precision of Target** | Heuristic guesswork | 100% exact symbol | **Deterministic** |
| **API Cost Per Task** | ~$0.08 – $0.15 | ~$0.008 – $0.015 | **10x cheaper** |

---

## 4. How Redacted Skeletons Preserve Semantic Context

Unlike AST pretty-printers which strip formatting, comments, and annotations, S.A.N.E. uses byte-range redaction:

### Original Source (`PaymentService.py`):
```python
class PaymentService:
    """Core payment business logic service."""

    def __init__(self, gateway: PaymentGateway, retry_coord: PaymentRetryCoordinator):
        self.gateway = gateway
        self.retry_coord = retry_coord

    def capture(self, token: PaymentToken) -> bool:
        """Captures payment for an order and records transaction."""
        success = self.gateway.process_charge(token)
        if not success:
            self.retry_coord.should_retry(1, "TIMEOUT")
        return success
```

### Redacted Skeleton (`get_skeleton`):
```python
class PaymentService:
    """Core payment business logic service."""

    def __init__(self, gateway: PaymentGateway, retry_coord: PaymentRetryCoordinator):
        # ... implementation omitted ...

    def capture(self, token: PaymentToken) -> bool:
        """Captures payment for an order and records transaction."""
        # ... implementation omitted ...
```

The agent learns:
1. What methods exist on the class.
2. What arguments and types they accept.
3. What docstrings explain their contract.
4. Without paying tokens for the internal implementation of helper methods it doesn't need to touch.

---

## 5. Output Budget Guarantee

Every S.A.N.E. operation is governed by `OutputBudget`:
- If an agent queries `find_usages("common_helper")` and there are 1,400 call sites across the codebase, S.A.N.E. **will never dump 1,400 call sites into context**.
- It returns the top 10 most confident usages with an explicit notification:
  ```text
  ... [Showing 10 of 1400 usages. Refine query by path or request specific sub-range]
  ```
- This guarantees that an agent never suffers an accidental context blow-up.
