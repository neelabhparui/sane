# Language Adapters in S.A.N.E.

## 1. The Language Adapter Protocol

Every language supported by S.A.N.E. implements the `LanguageAdapter` protocol defined in `sane_nav.parsing.base`:

```python
class LanguageAdapter(Protocol):
    language: str

    def supports(self, path: str) -> bool:
        """Determines if the adapter can parse the specified file extension."""
        ...

    def parse(self, path: str, source: bytes) -> ParsedFile:
        """Extracts symbols, references, docstrings, and occurrence ranges."""
        ...

    def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
        """Redacts implementation bodies from source bytes byte-for-byte."""
        ...
```

The parsed output is normalized into a language-agnostic intermediate representation (`ParsedFile`, `ParsedSymbol`, `ParsedReference`, `ParsedDocumentSection`).

---

## 2. Implemented Adapters

### 2.1 Python (`sane_nav.parsing.python`)
- **Parser Backend**: Python's native `ast` module.
- **Supported Constructs**:
  - Class declarations with base classes.
  - Sync and `async` function definitions.
  - Class methods, static methods, and properties.
  - Decorators (`@dataclass`, `@retry`, `@property`).
  - Function and class docstrings (`"""..."""`).
  - Function calls with receiver attributes (`gateway.process_charge()`).
- **Skeleton Redaction**: Identifies start/end byte offsets of function bodies, preserving docstring lines, and replacing body statements with `# ... implementation omitted ...`.

### 2.2 Java (`sane_nav.parsing.java`)
- **Supported Constructs**:
  - Package declarations (`package com.acme.auth;`).
  - Classes, interfaces, records, and enums.
  - Method declarations with annotations (`@Transactional`, `@Override`).
  - Javadoc comments (`/** ... */`).
  - Call sites (`paymentProcessor.capture()`).
- **Skeleton Redaction**: Preserves class signatures, annotations, and Javadocs while replacing method bodies `{ ... }` with `{\n        // ... implementation omitted ...\n    }`.

### 2.3 Kotlin (`sane_nav.parsing.kotlin`)
- **Supported Constructs**:
  - Package and import statements.
  - Data classes, sealed classes, value classes, objects, and companion objects.
  - `fun`, `suspend fun`, and extension functions (`fun String.foo()`).
  - KDoc documentation comments (`/** ... */`).
  - Call sites with receiver text.
- **Skeleton Redaction**: Preserves modifiers, annotations, and return types while redacting function bodies with `// … implementation omitted …`.

### 2.4 Markdown (`sane_nav.parsing.markdown`)
- **Structural Heading Stack**: Parses `#`, `##`, `###` headings and tracks full ancestor paths:
  ```text
  System Architecture
  System Architecture > Authentication
  System Architecture > Authentication > Refresh tokens
  ```
- **Direct Section Chunking**: Unlike naive chunkers that duplicate entire ancestor documents, S.A.N.E. associates only the direct text between headings with each section node.
- **Doc-to-Code Mention Extraction**: Scans documentation prose for references to CamelCase identifiers, creating semantic bridges between documentation and code symbols.

---

## 3. How to Add a New Language Adapter

To add support for a new language (e.g. TypeScript or Go):

1. **Create Adapter File**: Create `src/sane_nav/parsing/typescript.py`.
2. **Implement Protocol**:
   ```python
   class TypeScriptAdapter:
       language = "typescript"

       def supports(self, path: str) -> bool:
           return path.endswith(".ts") or path.endswith(".tsx")

       def parse(self, path: str, source: bytes) -> ParsedFile:
           # Extract interfaces, classes, functions, calls
           ...

       def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
           # Redact function and method bodies
           ...
   ```
3. **Register in `ParserRegistry`**: Add `TypeScriptAdapter()` to `self.adapters` in `src/sane_nav/parsing/registry.py`.
4. **Update File Inclusions**: Add `"**/*.ts"`, `"**/*.tsx"` to `include` in `src/sane_nav/config.py`.
5. **Add Fixtures & Tests**: Add test fixtures under `tests/fixtures/` and add test cases to `tests/test_sane.py`.
