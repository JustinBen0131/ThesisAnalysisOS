# Contributing

Research notes, exchange entries, questions and reports of mistakes are welcome
from anyone. Open an issue, or follow the steps on the research-notes and
exchange pages.

## Code

Describe the change in an issue before sending code, so it can be agreed first.
Code you contribute is licensed to the project and its users under the Apache
License, Version 2.0, the same license as the rest of the repository.

## The research exchange

Use a question’s reply link to suggest an observation, correction or new test.
It opens a public GitHub issue. Identify the result you are responding to and
the evidence a reader can check. A person reviews the suggestion before sending it.

Before publication, a maintainer checks the source, scientific scope, privacy
and permission to share the material. The maintainer writes the project’s entry
and links the original issue or pull request. The website never imports issue
text automatically. A citation check establishes what the saved record says.
Assessing the conclusion requires scientific review.

Use public or simulated research material that you have the right to share.
Keep personal data, confidential records and actionable instructions for causing
harm out of submissions. To request a correction or removal, identify the entry
by its ID in an issue. Send software security concerns through the reporting
process. [Software security](SECURITY.md) · [Project license](LICENSE)

## Learning from workflow feedback

Choose one decision from a real task or the bundled example. The questionnaire asks what happened, how you checked it, and what a fresh assistant should do with the same inputs. A report that a step worked can help us preserve it. [Open the questionnaire](https://github.com/JustinBen0131/ThesisAnalysisOS/issues/new?template=workflow-feedback.yml)

When a report points to an improvement, the maintainer records the first decision that anyone can reproduce with public or synthetic inputs. Before changing the OS, write down the expected decision and choose one nearby case where the existing behavior should stay the same. Run both cases before and after the change. For a handoff, give the saved record to a fresh assistant and check which work it repeats or reuses. Link the issue, inputs and observed results in the change that follows.

If the original task cannot be reproduced, keep the report as an open question. Counts of voluntary responses describe the respondents. A claim about system performance needs a comparison with known outcomes.

One example started with a reader reporting that the research exchange's source link was broken. The published check reproduces the old link to an unpublished commit, checks the link from a nested error page, and verifies that both corrected links reach the bundled source. [Source navigation regression test](evals/test_release_integrity.py)

## Credit

For the software citation, see [CITATION.cff](CITATION.cff). The attribution
notice is in [NOTICE](NOTICE).
