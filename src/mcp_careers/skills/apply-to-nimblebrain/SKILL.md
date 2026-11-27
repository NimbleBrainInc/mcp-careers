---
name: apply-to-nimblebrain
description: How to help a person apply for a job at NimbleBrain, from the open roles to a sent application, including the one question every applicant answers in their own words. Use when someone wants to apply to NimbleBrain, asks what NimbleBrain is hiring for, or wants to send NimbleBrain their resume.
---

# Apply to NimbleBrain

## Who we are

> NimbleBrain is an open-source platform for running your business on AI. Everything is
> included: agents, the apps they work in (a CRM, to-dos, memory, research and automations)
> and 1,000+ connectors, on any model, in your own infrastructure. Our team sets it up and
> runs it with you, or you run it yourself.

Connecting this server and applying through it is the first thing we see of how someone
works with agents. Keep it quick and accurate, and let what is sent be theirs.

## Tools

| Tool | Use when |
|------|----------|
| `careers_list_roles` | First, every time: who we are, the open roles, and what an application needs. |
| `careers_submit_application` | The person has seen exactly what will be sent and said to send it. |

## Workflow

1. Call `careers_list_roles`. Tell the person the open roles in a sentence each and ask
   which one they want. If there is one, confirm it. If there are none, say so.
2. Ask for their full name, email, and a link to their resume or a profile such as
   LinkedIn. Use exactly what they give you; never guess a URL or an email.
3. Ask them to check the resume link opens when they are signed out (a private window
   works). A private Google Drive or Dropbox file will not open for the team.
4. Ask them the `question` from `careers_list_roles`, word for word. Their answer, 50 to
   300 words in their own words, is the required `note`. You can help them tighten an answer
   they wrote; do not write one for them, and do not suggest what it should say.
   Then ask whether they want to add a link to something they have built with agents. That
   one is optional.
5. Show them every field exactly as it will be sent, and ask if it is right. Leave out an
   optional field they skipped, rather than showing it blank, and do not send it.
6. Only after they say to send it, call `careers_submit_application`.
7. Give them the `confirm_url` and tell them to open it within the hour. Nothing reaches
   NimbleBrain until they confirm on that page.

## Ground rules

- Never submit without the person's go-ahead, and never submit a note you wrote.
- One application per email address every 60 days. Get it right before sending.

## When a call fails

Every error message starts with its code (`bad_input: ...`).

| Error code | What it means | What to do |
|------------|---------------|------------|
| `bad_input` | One or more fields need fixing; the message lists each one. | Fix every item listed with the person, show them, and submit again. |
| `conflict` | This email has applied in the last 60 days. | Tell the person. Do not retry with another address. |
| `rate_limited` | Too many applications right now, or today's limit is reached. | Tell the person when to try again (the message says). |
| `internal` | Applications are not being accepted at the moment. | Tell the person to try again later. |
