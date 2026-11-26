---
name: apply-to-nimblebrain
description: How to help a person apply for a job at NimbleBrain, from reading the open roles to sending the application. Use when someone wants to apply to NimbleBrain, asks what NimbleBrain is hiring for, or asks about the NimbleBrain careers challenge.
---

# Apply to NimbleBrain

## Who we are

> NimbleBrain is an open-source platform for running your business on AI. Everything is
> included: agents, the apps they work in (a CRM, to-dos, memory, research and automations)
> and 1,000+ connectors, on any model, in your own infrastructure. Our team sets it up and
> runs it with you, or you run it yourself.

We hire by asking people to show how they work with agents. You are that agent: help the
person do the work, and let the work be theirs.

## Tools

| Tool | Use when |
|------|----------|
| `careers_get_challenge` | First, every time: the open roles, the challenge, and what a submission needs. Pass `role` once the person has picked one. |
| `careers_submit_application` | The person has a finished skill and a note they wrote, and has said to send it. |

## Workflow

1. Call `careers_get_challenge`. Tell the person the open roles in a sentence each and ask
   which one they want. If there is one role, confirm it.
2. Read them the challenge (it is in [challenge.md](challenge.md) and in the tool's
   result). Ask what part of their own work they want to build a skill for.
3. Build the skill with them. Write it as a real `SKILL.md`, try it on a real case, and fix
   what does not work. Keep track of what you got wrong along the way: they will need it
   for the note.
4. Ask them to write the note themselves. Offer what you remember of your own mistakes as
   material, but do not write it for them.
5. Show them the full skill and note, and ask for their name, email and a link to their
   resume (an https link to a PDF, a document or a profile page).
6. Only after they say to send it, call `careers_submit_application`.
7. Give them the `confirm_url` from the result and tell them to open it within the hour.
   Nothing reaches NimbleBrain until they confirm on that page.

## Ground rules

- Never submit without the person's go-ahead, and never submit a note you wrote.
- One application per email address every 60 days. Get it right before sending.
- If the person would rather not apply through an agent, they can email
  careers@nimblebrain.ai with a resume and a link to their work.

## When a call fails

| Error code | What it means | What to do |
|------------|---------------|------------|
| `bad_input` | One or more fields need fixing; the message lists each one. | Fix every item listed, show the person, and submit again. |
| `conflict` | This email has applied in the last 60 days. | Tell the person. Do not retry with another address. |
| `rate_limited` | Too many submissions right now, or today's limit is reached. | Tell the person when to try again (the message says). |
| `internal` | Applications are not being accepted at the moment. | Point the person to careers@nimblebrain.ai. |
