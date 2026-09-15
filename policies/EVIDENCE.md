# Evidence

The system runs on the difference between "I did it" and "here is where you
can see that it happened".

## What counts

- A path to a file that exists.
- A commit sha, a branch name, a PR link.
- A gate run recorded by `taos gate run`.
- Test or command output pasted into a task comment.
- A clear statement from the human.

## What does not

- A sentence in chat.
- A memory of having done it earlier.
- "It should work."
- A plan.

## Where it goes

`taos task evidence <ID> --ref <thing> --note <why>`. `taos finish --evidence`
attaches one at the transition. `done` is refused without at least one.

## Status words

- `active`: someone is moving it now.
- `blocked`: a named blocker, on the task, with an owner.
- `waiting`: on the human, a collaborator, or an external event; say which.
- `review`: an artifact exists and the gates passed; a human should look.
- `done`: evidence attached, gates passed, nothing outstanding.

Do not use a status to signal effort. Use it to signal what is true.
