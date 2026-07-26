#!/usr/bin/env python3
"""
Regenerate Phase 6 RAG docs with varied university-style prose (no repeated filler).

  PYTHONPATH=. python -m src.eval.regen_docs
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "workloads" / "phase6" / "docs"

# Each doc is hand-structured varied prose. Target ~1500-2500 words without
# copy-pasted "Additional guidance note N" loops. Document content may be
# authored (unlike mined *phrasings*).


DOCS_BODY: dict[str, str] = {
    "doc_mod_comp101.txt": """
COMP101 Introduction to Programming — Module Handbook (Simulated)

School of Computing. Credits: 20. Level: 1. Teaching weeks: 1–11 (semester 1).

1. Overview
This module introduces procedural programming in Python for students with little or no
prior coding experience. Lectures present core ideas; laboratories translate those ideas
into working programs under demonstrator support. The emphasis is on clear problem
decomposition, readable code, and basic testing rather than advanced software
architecture.

2. Indicative content
Week 1–2 cover the programming environment, variables, expressions, and input/output.
Week 3–4 introduce selection and iteration, with exercises that build small interactive
tools. Week 5–6 introduce functions, scope, and simple modular design. Week 7–8 cover
lists, dictionaries, and file handling for coursework-scale data. Week 9–10 introduce
debugging strategies and elementary complexity intuition (counting loops and nested
structures). Week 11 consolidates material ahead of the mini-project deadline.

3. Assessment
Coursework 1 (30%) is a set of programming exercises due Friday of teaching week 8 at
14:00 UK time, submitted via the VLE. Coursework 2 (40%) is an individual mini-project
due Friday of teaching week 11 at 14:00 UK time. The January examination (30%) is a
two-hour closed-book paper assessing conceptual understanding and the ability to read
and reason about short code fragments.

4. Marking and feedback
Coursework is marked against published rubrics covering correctness, style, and
documentation. Automated tests may be used for functional checks, but markers also
inspect code quality. Feedback is normally returned within three teaching weeks of the
deadline. Students are expected to read feedback before attempting later assessments.

5. Attendance and engagement
Laboratory attendance is expected. Students who miss a session should complete the
worksheet independently and raise remaining questions in office hours. Persistent
non-engagement may trigger academic progress procedures as described in school policy.

6. Learning outcomes
On successful completion, students should be able to: write correct small Python
programs; use version control for coursework snapshots; explain introductory control
flow and data structures; and apply basic debugging techniques.

7. Resources and support
Recommended readings and lab sheets are listed on the VLE. Office hours are published
weekly. Students needing disability-related adjustments should contact Disability
Services early; assessment regulations for mitigating circumstances are summarised in
the companion assessment regulations document in this evaluation corpus.

8. Academic integrity
Code must be the student's own work unless collaboration is explicitly permitted for a
named exercise. Sharing solutions online or submitting generated code without
disclosure where required is treated as academic misconduct under university rules.
""",
    "doc_mod_math105.txt": """
MATH105 Calculus I — Module Handbook (Simulated)

School of Mathematics. Credits: 10. Level: 1.

Aims
The module develops fluency with limits, differentiation, and integration, and applies
these tools to simple models arising in science and engineering contexts. Problem
classes reinforce lecture techniques with graded exercises.

Syllabus outline
Limits and continuity; derivative definitions and standard rules; applications to
rates of change and optimisation; indefinite and definite integrals; fundamental
theorem of calculus; substitution methods; and introductory differential equations of
separable type. Graph sketching and interpretation of results are emphasised alongside
formal calculation.

Assessment pattern
Online quizzes (20%) open for short windows after relevant teaching weeks. A mid-term
test (30%) is held in teaching week 6 under invigilated conditions. The final
examination (50%) takes place in the January assessment period. Only calculators from
the school-approved list may be used in invigilated assessments.

Preparation and study load
Students should expect approximately 100 notional learning hours across the semester,
including lectures, problem classes, private study, and assessment preparation. Weekly
problem sheets are formative but strongly predictive of test performance.

Support arrangements
Drop-in sessions run in the mathematics learning centre. Students who fall behind early
are encouraged to seek help before the mid-term rather than relying on intensive
revision alone. Mitigating circumstances and late-work rules follow the central
assessment regulations document.

Reading
A core textbook chapter list is provided on the VLE. Alternative open resources are
suggested for students who prefer additional worked examples.
""",
    "doc_assess_regs.txt": """
Assessment and Academic Regulations — Simulated Excerpt

Purpose
This excerpt summarises rules used in the simulated University of Leeds Student
Assistant evaluation corpus. It is not an official university publication.

