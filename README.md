# DocBinder

DocBinder is a clinic-controlled hackathon prototype for requesting clinical documents from professionals outside a Matrix network, checking the returned patient, converting the answer to FHIR R4, and notifying the doctor.

The 90-second demo story is:

1. Dr. Lena Hofer creates a structured request in DocBinder or sends one copyable block to the Matrix bot.
2. The patient receives a simulated notification; the external professional receives a privacy-safe email or simulated SMS link.
3. The external professional types their name in the clearly labeled **Simulated ID Austria — name matching** screen and uploads one to three Markdown documents.
4. DocBinder checks the patient and batch, files the generated resources in HAPI FHIR, and shows the doctor source documents, FHIR JSON, audit history, and a deterministic LOINC timeline.

All data is synthetic. This is not a production security design.

## Components

- **DocBinder React app** — doctor dashboard, request details, invitation portal, and SMS simulator.
- **FastAPI + SQLite** — request state, hashed invitation tokens, name matching, parsing, FHIR generation, audit events, and notification queues.
- **DocBinder Matrix bot** — one-message request creation from Element Web.
- **Synapse + Element Web** — the internal doctor communication channel.
- **Mailpit** — local invitation email delivery.
- **HAPI FHIR** — FHIR R4 Patient, Observation, DocumentReference, and Provenance storage.

## Quick start

Requirements: Docker Desktop with Docker Compose. Java is only needed for the optional standalone HL7 validator.

```bash
cd TRACK-2-interoperability
cp .env.example .env
./scripts/matrix-init.sh
docker compose up -d --build
```

HAPI can take a minute or two on first start. Wait for `http://localhost:8081/fhir/metadata`, then create the two local Matrix accounts:

```bash
./scripts/matrix-create-users.sh
```

| Service | URL |
|---|---|
| DocBinder | http://localhost:3000 |
| Element Web | http://localhost:8080 |
| Mailpit | http://localhost:8025 |
| FastAPI docs | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8081/fhir |

Default synthetic doctor login:

```text
Matrix user: @lena.hofer:klinikum.example
Password: docbinder-doctor-demo
```

Change these credentials if the environment is reachable by anyone else.

## Matrix demo

1. Sign in to Element as `@lena.hofer:klinikum.example`.
2. Create a private, unencrypted room and invite `@docbinder:klinikum.example`.
3. Send `!request-document`.
4. Copy either example, edit any synthetic patient or recipient values, and send the complete key-value block once.
5. Review the bot summary and reply `confirm`.

`!help` shows both laboratory and rehabilitation examples. `!requests` lists recent requests, `!revoke DBR-...` revokes an active request, and `!cancel` drops an unfinished draft.

The doctor can also create the same request directly in DocBinder. Both interfaces require a structured document type, one of the three demo purpose/legal-basis values, and a separate reason.

## External-professional demo

For a laboratory request:

1. Open the Mailpit invitation to `eva.brandl@labor-kanal.example`.
2. Open its secure link. Before verification, it exposes only the request reference.
3. Enter `Eva Brandl`, `Dr Eva Brandl`, or `Dr. Eva Brandl`. The field is initially empty and no expected identity is suggested.
4. Upload `scenario/documents/lab-result-maria-beispiel.md`, or paste it.
5. Submit the batch. DocBinder produces four Observations and one Provenance for that source document.

For rehabilitation, use the dashboard shortcut for Stefan Kern, open the external invitation in **SMS simulator**, enter `Stefan Kern`, and upload `scenario/documents/rehab-report-maria-beispiel.md`.

The invitation accepts one to three UTF-8 `.md` documents, with a combined 3 MiB limit. Every document must match the patient and requested structured document type. The batch is filed atomically and the invitation is consumed only after successful filing. Duplicate content within a batch is rejected.

## Doctor request details

Select any row in **Requests**. `/requests/{request-id}` shows:

- patient, recipient, purpose/legal basis, reason, and status;
- a deterministic timeline grouped from stored FHIR Observations by LOINC and clinical date;
- each preserved Markdown source with filename and hash;
- generated FHIR JSON and direct HAPI URLs;
- a chronological audit timeline.

The summary is deterministic and contains no diagnosis, recommendation, alert, or AI interpretation. Consistent units are assumed for the demo and enforced within a submitted batch.

Equivalent API endpoints are:

```text
GET http://localhost:8000/api/requests/{request-id}/detail
GET http://localhost:8000/api/requests/{request-id}/summary
GET http://localhost:8000/api/requests/{request-id}/fhir
GET http://localhost:8000/api/requests/{request-id}/audit
```

## Patient notification

The SMS simulator displays:

