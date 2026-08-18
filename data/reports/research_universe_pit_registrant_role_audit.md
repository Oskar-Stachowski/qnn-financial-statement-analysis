# Final registrant-role / economic-entity audit

## Scope and invariants

The audit covers every eligible observation carrying the old combined role
`co_registrant_or_non_xbrl_registrant` and every eligible observation with
`joint_filing_flag = True`: **4,534 observations** and
**2,773 CIKs**.  The frozen PIT-B target was neither
read for analysis nor modified; its frozen artifact hash was reverified as
`473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff`.  X_t was not built.
The canonical universe was not rewritten; its evidence-bound hash is
`7ed8faf9262f91b0098681722f941b9ffe6f44f6689ed8b7e96a7759dbcb5bb7`.

The all-case screen reads the primary original 10-K and maps registrants to
distinct audited annual balance-sheet, operations/income and cash-flow suites.
XBRL context identifiers are retained as secondary provenance, but are not used
alone: several combined filings have one XBRL entity identifier and two or more
separately audited reporting entities. All 13 non-XBRL joint filings also have
explicit manual decisions in `configs/research_universe_registrant_role_manual.yaml`.
Inconclusive cases fail closed as ambiguous.

## Corrected registrant roles

All eligible observations:

| registrant_role_resolved | observations | unique_ciks | accessions |
| --- | --- | --- | --- |
| joint_co_registrant | 437 | 103 | 364 |
| joint_primary_registrant | 339 | 78 | 339 |
| single_filer_non_xbrl_registrant | 3758 | 2617 | 3758 |
| single_filer_xbrl_registrant | 60533 | 9295 | 60533 |

Observations specifically covered by this audit:

| registrant_role_resolved | observations | unique_ciks | accessions |
| --- | --- | --- | --- |
| joint_co_registrant | 437 | 103 | 364 |
| joint_primary_registrant | 339 | 78 | 339 |
| single_filer_non_xbrl_registrant | 3758 | 2617 | 3758 |

The old role was therefore not semantically usable: it combined **single-filer
non-XBRL registrants** with actual **joint-filing co-registrants**.

## Economic-entity result

| economic_entity_status | recommended_membership_action | observations |
| --- | --- | --- |
| ambiguous_reporting_scope | mark_ambiguous | 2 |
| co_registrant_sharing_same_consolidated_statements | exclude_duplicate_registrant_row | 132 |
| co_registrant_sharing_statement_of_noneligible_cik | mark_ambiguous | 4 |
| separate_reporting_entity_nonoperating_coissuer | exclude_nonoperating_issuer | 28 |
| separate_reporting_entity_with_own_statements | retain_one_economic_entity | 4368 |

Across the scoped observations, **4,396** are supported as separate
reporting entities with their own 10-K statement scope. This total comprises
**4,368**
retained observations and **28** verified nominal
finance co-issuers with their own statements but no substantive operations.
There are **132** confirmed duplicate co-registrant rows
sharing another eligible registrant's statement scope and **6**
unresolved observations. Of the ambiguous observations,
**4** point to a statement entity that is
not eligible under its own historical classification; its statements are not
relabelled using the co-registrant's SIC.

The primary-document mapper resolved 311 straightforward joint accessions.
Another **74** edge-case
accessions have explicit, accession-level primary-10-K decisions:

| manual_resolution | accessions |
| --- | --- |
| manual_two_distinct_audited_statement_scopes | 20 |
| manual_dual_listed_company_single_statement_scope | 14 |
| manual_four_distinct_audited_statement_scopes | 14 |
| manual_primary_statement_review | 11 |
| manual_three_distinct_audited_statement_scopes | 6 |
| manual_name_collision_resolved_by_xbrl_series | 5 |
| manual_name_collision_two_distinct_statement_scopes | 2 |
| manual_primary_statement_review_with_longitudinal_cik_check | 1 |
| statements_belong_to_nonregistrant_parent | 1 |

