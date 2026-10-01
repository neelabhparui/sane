# Symbol Resolution & The S.A.N.E. Semantic Graph

## 1. The Core Insight: Occurrences vs. Edges

Most source-navigation tools make a fundamental architectural error: they immediately convert every syntactic identifier into a definitive graph edge (`Symbol A -> calls -> Symbol B`).

In dynamic and multi-paradigm languages (Python, Kotlin, Java), Tree-sitter and AST parsers can only detect **syntactic occurrences**, not compiler-verified type bindings:
```kotlin
val result = paymentProcessor.capture(token, total)
```
At the parser level, we only know:
- An identifier `capture` was called.
- The receiver variable was named `paymentProcessor`.
- The call occurred inside `CheckoutService.submitOrder()`.

Declaring that this definitively calls `com.acme.billing.PaymentProcessor.capture()` without type analysis can create false graph edges.

S.A.N.E. solves this by introducing a **two-phase resolution pipeline**:
1. **Phase 1 (Parse-time)**: Store the reference as an `occurrence`.
2. **Phase 2 (Resolution-time)**: Attempt conservative resolution, categorizing the relationship with an explicit **resolution kind** and **confidence score**.

---

## 2. Multi-Stage Resolution Pipeline

```text
               Unresolved Occurrence (spelling, receiver, enclosing)
                                      │
                 Is target declared in the same local/class scope?
                                    ┌─┴─┐
                               Yes ┌┘   └┐ No
                                   ▼     ▼
               [class-scoped, conf=0.95]  Does receiver match imported type?
                                              ┌─┴─┐
                                         Yes ┌┘   └┐ No
                                             ▼     ▼
                         [import-scoped, conf=0.90]  Is there exactly one global candidate?
                                                        ┌─┴─┐
                                                   Yes ┌┘   └┐ No (Multiple or None)
                                                       ▼     ▼
                                  [probable, conf=0.80]     [ambiguous / unresolved]
```

### Resolution Categories & Confidence Scoring

| Resolution Kind | Confidence | Criteria |
|---|---|---|
| `exact` | **0.98** | Definition and reference are verified in same local function scope or explicit type-safe binding. |
| `class-scoped` | **0.95** | Reference matches a method on the enclosing class or companion object. |
| `import-scoped` | **0.90** | Receiver type or explicit import statement matches the declaring namespace. |
| `probable` | **0.80** | Exactly one symbol with the matching name exists across the entire indexed codebase. |
| `ambiguous` | **0.45** | Multiple candidates exist with identical short names; resolved with candidate list. |
| `unresolved` | **0.00** | External library, standard library, or unresolvable dynamic invocation. |

---

## 3. The Future SCIP Integration Path

For projects requiring 100% compiler-verified definitions, implementations, and call graphs, S.A.N.E. includes an extension bridge for **SCIP (Source Code Intelligence Protocol)**.

Existing compiler indexers (such as `scip-java`, `scip-python`, and `scip-typescript`) emit precise `.scip` protobuf indices. S.A.N.E.'s storage schema (`occurrences` and `edges`) is directly isomorphic to SCIP's occurrence model:

```text
SCIP Indexer (javac / pyright)
          ↓
     index.scip
          ↓ [scip_ingest]
S.A.N.E. SQLite DB (occurrences + edges with exact compiler confidence)
```

This allows S.A.N.E. to remain lightweight and zero-setup by default with Tree-sitter/AST heuristics, while accepting compiler-grade precision when a SCIP file is provided.
