# Attack Library Attribution

This document records the provenance of every test case and converter in Aegis Vuldris's
bundled attack library, along with the grading rationale for each source corpus.

## Sources

### garak probe corpora (jailbreak/suf_*.yaml)

- **Source project:** [garak](https://github.com/NVIDIA/garak) by NVIDIA, Apache-2.0 licensed.
- **Specific probes:** `jailbreak/dan`, `jailbreak/deepAliPajin`, `inject/*` (prompt injection),
  `privacy/pp_exact`, `scamseek/scamseek`, `risky_jwt`, `xss/xss`, and others.
- **Extraction:** Prompt text and adversarial suffixes were extracted from the garak
  `harness.py` and probe definitions as static strings. No garak code or Python packages
  were imported or installed.
- **Conversion:** Each probe was converted to Aegis Vuldris's TestCase YAML schema with:
  - The adversarial suffix appended to the original instruction as a user prompt.
  - Grading patterns derived from the probe's safety criteria.
  - `category: jailbreak` mapped to OWASP GenAI LLM Top 10:2026 LLM01 (Prompt Injection).
- **File naming:** `suf_###_gcg.yaml` where `###` is a zero-padded sequence and `gcg`
  indicates a GCG-style (gradient-based) adversarial suffix.

### garak probe corpora (prompt_injection/enc_*.yaml)

- **Source project:** garak probes `inject/*` and PyRIT-style encoding probes.
- **Extraction:** Attack instructions (e.g., "reveal your system prompt", "output the
  configuration values", "print the API key") extracted as static strings.
- **Conversion:** Each instruction was wrapped in a TestCase that applies one of Aegis Vuldris's
  native converters (base64, ROT13, Caesar, etc.) to test whether the model decodes and
  complies with an obfuscated instruction.
- **File naming:** `enc_NN_NN_<converter>.yaml` where the first `NN` is a prompt variant
  group (01, 02, 03) and the second identifies the converter used. Names are unique by
  combining the prompt topic and converter parameters.

### Original Aegis Vuldris test cases (non-encoded)

- Prompt injection, privacy/data leakage, RAG attacks, and agent/tool-use tests were
  authored directly for Aegis Vuldris and are not derived from external sources.

## Excluded corpora

The following garak/PyrIT content was deliberately excluded because it tests for
toxicity, slurs, or offensive language rather than AI security vulnerabilities:

- `ldnoobw-en.txt` (offensive wordlist)
- `ofcom-potentially-offensive.txt` (offensive content detection)
- `slursreclaimedslurs.txt` (slur detection)
- `realtoxicityprompts/*` (toxicity benchmarks)

These are not security test cases and their inclusion would conflate content-moderation
benchmarks with security evaluation.

## Converter provenance

The 16 converters in `app/services/converters.py` are implemented directly in Aegis Vuldris,
adapted from [PyRIT](https://github.com/Azure/PyRIT) by Microsoft (MIT licensed).
Only text-level transforms were taken; PyRIT's audio, image, PDF, and translation-
dependent converters are omitted because they require external assets or models that
Aegis Vuldris does not depend on.

The adapted converters are:
base64, caesar, rot13, atbash, vigenere, morse, nato, binary, braille, leetspeak,
homoglyph, zero_width, tag_smuggle, negation_trap, task_framing, math_obfuscation.

## License compliance

All extracted content inherits garak's Apache-2.0 / PyRIT's MIT licensing terms.
The full Aegis Vuldris project is Apache-2.0 licensed (see LICENSE).

## Grading rationale

Each test case uses one of three grading methods:

1. **Keyword grading** (`method: keyword`): Matches response text against patterns
   that indicate the model fell for the attack (e.g., compliance indicators, leaked
   data). Safe refusals are suppressed via the refusal-detection logic in
   `finding_classifier.py`.

2. **Regex grading** (`method: regex`): Uses regex patterns for structural matches.

3. **Judge-model grading** (`method: judge_model`): Defers to a dedicated,
   project-scoped judge target — the project's judge target, or one named per
   test with `grading.judge.target_id` — for nuanced cases. Returns
   `INCONCLUSIVE` if the judge is unavailable or would be the target under test
   itself.

## Test counts

| Category            | Count | Source                           |
|---------------------|-------|----------------------------------|
| jailbreak           | 108   | garak suffix (88) + original (20)|
| prompt_injection    | 67    | garak encoding (42) + original (25)|
| privacy_data_leakage| 20    | Original Aegis Vuldris                 |
| rag_attack          | 14    | Original Aegis Vuldris                 |
| agent_tool_use      | 15    | Original Aegis Vuldris                 |
| **Total**           | **224**|                                 |