There are **776 eligible rows in 385
joint accessions**.  Of these accessions, **384** have a
resolved statement scope and **1** are ambiguous.

Statement-scope structure by accession:

| joint_scope_structure | accessions |
| --- | --- |
| multiple_distinct_statement_scopes | 266 |
| one_statement_scope | 118 |
| ambiguous | 1 |

## Can one accession generate multiple observations for one economic entity?

Yes.  The eligible-CIK multiplicity is:

| eligible_ciks_per_accession | accessions |
| --- | --- |
| 1 | 56 |
| 2 | 301 |
| 3 | 12 |
| 4 | 14 |
| 13 | 2 |

**720 eligible rows** occur in accessions that generate more
than one eligible CIK-year. Under the current `preserve_each_master_index_registrant_and_flag`
policy, all can flow into X_t as apparently independent company-years. The
audit confirms that **132 excess rows in
106
accessions** have no distinct statement scope. Those are deterministic
duplicates if the shared values are attached to every CIK. Distinct
parent/subsidiary statement scopes are not duplicates, but remain economically
linked and often overlap; splitting by CIK can still put the same group on both
sides of a model split.

## Conservative membership rule proposed

1. Split the source role into `single_filer_xbrl_registrant`,
   `single_filer_non_xbrl_registrant`, `joint_primary_registrant`, and
   `joint_co_registrant` before any feature extraction.
2. A single-filer original 10-K remains one reporting entity regardless of
   whether an XBRL instance exists.  Non-XBRL affects X_t availability, not
   universe membership.
3. For a joint filing, define an `economic_statement_scope_id` from accession,
   annual statement scope, and XBRL entity CIK.  Retain at most one row per
   scope unless distinct full annual statement scopes are positively evidenced.
4. Retain a CIK as a separate reporting entity only when its own consolidated
   annual balance sheet, income/operations statement, and cash-flow statement
   are evidenced for that accession.  A cover-page filer, guarantor, finance
   subsidiary, operating partnership, or co-registrant without its own scope is
   not an independent company-year.
5. If multiple legal CIKs represent one consolidated/DLC economic scope, keep
   one stable representative CIK and record every linked co-registrant CIK in
   provenance. Group/split later data by `economic_statement_scope_id`, never
   by CIK alone. Distinct but related scopes from joint filings must share the
   connected-component `economic_group_id` for all future splitting and
   clustered inference.
6. If the statement entity CIK is sector-excluded while a co-registrant CIK is
   superficially eligible, do not transfer the co-registrant SIC to the shared
   statements.  Mark the candidate ambiguous pending a documented economic-scope
   classification.
7. If evidence cannot distinguish shared from separate full statements, set
   membership to `ambiguous`; do not guess and do not let the row enter X_t.
8. A finance/capital name is only a review flag, never an exclusion rule. The
   audit identifies **22** such retained name-screened
   rows, but excludes only **28** observations for
   which the primary filing expressly documents a nominal co-issuer with no
   substantive operations. A separate zero-activity finance shell is not a
   duplicate, but it is outside an operating-company research population.

## Ambiguous cases

| reason | observations |
| --- | --- |
| statement_entity_is_not_an_eligible_company_year | 4 |
| statements_belong_to_nonregistrant_parent | 2 |

## Freeze gate

The canonical universe still preserves every master-index registrant and still
uses the combined source role. Before freezing, it must (a) split that role,
(b) remove the 132 confirmed duplicate rows while keeping
one stable statement-scope representative, (c) apply the issuer-substance
exclusion to the 28 verified nominal co-issuer rows,
(d) keep the 6 unresolved rows out of X_t as ambiguous, and
(e) persist `economic_statement_scope_id` and connected `economic_group_id`.
The universe audit must then be rerun. No canonical membership row has been
changed by this freeze-gate audit.

**RESEARCH UNIVERSE NOT READY TO FREEZE**
