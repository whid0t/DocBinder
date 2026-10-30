# Track 2: Health Data Interoperability

Austrian doctors are piloting PGK, a closed document network built on Matrix. Patients, labs and rehab clinics outside the network are still reached by fax or unencrypted email and their results come back as scans that someone types in by hand.

## What to build

A service that lets a doctor in the network request a document from someone outside it and files the answer as FHIR R4.

1. Dr. Lena Hofer requests the document from her Matrix room, through a bot or a widget.
2. The outside person gets a link by email or SMS, proves who they are and answers in the browser. They need no account and install nothing. You can simulate an electronic ID such as ID Austria.
3. Your service turns the answer into FHIR resources plus a Provenance resource: who sent it, when and how their identity was checked.
4. It stores the resources on a FHIR server and tells Dr. Hofer in Matrix.

Also:

- Lab values become Observations with their LOINC codes. The rehab report can be a DocumentReference with the text attached.
- Write an audit entry at each of the six steps listed under Metrics.
- Catch misdeliveries, such as a request sent to the wrong address.
- Emails and SMS must not contain the patient's name, birth date or the type of document.
- You may use commercial products, FTAPI's included, as long as each one could be replaced by another.

You do not need your own Matrix app or end-to-end encryption. Element Web and an upload over HTTPS are enough.

## What you get

- `scenario/README.md`: the people, the two requests (lab result by email, rehab report by SMS) and suggested tools.
- `scenario/patient.json`: the patient, Maria Beispiel, as a FHIR Patient.
- `scenario/documents/`: the answers as Markdown, plus a lab result for a different patient.
- `scenario/misdelivery.md`: three misdelivery tests.

There is no starter code.

## Metrics

Measure these on the scenario. The jury also tests with other outside people and documents in the same Markdown format, some of them for the wrong patient.

| Metric | How to measure | Target |
|---|---|---|
| FHIR validation | Errors from the HL7 validator on every resource you file (command in `scenario/README.md`) | 0 |
| Effort for the outside person | Someone new answers request 1. Count the installs and accounts they need and the time from opening the email to sending | 0, 0, under 2 min |
| Misdeliveries caught | The three tests in `scenario/misdelivery.md`, run on request 1 | 3 of 3 |
| Audit coverage | Steps logged with who, what and when: request sent, link opened, identity checked, answer sent, answer filed, misdelivery caught | 6 of 6 |

## Your design

Answer these in your repository README:

1. How does an outside person prove who they are if they are in no directory?
2. Which identity check do you require for each type of document and why?
3. Which FHIR resources do you create and how do they reference each other and the patient?
4. How do you notice a misdelivery?
5. Where does your service run: at the clinic, at the outside organisation or at a third party?

## Rules

Use only synthetic data.

## Judging

| Criterion | Weight | Question |
|---|---|---|
| Clinical approach and impact | 33.3% | Would a lab, rehab clinic or patient answer this way? Could a clinic run it? |
| Technical quality and AI | 33.3% | Is the FHIR data valid and useful? Is the identity check strong enough without burdening the outside person? If you use AI, is its output correct? |
| Execution and prototype | 33.3% | Does the whole flow work, on this scenario and on new documents? |

The jury scores each criterion from 1 to 10 and takes your metric results into account.

## Submission

1. A video of up to 2 minutes showing your demo. Say what works and what does not.
2. A link to your public repository with instructions to run it and your design answers. Its README has to explain your technical architecture: which components you built, how they work together and which models or services you use.
3. Your metric results on this scenario.

---

## CareBridge prototype

This repository now contains a runnable end-to-end prototype:

- **Element Web + Synapse** for Dr. Hofer's internal workflow.
- **Python Matrix bot** with a guided `!request-document` conversation.
- **FastAPI + SQLite** for request state, hashed invitations, identity checks, audit events and notifications.
- **React portal** for simulated ID Austria verification and Markdown upload/paste.
- **Mailpit** for external email and an in-app SMS outbox for external and patient messages.
- **Deterministic Markdown parsing** for the supplied lab and rehabilitation reports.
- **FHIR R4 generation** and transaction filing into HAPI FHIR.

Only synthetic scenario data is supported. This is a local hackathon prototype, not a production deployment.

## Quick start

Requirements: Docker Desktop with Docker Compose. Java is needed only for the optional standalone HL7 validator.

```bash
cd TRACK-2-interoperability
cp .env.example .env
./scripts/matrix-init.sh
docker compose up -d --build
```

HAPI FHIR can take a minute or two to become ready on its first start. Inspect the stack with:

```bash
docker compose ps
docker compose logs -f backend hapi-fhir
```

Create the two local Matrix accounts after Synapse is running:

```bash
./scripts/matrix-create-users.sh
```

The bot retries login while the accounts are being created, so no manual bot restart is normally required.

Open the services:

| Service | URL |
|---|---|
| CareBridge portal/dashboard | http://localhost:3000 |
| Element Web | http://localhost:8080 |
| Mailpit | http://localhost:8025 |
| FastAPI documentation | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8081/fhir |
| Synapse client API | http://localhost:8008 |

The default synthetic credentials from `.env.example` are:

```text
Matrix user: @lena.hofer:klinikum.example
Password: carebridge-doctor-demo
```

