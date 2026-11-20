# Smart School Management System

A single-school university OOP and DSA demo. Django 6.1.3, SQLite3, Django templates, HTML5, CSS3, Vanilla JavaScript, Bootstrap 5.3.8, and Chart.js 4.5.1.

## Run on Windows PowerShell

Extract the archive and open PowerShell inside the `smart-school` folder, beside `manage.py`. Use Python 3.12 or newer.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_data
.\.venv\Scripts\python.exe manage.py runserver
```

## Run on macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_data
.venv/bin/python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). The first installation needs internet for pip. The running app defaults to bundled Bootstrap and Chart.js and runs without internet. To load the CDN builds instead, open `/dashboard/?cdn=1`. The packaged copies provide a fallback.

The project and app are already scaffolded. The exact commands used to create their initial structure were `python -m django startproject smart_school .` and `python manage.py startapp core`. Run those only in an empty project when rebuilding from scratch. The archive includes the initial migration. If reconstructing manually without the migration file, run `python manage.py makemigrations core` before `migrate`.

## Demo accounts

All demo accounts use the password `pass1234`.

| Role | Username |
| --- | --- |
| Teacher | `teacher1` |
| Admin | `admin` |
| Student | `student1` |
| Finance | `finance1` |
| Principal | `principal` |

Additional synthetic accounts include `teacher2` and `student2` through `student6`. Seed data includes classes, grades, attendance, health flags, upcoming syllabus, fee history, payroll, leave requests, and pending check-ins. The seed command preserves existing decisions and passwords. For a completely fresh demo, extract into a new folder and repeat setup.

## Suggested viva sequence

1. Sign in as Teacher. Select a class and choose **Simulate QR & GPS**. Open the live camera and capture a frame, or choose **Use demo snapshot** if the camera is unavailable. Submit and show **Pending**.
2. Sign in as Admin. Approve the new check-in. Use the second seeded check-in to demonstrate **Reject** independently. Review a leave request and resolve the oldest Tier 2 task. Switch Talent Scout between Debate and Sports.
3. Return to Teacher. Mark a planned syllabus topic as missed and show the next planned topic moving forward one day. Record a new subject score and lock it. Report a Tier 3 issue.
4. Open Student to show personal grades, attendance, syllabus, health flags, and fee alerts. Open Finance and look up `student1`. Run the defaulter check before collecting the fee. Generate and verify a transcript, or print it to PDF.
5. Open Principal to show the simulated WhatsApp escalation, pass/fail doughnut, teacher audit, and monthly cashflow chart.

## Source map

| File | What to show |
| --- | --- |
| `smart_school/settings.py` | SQLite, local static/media settings, sessions and custom user |
| `smart_school/urls.py` | Shared dashboard, role actions, protected photos, transcript verification |
| `core/models.py` | BaseUser and five role proxy subclasses, guarded payroll access, grade validation and locking |
| `core/dsa_engine.py` | Doubly linked nodes with forward/backward references, manual max heap, dictionary lookup, deque |
| `core/services.py` | Role dashboards, abstract notifications, transactional scheduling and escalation |
| `core/views.py` | Role and object checks, Django form actions, signed transcripts |
| `core/management/commands/seed_data.py` | Demo account and record creation |
| `core/templates/` | Base, login, five dashboards, reusable form fragments, transcript |
| `core/static/core/` | CSS, camera capture, charts and offline vendor assets |
| `core/tests.py` | Integration checks for core demo workflows |

## Complexity and demo boundaries

- Syllabus construction is O(n). The node index locates the missed topic in expected O(1). Walking and updating the remaining k topics is O(k).
- Building the max heap is O(n). Peeking at the root is O(1). Each top-student extraction is O(log n).
- Loading the finance roster and building the dictionary take linear time in the returned records. A lookup in the populated map is expected O(1).
- The FIFO queue loads open Tier 2 issues in creation order. Popping the next issue from the deque is O(1).
- Role checks and class ownership enforce authorization on the server. Python name mangling illustrates encapsulation. The webcam UI exposes live capture and a labeled simulation and has no file picker. Browser payloads are not attested, so this demo does not prove a photo's origin or geographic location.
- QR, GPS and WhatsApp delivery are simulated. Camera capture uses the device camera if permitted on localhost. Fee defaulter reminders run from the Finance button, with Tier 1 on the due date and Tier 2 from seven days overdue.
- A transcript contains only finalized grades. The signed verification link is a bearer link containing the transcript and can be opened by anyone who receives it. Verification uses the issuing installation's signing key.
- This is a local, single-school demonstration with synthetic data and shared demo passwords.

Run checks with the virtual environment's Python and `manage.py check` or `manage.py test`.
