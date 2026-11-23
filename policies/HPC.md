# Decide what needs to run

Start with the researcher's question and the manifest of expected outputs. A completed job can return an empty file. An interrupted submission report can hide a running job. The next action depends on which happened.

Try the three-sample case in a fresh checkout with Python 3.9 or later.

```sh
./taos hpc review examples/hpc/campaign.json
```

A and B account for five readings. C returned zero of two. A transfer record identifies the incomplete input. Keep A and B and take a retry of C to the resource owner. Each row names its evidence. [Example packet](../examples/hpc/campaign.json)

## Inspect your campaign

1. List the expected output IDs from the project's input manifest. Record the input, recipe, settings, independent check and expected count for each ID. Use digests or immutable revisions.
2. Reconcile attempts against the execution record. Preserve existing attempt identities. Missing returns remain unknown. Include unexpected returns so the owner can reconcile them.
3. For each finished attempt, retain a small output or independent audit file with its original SHA-256. Record the observed count and the result of the project's own test. The reviewer compares the records and hashes the cited file. A saved audit receipt represents the output when the audit was performed.
4. For a terminal failure, cite its cause and the evidence for that diagnosis. Request a retry of the affected IDs after the owner reviews the scope. Preserve every passing result.
5. Before expanding, name the proposed IDs, a checked pilot of the same workload profile and the resource owner. Use measured upper bounds that cover the expensive inputs, with the site's margin. Include duration, memory, temporary and retained space, file counts and concurrency. Cloud proposals also need cost and budget in one currency.

Choose a pilot that can tell whether a change took effect. If the study widens a selection range, include a known input in the added interval and a control inside the original interval. Record the worker revision that actually ran and what it returned for each input. A successful job with a nonempty file can still contain only the old range. If the added input is missing, mark the project's output check as failed and retain both observations for diagnosis.

Generate an inspection brief for HTCondor, Slurm, AWS Batch, a workstation or another environment.

```sh
./taos hpc brief --setting slurm --question "Which outputs need another run?"
./taos hpc review campaign.json --json
```

Save the JSON output and open it under **Read a review** on the HPC page. The command also prints a human-readable summary when run without the JSON option. Both work locally. The report fingerprints the evidence packet and the reviewer and lists the input, recipe, settings and check for each output. Carry those identities across handoffs.

## Connect compute to a research task

Run `./taos usage progress --packet campaign.json` to see recorded worker time and how many listed outputs were reusable when checked. Accounting is optional. Cite a saved JSON file and its original SHA-256 in `accounting`. Each attempt in the file names a unique ID, its output and whole elapsed worker-seconds. Durations from parallel workers add. Coverage counts only the outputs represented in the record. Missing or unreadable accounting leaves time unknown. Batch forecasts and possible savings are separate from observed usage. [Fictional accounting record](../examples/hpc/returns/worker-accounting.json)

To keep the review with a project, replace `TASK-ID` below with the ID from `./taos task list`. Use a stable campaign name for each independent set of outputs.

```sh
./taos hpc review campaign.json --task TASK-ID --campaign sensor-study
./taos usage progress --task TASK-ID
```

The task capsule carries the latest review of each campaign into the next session. Each review records when it was filed, its actor label, counts and fingerprints. Filter checks and latest reviews by filing actor with `./taos usage progress --actor NAME`. Worker time belongs to the attempts in the receipt. The project principal is the person named at setup. A task approval covers the workspace and instructions accepted by that person. Recheck a campaign packet when its files change.

## Evidence format

The `manifest` names the original source and its independently recorded `total` number of outputs. Each entry in `expected` has a distinct `id`, workload `profile`, expected `count` and a `basis` with `input`, `recipe`, `settings` and `check`. Each entry in `returns` names an ID, a `source` for its execution state and one of `unstarted`, `queued`, `running`, `finished`, `failed` or `unknown`. A finished receipt contains its original basis, observed count, boolean `passed`, and a local `file` and `sha256`. File paths are relative to the packet directory. Use small audit receipts for large datasets. A diagnosed failure cites its `cause`, the local `reference` behind it and that file's recorded `sha256`.

The optional `batch` section in the example scopes a proposal to exact IDs. Retained output accumulates across the batch. Temporary use is charged for concurrent workers. Supply the capacity still available after other reservations. The estimate assumes independent, comparable jobs and one storage pool. Check each pool if data and scratch use separate volumes. Elapsed time excludes queue waits. Use whole seconds, MiB, file slots and minor currency units. Round measured usage up. Workstations also need the memory available to all workers in `limits.shared_memory_mib`. An estimate that exactly consumes a limit calls out the missing headroom. A proposal that fits still goes to its named resource owner.

## Improve a rule after an incident

Keep the failure and an ordinary successful case. Identify the first observation that distinguishes them. Add the smallest check that captures the difference and replay it against both examples and representative history. Count the failures it would catch and the ordinary work it would hold. Keep site-specific thresholds in the site's limits. Add a regression case and carry the result into the downloadable evidence and the page through the same reviewer. [Testing proposed changes](SCIENCE.md)
