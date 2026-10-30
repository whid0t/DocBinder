# DocBinder

Doctors in a closed clinical network still request outside lab results and rehabilitation reports by fax or email, then manually enter the answers. DocBinder connects that workflow: request a document through Matrix, let the outside professional answer in a browser, and file the result as FHIR R4 with provenance and an audit trail.

The outside person needs no installation or new account. The demo uses synthetic data and simulated ID Austria name matching.

## Start locally

Requirements: Docker with Docker Compose.

```bash
# First setup only; keep your existing .env if you already have one.
cp .env.example .env
./scripts/matrix-init.sh
docker compose up -d --build
```

Wait for Synapse to start and for [HAPI metadata](http://localhost:8081/fhir/metadata) to respond, then create the demo Matrix users:

```bash
./scripts/matrix-create-users.sh
```

Synapse defaults to UID/GID 1000. If your local user differs, set `SYNAPSE_UID` and `SYNAPSE_GID` in `.env` to match the owner of the generated files.

| Service | Open |
|---|---|
| DocBinder dashboard and invitation portal | http://localhost:3000 |
| Element / Matrix | http://localhost:8080 |
| Mailpit invitation inbox | http://localhost:8025 |
| Backend API documentation | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8081/fhir |

Check startup or stop the stack:

```bash
docker compose ps
docker compose logs --tail=100 backend matrix-bot hapi-fhir
docker compose stop
```

## Try the workflow

1. Sign in to Element as `@lena.hofer:klinikum.example`, using `DOCTOR_MATRIX_PASSWORD` from `.env` (default: `docbinder-doctor-demo`).
2. Create a private, **unencrypted** room and invite `@docbinder:klinikum.example`.
3. Send `!request-document`, fill in the example block, and reply `confirm`.
4. Open the invitation in Mailpit (laboratory) or DocBinder's **SMS simulator** (rehabilitation).
5. Enter the recipient's name: `Eva Brandl` for the laboratory example or `Stefan Kern` for rehabilitation.
6. Upload the matching file from [scenario/documents/](scenario/documents/): `lab-result-maria-beispiel.md` or `rehab-report-maria-beispiel.md`.
7. Check the Matrix result notice and select the request in DocBinder to see source documents, FHIR resources, audit events, and the laboratory timeline.

Requests can also be created on the dashboard. Matrix notifications require a request created through the bot so it has a destination room.


## Metric results

Scenario evidence recorded on **2026-10-30**:

| Metric | Target | Result |
|---|---|---|
| HL7 FHIR validation | 0 errors | **PASS — 0 errors** across all 8 exported scenario resources. |
| Misdeliveries caught | 3 of 3 | **PASS — 3/3** under the hackathon assumptions below. |
| Audit coverage | 6 of 6 | **PASS — 6/6** required steps have actor, event and timestamp. |
| Outside-person effort | 0 installs, 0 accounts, under 2 min | **0 installs, 0 accounts.**, under 2 min |

For the hackathon, the simulated name is treated as an eID-provided identity and clinic APIs are assumed to be trusted/internal. 

See [metric evidence and verification commands](metrics/README.md). Seven FHIR-related regression tests also passed on recheck.

## Architecture and design

React provides the dashboard and external portal. FastAPI handles requests, invitation sessions, Markdown parsing and SQLite audit records. The Matrix bot connects Synapse/Element to the backend; Mailpit and the SMS simulator deliver demo invitations; HAPI stores FHIR R4 resources.

- **Identity:** an outside person follows an invitation and completes simulated ID Austria name matching. Both document types use the same check because both require an attributed submitter. Real eID would supply a verified identity instead of typed text.
- **FHIR:** lab values become LOINC-coded Observations; rehab text becomes a DocumentReference. Both reference the Patient and receive source-specific Provenance. Each submission is filed in one transaction.
- **Misdelivery:** wrong identities and wrong-patient documents are rejected and audited. Invitations contain only a reference and link, without patient or document details.
- **Hosting:** the demo runs locally as a clinic-controlled Compose stack. Matrix, SMTP and FHIR use standard protocols and configurable endpoints.

## Tests

In a Python environment with the backend dependencies and pytest installed:

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=matrix-bot python3 -m pytest -q matrix-bot/tests
docker compose config --quiet
```

Official validator evidence and reproduction instructions are in [metrics/](metrics/README.md).

## Demo scope

This is a local synthetic-data prototype. The internal dashboard/API assumes a trusted clinic environment; it has no enforced login. Outside identity is simulated, and invitation links have no expiry (they are revocable, single-use after successful filing, and locked after five failed identity checks). Patient consent replies, real ID Austria, SMS delivery, HTTPS deployment, OCR and PDFs are not implemented. Matrix rooms are unencrypted for the demo.