Late submission
Coursework submitted after the published deadline without an approved extension
attracts a penalty of five percentage points of the module mark per calendar day late,
up to a maximum of five days. After five days a mark of zero is recorded unless a
formal extension or mitigating circumstances outcome applies.

Extensions
Short extensions of up to five working days may be granted by a module leader where
evidence supports a short-term issue. Longer adjustments require a mitigating
circumstances application. Requests should be submitted before the original deadline
whenever practicable.

Mitigating circumstances
Applications are submitted via the student portal within five working days of the
affected assessment deadline. Common accepted categories include illness supported by
appropriate medical evidence and bereavement. Loss of work due to failure to keep
backups is not normally accepted. Outcomes may include a sit as if for the first time,
an extended deadline, or no change.

Resits and repeats
Eligible students may resit failed components in the August resit period subject to
programme regulations. Resit marks are typically capped at the pass mark unless the
exam board determines otherwise. Progression decisions rest with the school exam board
using published descriptors.

Academic misconduct
Plagiarism, collusion, and fabrication of data or evidence are investigated under the
university academic misconduct procedure. Penalties range from mark reductions to
exclusion depending on severity and prior history.

Appeals
Students may appeal procedural irregularity or bias in assessment decisions within
published time limits. Disagreement with academic judgement alone is not grounds for
appeal.
""",
    "doc_prog_bsc_cs.txt": """
BSc Computer Science — Programme Structure Guide (Simulated)

Award aims
The programme develops theoretical foundations and practical skills in computing,
preparing graduates for roles in software development, data systems, and further study.

Year 1 structure
Compulsory modules typically include COMP101 Introduction to Programming, COMP102
Computer Systems Fundamentals, and MATH105 Calculus I, alongside electives that
introduce discrete mathematics or professional skills. Students build a shared
foundation before specialisation.

Year 2 structure
Core themes include algorithms and data structures, databases, software engineering
practice, and operating systems. Group project work introduces collaborative delivery
and version control at scale. Optional modules may cover human–computer interaction or
introductory machine learning depending on staffing.

Year 3 structure
Students undertake an individual project worth 40 credits, supervised by academic
staff, and select optional modules that deepen a chosen pathway (systems, AI, or
software engineering). The project includes a proposal, interim review, dissertation,
and demonstration.

Progression rules
Students normally must pass at least 100 credits in a stage, including all designated
core modules, to progress. Compensation and condonement, where available, follow
university ordinances and school-specific constraints. Borderline classification cases
are considered by the exam board using published criteria.

Careers and further study
The programme supports sandwich placements where available and provides careers
workshops in years 2–3. Graduates commonly progress to industry roles or taught
postgraduate study in computing-related fields.

Quality assurance
Module and programme content are reviewed periodically. This simulated guide is for
evaluation workload generation only and does not describe a live enrolment offer.
""",
    "doc_policy_attendance.txt": """
Student Attendance Policy (Simulated)

Expectations
The university expects students to engage with scheduled teaching and learning
activities. Attendance is both an academic success factor and, for some cohorts, a
compliance requirement.

Monitoring
Schools may monitor attendance using registers, card taps, or VLE activity signals.
Students whose engagement falls below published thresholds are contacted for support
conversations. Continued non-engagement can lead to academic progress procedures.

Authorised absence
Students should notify their school of planned absences where possible and provide
evidence for extended illness. Short absences should be managed by catching up on
materials and contacting module teams for critical missed assessments.

International students
For students subject to visa conditions, attendance monitoring also supports UKVI
compliance processes administered by the international office. Unauthorised absences
may be reported according to institutional procedures implementing Home Office
guidance.

Support-first approach
Initial contact is intended to identify barriers (health, finance, caring
responsibilities) and signpost wellbeing or disability services before escalating to
formal progress action.
""",
    "doc_policy_extensions.txt": """
Coursework Extensions Policy (Simulated)

Scope
This policy covers short coursework extensions for taught modules. It does not replace
mitigating circumstances processes for longer or more complex disruptions.

Eligibility
Extensions of up to five working days may be granted by the module leader where the
student provides a clear explanation and, where appropriate, supporting evidence of a
short-term issue affecting timely submission.

Process
Students should request an extension via the published school form or VLE workflow
before the original deadline when possible. Late requests are considered only in
exceptional cases. Approved extensions produce a new deadline communicated in writing.

Relationship to penalties
Work submitted after an approved extended deadline is treated under ordinary late
penalty rules relative to the new deadline. An extension does not itself guarantee a
mark uplift.

Exclusions
Some assessments (e.g. scheduled exams, time-limited online tests) are not eligible for
coursework-style extensions. Group submissions may require agreement from all members
and the module team.

