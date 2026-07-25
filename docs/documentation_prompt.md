# Prompt: Write Documentation Using the Hybrid Markdown Approach

You are writing documentation for a feature, module, or subsystem inside this repository.
Use the **Hybrid Markdown Format**, which combines:

1. **Human-friendly Markdown links for navigation**
2. **Machine-parsable `code-ref` blocks for AI agents**

Write concise, accurate, technical documentation.

---

## 📌 REQUIRED DOCUMENT STRUCTURE

Follow this structure exactly:

---

# Feature: <Feature Name>
A short summary (2–4 sentences) describing:
- what the feature does
- why it exists
- the high-level workflow

---

## Human-Friendly Code Map
List Markdown links to relevant files for keyboard navigation.

Format:

```md
- [Name of component](./path/to/file.py)
- [Another component](./path/to/another_file.py)


Rules:

Use relative paths only.

Keep descriptions short.

### Detailed Flow Explanation

Explain the feature step-by-step using numbered lists.
Describe the data flow, transformations, and component roles.

Example:
```1. Request enters API route.
2. Payload is validated.
3. Domain handler transforms data.
4. Repository persists the record.
```

### Code References (Machine-Readable)

Provide a code-ref block for each key function/class.

Format (must be exact):
```
file: src/path/to/file.py
symbol: function_or_class_name
feature: <feature_name>
description: >
  One–two sentence factual description of what this symbol does.
```
Rules:

No Markdown links inside code-ref blocks.

Use actual symbol names from the codebase.

Keep descriptions short and factual.


### Edge Cases

List important failure modes, validation failures, retries, or special handling.

Example:

Missing fields → validation error

Database failure → retry or propagate

Invalid enum → rejected input


### Final Rule

Always use both Markdown links (for humans) and code-ref blocks (for agents).
Do not include anything outside this defined structure.

Now produce the documentation.