```text
Klinikum Beispielstadt (Dr. Lena Hofer) initiated healthcare document request DBR-…. REPLY WITH 1 TO ACCEPT, 0 TO DECLINE. If an answer is NOT RECEIVED in 6 hours, you will receive a call to confirm.
```

This is visible demo copy only. Replies, approval state, the six-hour timer, and a real call are storyboarded future integrations. The prototype does not claim this message proves patient consent and it does not gate the invitation.

## Identity and misdelivery behavior

The simulated identity step normalizes Unicode, case, whitespace, and an optional leading `Dr`/`Dr.` before exact name equality. It does not use fuzzy matching, partial names, the contact address, or a browser-selected identity ID. Five failed attempts lock the invitation. This low-overhead name match is explicitly **not real ID Austria authentication**.

Misdelivery demos:

- **Wrong or forwarded recipient:** type a different name. Patient and request details remain hidden, and `identity_checked` plus `misdelivery_caught` are audited.
- **Repeated attempts:** five incorrect names lock the invitation and notify the doctor.
- **Wrong patient:** verify correctly, then upload `lab-result-max-beispiel.md`. DocBinder rejects it before FHIR filing and notifies the doctor.
- **Invitation privacy:** inspect the email/SMS before verification; it contains no patient, birth date, reason, or document type.

## FHIR behavior

- A new synthetic patient ID creates a minimal Patient. An existing ID must have the same name and birth date; conflicting demographics are blocked instead of overwritten.
- Laboratory documents produce LOINC-coded Observations with `effectiveDateTime`, optional `issued`, performer, value, display unit, UCUM code, and a source-specific Provenance.
- Rehabilitation documents produce a DocumentReference containing the Markdown and a source-specific Provenance.
- All resources in a submission are sent to HAPI in one transaction Bundle.
- Malformed table rows, impossible dates, non-finite values, missing sample times, unsupported document types, and patient mismatches return controlled errors.

## Tests

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=matrix-bot python3 -m pytest -q matrix-bot/tests
docker compose config --quiet
```

With the stack running:

```bash
docker compose exec -T backend python tests/integration_smoke.py
docker compose exec -T backend python tests/matrix_smoke.py
```

For formal validation, obtain the official `validator_cli.jar`, export the resources, and run:

```bash
./scripts/validate-fhir.sh path/to/resource.json
```

## Supplied example dataset

`example-data/` contains ten synthetic patients with two laboratory dates each, plus extraction and trend ground truth. With the stack running, load all twenty reports through the normal invitation, verification, parsing, FHIR, and audit workflow:

```bash
python3 scripts/seed-example-data.py
```

The loader is idempotent for already-filed example patients. It supports the dataset's ISO headers, explicit missing results, and deterministic glucose/creatinine unit normalization while retaining the source value in the Observation notes.

## Design answers

### How does an outside person prove who they are?

For this demo, the external professional types their name in a simulated ID Austria screen. The server compares it with the named recipient and only then creates a verification session. It is deliberately labeled as name matching, not strong authentication. A production adapter would replace it with a server-verifiable eID assertion.

### Which identity check is required and why?

Both supported document types use the same name-match simulation because both contain health data and need an attributed submitter. This keeps the external demo account-free while making the security assumption visible.

### Which FHIR resources are created?

Laboratory rows become Observations referencing the Patient; rehabilitation text becomes a DocumentReference referencing the Patient. Every source document gets a distinct Provenance linking its generated resources to the verified submitter and original author where available.

### How is a misdelivery noticed?

The invitation reveals no clinical detail before name matching. Wrong names are blocked and audited, repeated failures lock the link, and document patient name/date are checked before conversion and storage.

### Where does the service run?

The prototype is a clinic-controlled Docker Compose deployment. External professionals access only the invitation portal. Matrix, email, SMS, identity, and FHIR services are adapter boundaries; the demo uses Synapse, Mailpit, an in-app SMS outbox, simulated name matching, and HAPI FHIR.

## Accepted prototype limitations

- The doctor is assumed to already be logged in to both DocBinder and Element. The internal dashboard, request APIs, audit APIs, notification outboxes, and revocation route are not authenticated in code. Keep the stack on a trusted local machine and do not claim an enforced internal access boundary.
- Invitation links do not expire; they are hashed, revocable, single-use after successful filing, and locked after five failed name attempts.
- Matrix rooms are intentionally unencrypted for this local demo.
- No real ID Austria, SMS, patient approval, email provider, OCR, PDFs, AI extraction, terminology lookup, or production retry reconciliation is included.
- Pre-rename `CBR-...` request rows remain readable. New requests use `DBR-...`. The database migration copies the legacy database once into the DocBinder filename.