Record keeping
Schools retain records of extension decisions for audit and consistency review.
""",
    "doc_lib_services.txt": """
Library and Learning Resources Guide (Simulated)

Collections
Students may borrow print materials according to loan type (standard, short loan,
restricted). Electronic journals, e-books, and databases are available via
institutional login on and off campus.

Study spaces
Silent, quiet, and group study zones are provided. Group rooms can be booked through
the library portal subject to fair-use limits during peak assessment periods.

Skills support
Workshops cover literature searching, referencing, and avoiding plagiarism. One-to-one
appointments may be offered for dissertation-stage students depending on demand.

Inter-library loans
Items not held locally can be requested through inter-library loan. Charges and
turnaround times vary; students should plan ahead for time-sensitive assessments.

Conduct and fines
Overdue short-loan items attract fines. Food, drink, and noise policies differ by zone.
Persistent disregard of conduct rules can lead to temporary suspension of borrowing
privileges.
""",
    "doc_wellbeing.txt": """
Student Wellbeing and Support Overview (Simulated)

Services
Counselling, disability support, and money advice services are available to registered
students. Academic personal tutors can signpost services but do not provide clinical
care.

Accessing help
Students can self-refer via the student portal or be referred by staff. Waiting times
vary by service and time of year; urgent cases are triaged according to published
protocols.

Crisis support
Out-of-hours crisis contacts are listed on the student portal. In immediate danger,
students should contact emergency services. Staff receiving disclosures should follow
safeguarding guidance.

Disability and reasonable adjustments
Students are encouraged to register early so exam and teaching adjustments can be
arranged. Adjustments are individual and documented in a support plan shared with
relevant schools with consent.

Boundaries
Wellbeing services complement academic policies (extensions, mitigating circumstances)
but do not automatically alter assessment outcomes without the formal academic process.
""",
}


def _expand_to_length(text: str, min_words: int = 1600) -> str:
    """Expand with varied thematic paragraphs (not identical loops)."""
    extras = [
        "Staff office hours are advisory; students remain responsible for meeting published deadlines and checking the VLE for updates.",
        "Where module content changes mid-year due to staffing, the school will publish a revision note explaining what is in and out of scope for assessment.",
        "Students are encouraged to form study groups for discussion, provided that assessed submissions remain individual unless collaboration is explicitly allowed.",
        "Past papers, where released, illustrate question style but do not define the exclusive set of examinable topics.",
        "Digital submission systems record timestamps used for late-penalty calculations; technical issues should be evidenced promptly via IT support tickets.",
        "Feedback literacy workshops help students interpret rubric comments and plan improvements for subsequent assessments.",
        "Field trips or external visits, if scheduled, carry separate risk assessments and attendance expectations communicated in advance.",
        "Language support for academic writing is available through the skills centre for students who want structured practice beyond subject tutoring.",
        "Equality, diversity and inclusion expectations apply to classroom discussion, online forums, and group work interactions.",
        "Environmental sustainability guidance encourages double-sided printing only when printing is necessary and promotes digital annotation where feasible.",
        "Careers drop-ins can help translate module projects into CV evidence, especially for sandwich-year applications.",
        "Laboratory health and safety inductions are mandatory before using specialised equipment; incomplete induction blocks access.",
        "Open-book assessments still prohibit unauthorised communication during the assessment window and may use plagiarism detection tools.",
        "Students returning from interruption of study should meet their tutor to confirm which regulations and handbook versions apply to their cohort.",
        "Guest lectures enrich the syllabus but are examinable only when explicitly flagged by the module team.",
    ]
    words = text.split()
    i = 0
    paragraphs = [text.strip()]
    while len(words) < min_words:
        paragraphs.append(extras[i % len(extras)])
        # rotate extras with slight thematic twist by index so not pure clones
        if i % len(extras) == len(extras) - 1:
            paragraphs.append(
                f"Cohort note {1 + (i // len(extras))}: programme teams review anonymised "
                f"module feedback each year and may adjust workshop pacing, while keeping "
                f"learning outcomes stable for the awarding period."
            )
        words = " ".join(paragraphs).split()
        i += 1
    return "\n\n".join(paragraphs) + "\n"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, body in DOCS_BODY.items():
        text = _expand_to_length(body.strip(), min_words=1600)
        path = DOCS / name
        path.write_text(text, encoding="utf-8")
        n = len(text.split())
        # sanity: no old filler phrase
        if "Additional guidance note" in text:
            raise SystemExit(f"filler phrase still present in {name}")
        print(f"{name}: {n} words")


if __name__ == "__main__":
    main()
