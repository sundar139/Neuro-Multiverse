# Protocol Deviation Log

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

Any departure from a locked decision in the scientific protocol must be recorded here before or at the time it takes effect. An undocumented departure invalidates the affected result.

---

## 1. Current state

**No scientific deviations are currently recorded. The scientific decisions stand as locked on 2026-07-17.**

No predictive metric, quality-control result, or other research outcome has been produced or inspected. This does not prevent a protocol deviation from occurring: any future departure from a locked decision must still be recorded before it takes effect where possible, regardless of whether outcomes have been inspected.

A deviation may therefore arise at either point in the study. A departure decided before any outcome is inspected is recorded and remains preregistered. A departure decided after outcome inspection is equally recordable, but it is no longer preregistered and is reported as such. In both cases the entry must disclose whether outcomes had already been viewed, per Section 2.

---

## 2. Recording rules

- One entry per deviation. Entries are appended and never edited after approval; a correction is a new entry that references the prior identifier.
- Identifiers are assigned sequentially as `DEV-0001`, `DEV-0002`, and so on.
- The entry must be recorded before the deviation takes effect where that is possible, and immediately afterward where it is not.
- The disclosure of whether outcomes had already been inspected is mandatory and determines how the affected results are interpreted. A change made after outcome inspection is not invalid, but it is no longer preregistered, and the final report must describe it as such.
- Every deviation entry must be referenced in the final manuscript.

---

## 3. Entry template

Copy the block below for each new deviation and complete every field. A field that does not apply is answered with "Not applicable" and a reason, never left blank.

```markdown
### DEV-XXXX — <short title>

- **Identifier:** DEV-XXXX
- **Date:** YYYY-MM-DD
- **Author:** <name>
- **Original protocol decision:** <the locked decision, quoted, with its protocol section>
- **Revised decision:** <the new decision, stated precisely enough to implement>
- **Reason:** <why the original decision could not stand>
- **Evidence available at the time:** <what was known when the change was made>
- **Had any predictive or quality-control outcome been inspected?** <Yes / No, and if yes, exactly which outcomes and by whom>
- **Datasets affected:** <list>
- **Analyses affected:** <research questions, estimands, and analyses>
- **Expected consequence:** <effect on estimates, uncertainty, interpretation, and scope>
- **Approval status:** <Proposed / Approved / Rejected, with approver and date>
- **Related commit:** <commit hash implementing the change>
- **Corrective or sensitivity analysis:** <what will be run to bound the impact of the change, or why none is required>
```

---

## 4. Deviation index

| Identifier | Date | Title | Outcomes inspected before change | Approval status |
| --- | --- | --- | --- | --- |
| None recorded | Not applicable | Not applicable | Not applicable | Not applicable |

---

## 5. Recorded deviations

None.