Change these values if the environment will be accessible to anyone else.

### Element and bot demo

1. Sign in to Element as `@lena.hofer:klinikum.example`.
2. Create a private **unencrypted** room. Encryption is intentionally out of scope for this local challenge.
3. Invite `@carebridge:klinikum.example`.
4. Send `!request-document`.
5. Follow the prompts and reply `confirm` after the summary.
6. Use `!requests` to show recent workflow state or `!revoke CBR-...` to revoke an active request.

Element reserves slash commands, so the demo uses `!request-document`, although the bot also accepts `/request-document` if another client sends it literally.

### External professional demo

For the laboratory flow:

1. Create Eva's request in Matrix or on the CareBridge dashboard.
2. Open Mailpit and select the invitation sent to `eva.brandl@labor-kanal.example`.
3. Open its secure link.
4. Choose the simulated identity **Dr. Eva Brandl**.
5. Upload `scenario/documents/lab-result-maria-beispiel.md` or paste its content.
6. Submit. CareBridge checks the patient, creates four Observations plus Provenance, files them in HAPI FHIR and queues the Matrix success notification.

For the rehabilitation flow, choose Stefan Kern, obtain the invitation from the dashboard's **SMS outbox**, verify as Stefan and upload `rehab-report-maria-beispiel.md`.

The SMS outbox also shows Maria's informational patient notice separately from the external invitation. That notice is not presented as consent or approval.

## Misdelivery demo

- **Wrong/forwarded recipient:** choose the “Colleague” identity. The request stays hidden and a `misdelivery_caught` audit event is written. Five failed checks lock the invitation and notify Dr. Hofer.
- **Wrong patient:** verify as Eva but upload `lab-result-max-beispiel.md`. CareBridge rejects it before FHIR storage and notifies Dr. Hofer.
- **Invitation privacy:** inspect the Mailpit or SMS message before verification. It includes only a request reference and generic action link—not the patient, birth date, reason or document type.

View audit events and generated resources through the API:

```text
GET http://localhost:8000/api/requests/{request-id}/audit
GET http://localhost:8000/api/requests/{request-id}/fhir
```

## Tests

The core tests intentionally use only the Python standard library and pytest, so they run before container dependencies are installed:

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=matrix-bot python3 -m pytest -q matrix-bot/tests
docker compose config --quiet
```

With the Compose stack running, the live API/FHIR and Matrix smoke scripts are:

```bash
docker compose exec -T backend python tests/integration_smoke.py
docker compose exec -T backend python tests/matrix_smoke.py
```

The first script files Maria's lab result and verifies rejection of Max's wrong-patient report. The second creates a private Matrix demo room, invites the bot and checks its `!help` reply. The Matrix script uses the default synthetic password from `.env.example`; update it if you change that credential.

For formal HL7 FHIR R4 validation, place the official `validator_cli.jar` in the repository root, export API resources as individual JSON files and run:

```bash
./scripts/validate-fhir.sh path/to/resource.json
```

## Architecture and design answers

### 1. How does an outside person prove who they are?

The invitation reveals no clinical details. The recipient first completes a simulated ID Austria flow that returns an immutable synthetic subject identifier. FastAPI compares that identifier with the named recipient stored on the request. The browser cannot decide the match. A failed match reveals neither the expected person nor the patient.

### 2. Which identity check is required and why?

Both document types require the same simulated eID check because both contain sensitive health data and must be attributed to a named professional. Name or link possession alone is not sufficient. The architecture keeps the identity provider behind an adapter so a production eID service can replace the simulator.

The doctor must also attest a legal basis and enter a reason. This is auditable but is not claimed to be independent proof of patient consent. Maria receives a synthetic informational SMS; direct patient approval is deferred.

### 3. Which FHIR resources are created?

The lab report becomes four `Observation` resources coded with the supplied LOINC identifiers and referencing `Patient/maria-beispiel`. The rehabilitation report becomes a `DocumentReference` containing the original Markdown. Each submission also creates `Provenance`, recording the verified submitter and preserving the distinction between report author and submitter.

Resources are sent to HAPI in one FHIR transaction Bundle. Failed filing does not mark the request as successfully filed.

### 4. How is a misdelivery noticed?

The external link is only a capability to begin verification. It is not sufficient to view or answer the request. An identity mismatch is blocked and audited, repeated failures lock the invitation, and wrong-patient content is rejected by name and birth-date matching before FHIR conversion/storage. Dr. Hofer receives Matrix notifications for lockout, mismatches and processing failures.

### 5. Where does the service run?

The prototype runs as a clinic-controlled Docker Compose deployment. External professionals access only the browser invitation portal. Mail, SMS, identity and FHIR services are replaceable adapters; the local demo uses Mailpit, an SMS outbox, simulated eID and HAPI FHIR.

## Known prototype limitations

- Matrix rooms are deliberately unencrypted for the local hackathon demo.
- Invitation links do not automatically expire, per the agreed MVP decision; they are hashed, revocable, single-use and subject to identity lockout.
- The internal demo API has no separate web login and must remain on a trusted local machine.
- The FHIR CLI validator is not bundled because its JAR must be obtained from the official HL7/HAPI release.
- OCR, scanned PDFs, AI extraction, real SMS/email, real ID Austria and direct patient approval are deferred.
