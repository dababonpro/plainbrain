---
name: automate-this
description: "Procedure for turning a repeatable manual workflow into an agreed automation plan before anything runs: lock down the goal (revenue, cost, or personal obligation), restate today's messy process, surface hidden decisions one at a time, settle source conflicts, define saved vs confirmed done, walk three real examples, design self-checks, pick the trigger, present the full plan for approval, and propose the accepted plan as a commitment (and a note if rules should outlive the chat). Use when the user asks to 'automate this' or 'turn this into a routine', not for a one-off edit."
---

# Automate this

Jumping straight from "automate this" to running tools locks in hidden guesses
and breaks on the first messy case. This skill is an intake procedure: it turns
a repeatable manual workflow into a plain-language plan that the user approves
before any automation is built or run.

**Running the automation is out of scope for this skill.** During the interview,
run none of the automation and change nothing in live external systems. Reading
open commitments and notes stays allowed, and so does writing the accepted plan
with the `registry` and note commands afterwards. In the plan you propose, state
that each change must be shown before it is made and wait for approval.

## Procedure

Follow these nine steps in order. Do not skip ahead or batch steps that ask
the user to confirm.

### 1. Goal first

Ask what should exist at the end of the workflow, and whether it serves revenue,
cost, or a personal obligation (for example: bringing in or keeping revenue,
saving time and mistakes, or keeping a personal obligation). If the goal is
vague ("handle invoices", "clean up leads"), keep asking until the user confirms
the concrete end state in their own words.

### 2. Today's process

Ask the user to describe how they do the work today, as messily as they like:

- the steps they take and the tools they open;
- what they watch out for or double-check;
- where the information comes from;
- how they verify the result;
- who gives feedback or needs to know when it finishes.

Restate the whole process in plain words and wait for the user to confirm or
correct it. Plan first; run no automation.

### 3. Hidden decisions

Pull out every judgement call buried in their description — edge cases,
thresholds, missing fields, duplicates, exceptions, or steps that delete, send,
publish, or spend. Surface them **one question at a time**, with a short
recommended answer where one is obvious, until the standing rules are clear.

### 4. Conflicts

Ask which source wins when two sources disagree — for example, an email versus
the database, a spreadsheet versus a CRM record, or a message versus a ticket.
Record the winner for each pair and what should happen to the mismatch (flag it,
overwrite, or stop).

### 5. Done

Define two levels of done for each item or run:

- **Saved:** the record exists in the target system and its fields are right.
- **Confirmed:** the person or downstream system actually received it (a reply,
  a delivered status, a read-back check, or a visible confirmation).

### 6. Real examples

Walk through **three past examples** with the user: two normal cases and **one
that went wrong** (or would have gone wrong). Trace how the rules from steps 3–5
handle each one, and adjust the rules if an example exposes a gap.

### 7. Checking itself

Decide how the automation will check its own work after each run (counts,
read-backs, error thresholds, or spot-checks), and what to record first when
there is no historical baseline data yet (such as logging the first runs and
their outcomes before trusting unattended execution).

### 8. Trigger

Name what starts the workflow: a manual message, an incoming email or webhook,
or a schedule (and how often). Confirm whether any trigger needs a dry-run
window first.

### 9. Plan and record

Present the complete plan in five short parts, then stop and wait for a **yes**:

1. **Goal:** the end state and whether it serves revenue, cost, or a personal
   obligation.
2. **Process:** the agreed steps, noting that each change is shown before it is
   made and waits for approval.
3. **Rules:** standing decisions, source-of-truth order on conflicts, and
   saved vs. confirmed done.
4. **Routine:** self-checks, initial data to record, and the trigger.
5. **Next step:** the single smallest action to take once the user says yes.

After the owner accepts the plan:

1. **Search open commitments first** so you know whether this is a new item or an
   update to an existing one.
2. **Propose one registry item:** the goal as the title, part 5 (`Next step`) as
   `next`, and the trigger in `--why`.
3. **Propose one knowledge note** (using the `note-creation` skill) when the
   standing rules should outlive this chat.
4. **Write only after the owner accepts that proposal,** using the existing
   `registry` (`plainbrain registry add` / `update`, or `python scripts/brain.py`
   if cloned) and note-creation commands — or `capture` when running outside the
   second brain folder, just like `promise-tracking`.

## Credit

Idea adapted from Lauren Tan's "automate anything" prompt.
