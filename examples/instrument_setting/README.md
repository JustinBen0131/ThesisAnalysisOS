# One setting, one check

A stand-in for an instrument model, small enough to read in a minute.

- `model/settings.json` holds one setting: a correction that is on or off.
- `model/check_response.py` feeds the model 1000, prints what it reads back and
  passes when the reading is within 50 of what was fed in.
- `notes/lab_notes.txt` is a file the check never reads.

The readings are made up and the model is three lines. The check passes with
the correction on, where it reads 970, and with it off, where it reads 1000. A
pass therefore cannot say which setting is right. Only a reference measured
some other way can.

`evals/replay_setting_change.py` uses this folder to record what TAOS answers
when the setting changes after the check has passed. The saved answers are in
`evals/results/followups/setting-change.json`, and the homepage decision shows
them under "Inspect the saved record".

```bash
python3 evals/replay_setting_change.py --verify
```
