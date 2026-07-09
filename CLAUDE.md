# rulespec-rw Agent Notes

This repo stores Rwanda RuleSpec source registry materials, oracle references, and encoded policy rules. Rwanda is a unitary state, so all encoded law lives under a single `rw/` national namespace.

## Scope

- `rw/statutes/`: Rwandan laws — Law nº 027/2022 of 20/10/2022 establishing taxes on income as amended (employment income bands, the lump-sum/presumptive regime), the decentralized-entities revenue law (rental income tax), the pension scheme law, the maternity leave benefits scheme law (nº 003/2016), the VAT law (nº 049/2023), the excise duty law as amended, and other primary law needed for tax-benefit modeling.
- `rw/regulations/`: Presidential, Prime Minister's, and Ministerial Orders made under the laws (contribution-rate orders, CBHI premium category orders, lump-sum schedules).
- `rw/policies/`: RRA rulings captured as verified reproductions where a gazette print is not digitized, and social-protection programme rules (VUP Direct Support, school feeding, Girinka, fuel subsidies) set administratively by LODA/MINEDUC/MINAGRI.
- `programs/`: declarative compose specs (one per jurisdiction/program/period).
- `data/coverage/`, `data/oracles/`: coverage backlog and comparison references. These are never legal authority.

## Do

- Start from the furthest upstream source: Official Gazette prints (trilingual Kinyarwanda/English/French — the English text is citable; amategeko.gov.rw and the Ministry of Justice portal serve gazette PDFs, with gazette-facsimile mirrors acceptable when the portal does not, recorded with the host in manifest metadata), implementing Orders next, RRA guidance and programme manuals only after the governing instrument is identified.
- Add RuleSpec under `rw/statutes/`, `rw/regulations/`, or `rw/policies/` with companion `.test.yaml` files.
- Cite corpus paths from modules via `module.source_verification.corpus_citation_path` (or `corpus_citation_paths`).
- Use CY2025 as the validation year (Rwanda's income tax year is the calendar year; RWAMOD system RW_2025 corresponds to it, carrying the amended Law 027/2022 monthly PAYE schedule and the 2025 pension contribution rates). Indexed/annual values must be corpus-grounded, never invented.
- Keep exact oracle versions in `data/oracles/oracle-index.json`. The RWAMOD bundle (SOUTHMOD A4.0) is licensed and non-redistributable — never commit bundle bytes, dataset rows, or model XML; only comparison statistics and RWAMOD-produced values may be recorded.
- Sync `axiom-encode` and `.axiom/toolchain.toml` before substantial encoding runs (fetch origin and read the current version before every encode run and before choosing any version-bump number).

## Do Not

- Use RRA calculators, PAYE ready-reckoners, or third-party tax alerts as the first legal source when a law or order governs the rule.
- Invent, round, or interpolate any Rwandan monetary amount, rate band, or threshold. Every number must come verbatim from a captured official provision.
- Migrate RWAMOD, EUROMOD/SOUTHMOD, or agency calculator code mechanically as RuleSpec.
- Add generated source payload dumps, formula artifacts, `parameters.yaml`, or standalone YAML fixtures outside allowed RuleSpec roots.
- Hand-copy law text into RuleSpec without a corpus `citation_path`.
