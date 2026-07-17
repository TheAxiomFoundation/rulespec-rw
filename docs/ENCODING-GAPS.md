# Encoding gaps

## `rw/regulations/po-2024-086-01/pension-contribution-rate.yaml`

- Literal: `0.5` (rule `pension_equal_sharing_fraction`).
- Encodes: the employee's half of the mandatory pension contribution. The
  employer and the employee each bear one half of the total rate fixed by
  Presidential Order No 086/01 of 12/12/2024; the employee contribution is
  `mandatory_pension_contribution_rate * pension_equal_sharing_fraction`.
- Provisions searched: every provision in the pinned Rwanda corpus release
  (`rw-rulespec-2026-07-16`, content
  `e78f537fa45105afa12044f4062d20df59d443b893140de852ee39963030e74a`) was
  searched for a numeric statement of the employer/employee split. Law No
  05/2015 of 30/03/2015, Article 8 (Contribution rate), states the split only
  in words — English: "The employer and the employee shall contribute equally
  to the pension scheme."; French: "cotisations au régime de pension sont
  réparties à parts égales entre l'employeur et l'employé." — which the rule's
  proof atom cites verbatim. Presidential Order No 086/01 fixes only the total
  rate (12% from 2025, rising to 20% by 2030) and states no separate employee
  share. The `50%` occurrences in Law No 05/2015 concern unrelated thresholds
  (a deferred member's accrual and a voluntary-scheme participant's holding);
  the `one half (1/2)` occurrences concern a disability earning-capacity test,
  not the contribution split.
- Judgment: the split into two equal shares is legally compelled — Article 8
  names the two contributing parties (the employer and the employee) and
  requires them to contribute equally — so `0.5` is the correct value, but it
  appears in no cited provision as a substantive numeric value. The
  path-anchored numeric-grounding check (axiom-encode#1127) therefore reports
  it as ungrounded. This is a genuine grounding gap: a split stated textually
  ("equally" / "à parts égales") rather than as a percentage or fraction. The
  encoded `0.5` is retained unchanged; the module is listed under
  `validate_failures` in `known-validation-gaps.yaml` with the fingerprint
  emitted by the supervised waiver audit, tracked in
  https://github.com/TheAxiomFoundation/rulespec-rw/pull/10.
