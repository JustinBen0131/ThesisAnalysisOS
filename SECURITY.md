# Reporting a software security concern

If you find a security problem in the CLI, website, release process or research record checkers, sign in to GitHub and send it directly to the maintainer. Include the component, version or commit, what you observed, and what someone else could access. Use invented file names and data. Keep credentials, personal data and unpublished research in your own workspace. [Report a vulnerability privately](https://github.com/JustinBen0131/ThesisAnalysisOS/security/advisories/new)

If a scientific result looks wrong, use the reply link on its research question. If TAOS made a surprising workflow decision, describe that decision in the public form. [Research exchange](https://whatstillholds.com/exchange/) · [Workflow feedback](https://github.com/JustinBen0131/ThesisAnalysisOS/issues/new?template=workflow-feedback.yml)

## Working with a shared research record

TAOS is designed for collaborators who share a trusted local workspace. The
reviewer name on a decision is supplied by the caller. A teammate with write
access can change the local records, settings or history. Use individual
accounts and retain an independently controlled, versioned copy when a
decision needs attributable approval or a durable audit history.

A check runs a command with your operating-system account. Isolated checks
use separate verified copies of selected files. Their result records the
additional restrictions available on that machine. Use an appropriate
execution environment for untrusted programs or sensitive data.

## Checking a copy of the website

Each build produces `release.json`. It lists the path, length and SHA-256 of each served file except the inventory itself. Its release fingerprint is the SHA-256 of that list encoded as compact UTF-8 JSON with sorted keys, in path order.

From a checkout of the software, use the following command on a complete copy of the built site. The optional fingerprint lets you compare that copy with a value you saved separately from a trusted release.

```sh
python3 site/release_integrity.py PATH_TO_SITE --expected-sha256 SAVED_FINGERPRINT
```

The browser policy is set on each generated HTML page. Source listings can be read with scripts disabled. Only the private film templates can supply approved inline scripts. The project’s ordinary links to source files, research data and scientific discussions remain usable directly.

Pages that show the comparison with public main ask GitHub’s API for the repository’s file list. The production site uses Cloudflare Web Analytics. A separate collector records selected actions on the home, decisions, record, HPC, workflow, evidence and exchange pages. Actions within one page load share a random ID. Opening another page creates a new ID. The record includes the UTC day, site revision, page category, broad referral and screen-size categories, and actions taken. The collector defines no automatic deletion period for these records. The dashboard uses shorter reporting windows. The private preview omits both readership scripts. Downloaded research records and the command-line checkers work offline.

## Sharing a compute review

An HPC review can contain the research question, output names, source references and the diagnosis of a failed attempt. Opening the file on the HPC page reads it in your browser. Before you attach a review to a public issue, make a small copy with invented labels and inspect it yourself.

Filing the review with `--task` writes a compact event to the local project. It includes the task, campaign and actor labels, outcome counts and fingerprints. A project progress export also names its configured principal, project and tasks. To show someone how the report works with public data, run the bundled example from the repository root.

```sh
./taos usage progress --packet examples/hpc/campaign.json
```
