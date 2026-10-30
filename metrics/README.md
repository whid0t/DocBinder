# Scenario metric results

Evidence date: **2026-10-30**. Results apply to the supplied Maria Beispiel laboratory and rehabilitation scenario, not all additional resources on the running FHIR server.

| Metric | Target | Result | Evidence |
|---|---|---|---|
| HL7 FHIR validation | 0 errors | **PASS: 0 errors**, 8 resources | [Validator output](validator-output.txt), [validated JSON](fhir/) |
| Misdeliveries | 3/3 | **PASS: 3/3 under the hackathon assumptions** | [Run log](run-log.json), [audit records](audit/) |
| Audit coverage | 6/6 | **PASS: 6/6** with actor, event and timestamp | [Audit records](audit/), [recheck](recheck-2026-10-30.md) |
| Outside-person effort | 0 installs, 0 accounts, under 2 min | **0 installs, 0 accounts; human timing pending** | Browser workflow; no first-time-user timing record yet |

## FHIR validation: passed

The retained official HL7 validator 7.0.3 output against FHIR R4 4.0.1 reports zero errors on one Patient, four Observations, two Provenance resources and one DocumentReference. There are eight `dom-6` missing-narrative warnings; these are best-practice warnings, not errors.

To repeat from the repository root, place the official `validator_cli.jar` there and run:

```bash
./scripts/validate-fhir.sh metrics/fhir/*.json
```

The documentation recheck reviewed the retained validator output and reran seven FHIR-related regression tests: **7 passed, 3 deselected**. It did not execute a new HL7 validation run. Full command and scope: [recheck record](recheck-2026-10-30.md).

## Misdeliveries: passed

The challenge allows simulated electronic ID. This assessment treats the entered name as an eID-provided identity and assumes clinic APIs are available only in the trusted clinic environment.

| Scenario | Recorded outcome | Assessment |
|---|---|---|
| M1: wrong address | Different simulated identity rejected with HTTP 403 and audit event | **PASS under these assumptions** |
| M2: forwarded request | Colleague's simulated identity rejected with HTTP 403 and audit event | **PASS under these assumptions** |
| M3: wrong patient | HTTP 409, zero filed resources, mismatch notice in Matrix | **PASS** |

The raw run log also records acceptance when someone types the expected person's name and unauthenticated API exposure. Those limitations are outside this scoped demo assessment. The result does not certify real identity proof or production access controls. No new execution was performed when applying the agreed hackathon assumptions.

## Audit coverage: passed

All six required event types are present with nonempty actor and timestamp fields: `request_sent`, `link_opened`, `identity_checked`, `answer_sent`, `answer_filed`, and `misdelivery_caught`. Failed identity checks record the claimed identity.

## Outside-person effort: timing pending

The external workflow needs no installation or new account. The recorded 0.18-second scripted submission is not a human usability measurement. To complete this metric, time someone new from opening the request-1 email to sending the answer, and record the duration plus installs/accounts required here.

## Where to inspect the evidence

- [run-log.json](run-log.json): scenario request IDs, HTTP outcomes, Matrix notices and resource count.
- [validator-output.txt](validator-output.txt): official validation result for each of the eight resources.
- [fhir/](fhir/): exact exported scenario resources.
- [audit/](audit/): per-request events with actors and timestamps.
- [Email invitation](invitation-email-request1.txt) and [SMS invitation](invitation-sms-request2.txt): recorded invitation text.
- [Recheck record](recheck-2026-10-30.md): regression test command and audit counts.

In the running app, open **http://localhost:3000**, select a request, and inspect its FHIR resources and audit timeline. Request IDs for the measured scenarios are listed in the run log.
