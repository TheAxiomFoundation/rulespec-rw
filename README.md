# rulespec-rw

Rwanda RuleSpec source registry.

This repository targets the Rwanda tax-benefit surface: employment income tax (PAYE) under Law nº 027/2022 of 20/10/2022 establishing taxes on income as amended (including the lump-sum/presumptive regime for small businesses), rental income tax under the decentralized-entities revenue law, social security contributions administered by the Rwanda Social Security Board (the pension scheme with its 2025 contribution-rate reform, occupational hazards, the maternity leave benefits scheme under Law nº 003/2016, the RAMA medical scheme, community-based health insurance, and military medical insurance), value added tax under Law nº 049/2023, excise duty under the excise duty law as amended, and the transfer programmes needed for household-level calculations (VUP Direct Support, school feeding, Girinka, and fuel subsidies). Rwanda is a unitary state; all encoded law lives under a single `rw/` national namespace.

Rwanda's income tax year is the calendar year, and PAYE is computed on monthly bands. The validation year for encoded amounts is **CY2025** (RWAMOD system RW_2025); effective dates follow each law's own commencement provision as published in the Official Gazette.

## Source priority

Policy must come from the furthest upstream available source.

1. Official Gazette of the Republic of Rwanda prints (trilingual Kinyarwanda/English/French — the English text is citable) served by the official legal portal (amategeko.gov.rw / Ministry of Justice) — the authentic text of the income tax, VAT, excise, and social-security law and their amendments. Gazette-facsimile mirrors are acceptable when the official portal does not serve the print, recorded with the host in manifest metadata.
2. Presidential, Prime Minister's, and Ministerial Orders implementing the laws (contribution rates, CBHI premium categories, lump-sum schedules) once the governing law is identified.
3. Rwanda Revenue Authority rulings and guidance only after the governing law or order is identified.
4. Ministry/agency programme documentation (LODA VUP programme documents, MINEDUC school feeding, MINAGRI Girinka, petroleum pricing instruments) for rules set administratively rather than by law or order.
5. Oracles only for household-level parity tests against an external source that can calculate the same household case, never as law.

## Oracle scope

An oracle is an executable, pinned external calculator that accepts household-level inputs and returns household-level tax-benefit outputs comparable to Axiom outputs. Aggregate simulators, distributional reports, parameter documentation, and public model summaries are not oracles for RuleSpec parity, even when they are useful as background references.

The Rwanda household oracle is **RWAMOD**, the SOUTHMOD tax-benefit microsimulation model for Rwanda (UNU-WIDER). UNU-WIDER approved access on 2026-07-07, and RWAMOD is wired by eight per-case comparison suites in [axiom-oracles](https://github.com/TheAxiomFoundation/axiom-oracles) (`comparisons/rw-*.yaml`), run on system RW_2025. The bundle ships no Rwandan microdata, so every comparison household is synthetic. The SOUTHMOD_A4.0 Adhesion Agreement bars giving the bundle to third parties, so those suites run only on the machine that holds it, never on shared CI; the committed reports are the record. `data/oracles/oracle-index.json` pins the bundle hash and lists each suite with the outputs it compares.

## Listing gates

This repo carries `app_visibility = "experimental"` in `.axiom/registry.toml` and stays out of app surfaces until:

1. The encoded surface covers the flagship calculation (employment income tax gross-to-net for a formal employee) end to end with companion tests.
2. Oracle parity suites exist and pass against RWAMOD for the encoded surface. Status: **partially met**. Eight RWAMOD suites ran on 2026-10-04 against rulespec-rw 001fa4b, and all 64 comparisons over 42 synthetic cases match within the suites' 1-FRW tolerance (see `data/oracles/oracle-index.json`). Not all of that is independent validation: rw-vat and the cigarette row of rw-excise feed RWAMOD's own expenditure base to the modules, so they test rates, not the base; rw-cbhi-tiers runs the Axiom side at 2027 against RW_2025, so it checks the schedule amounts, not CY2025 law; and rw-dispy's levy comparison tests the composed pipeline's own copy of the CBHI levy rate, not the PM Order No 105/03 module. The compared modules are not supervised-encoder output: this repo has no encoding manifests ([rulespec-rw#18](https://github.com/TheAxiomFoundation/rulespec-rw/issues/18)). Not every module has a comparison: the PM Order No 105/03 CBHI employee contribution, the Law No 03/2015 CBHI module and the VUP Direct Support amounts have none.
3. Citation paths are stable (law-number form against the Official Gazette prints).
