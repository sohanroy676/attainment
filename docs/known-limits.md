# Known limits

What this version does not do, or does with a caveat. Items marked (owner) wait on a person, not on code.

## Calculation and method
- The reference results R1 and R2 are reproduced from synthetic data; the checks against the real workbooks (DS-A, DS-B) wait for the files (owner).
- The target revision proposal is not built; the rule has to come from the mentor (owner).
- Indirect attainment is an entered value (3 by default), not a survey, until v1.3.0. Reports say "entered, not measured".
- Which result the college treats as official, 2.18 (strict 60%) or 2.32 (approved pass marks), is a college decision (owner).
- Course-level comparison against old workbooks is not built; the comparison is at batch level.

## Entering marks
- The marks grid is a plain form (one box per cell) with an Excel template for bulk entry. The spreadsheet-style grid with paste is not built yet.
- Excel uploads read stored values only; a file with a formula that was never saved with its result is refused with the cell named.

## Reports and exports
- PDFs need the Pango libraries (present in the Docker image). Layout has not been compared with the mentor's documents (owner).
- Action Taken Report embeds PNG and JPEG proofs; PDF proofs are listed by name and checksum.
- Excel exports hold the text shown on the page, so numbers are text cells.

## Security and operations
- Rate limits are counted per server process; with three workers the limit is up to three times looser. They slow abuse down; they are not exact quotas.
- Lockout is per username (behind the proxy every client shares one address), so someone can lock a known username by guessing; the lock lasts 15 minutes.
- The accessibility check is a script (labels, headings, names, table headers). Colour contrast, keyboard order and screen-reader use need a human check.
- The audit viewer is college-wide only; there is no department-scoped view for a HoD.
- There is no platform administrator role: every user belongs to one college. Creating a college is a command-line job (`create_college`).
- Failed logins are not written to the audit log (the college is not known before login).
- Two-factor login, email reminders and Google sign-in arrive in v1.1.0; single sign-on in v1.5.0.
- The free demo hosting (Render, Neon) has not been set up; its free-tier limits have to be re-checked first (owner).

## Privacy
- Anonymising replaces the name and identifiers. Marks, enrolments and signed results stay, so a person who knows a student's marks could still recognise them; this is the trade-off for reproducible results.
- Parsed uploads and stored files are removed by sections whose batch is past retention, not student by student.
- The retention period and the notice wording must be agreed with the college (owner).
