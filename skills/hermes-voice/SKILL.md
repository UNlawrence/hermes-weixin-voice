---
name: hermes-voice
description: Send WeChat voice replies through Hermes iLink.
version: 1.0.0
author: UNlawrence
license: MIT
platforms: [macos, linux]
prerequisites:
  commands: [hermes-voice, hermes-voice-doctor]
metadata:
  hermes:
    tags: [Hermes, WeChat, Voice, iLink]
    requires_toolsets: [terminal]
---

# Hermes Voice Skill

Use this skill when the user wants Hermes to turn text into a WeChat voice reply and send it through the configured iLink / Weixin account. This skill is for sending short voice messages, not for debugging the Hermes gateway itself unless delivery fails.

## When to Use

- The user says to send a voice message through Hermes or WeChat.
- The user provides a `wxid` plus text and expects an audio reply.
- The user asks to validate whether Hermes Voice is installed and ready.

## Procedure

1. If the user is asking whether the setup works, run `hermes-voice-doctor`.
2. If the user wants to send a message, collect:
   - target `wxid`
   - text to speak
3. Run:

```bash
hermes-voice <to_wxid> "<text>"
```

4. Show the command result to the user in concise plain language.

## Pitfalls

- If `hermes-voice` is missing, tell the user to run the repository `install.command` once.
- If delivery fails with an iLink or HTTP error, run `hermes-voice-doctor` and report which prerequisite is missing.
- If the user does not provide a `wxid`, ask for it before sending.

## Verification

- Successful sends print a `SendResult(...)`.
- If `hermes-voice-doctor` shows a non-default remote iLink base URL and token present, configuration is usually ready.
