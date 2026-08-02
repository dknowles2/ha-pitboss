---
name: pr-comment-audit
description: Audits the review comment threads on a GitHub pull request, flagging unaddressed comments and requests for clarification. Use when checking whether PR feedback has been handled, either standalone or as part of a full review.
---

# Audit PR review comments

Vendored from Home Assistant Core's `ha-pr-comment-audit` skill (Apache-2.0),
with minor wording changes. The original carries no Home Assistant specifics.

## Instructions

- Resolve the PR context first. If no PR number is given, use `gh pr view` to
  identify the current branch's PR.
- Fetch the review comment threads (e.g. `gh api` for review threads and
  comments).
- Flag comments that have not been addressed. If the author replied but did not
  implement the suggestion, still flag it and summarise the reply.
- Flag comments where the author asked for clarification and got none.
- Summarise the flagged comments, with a link for each. Omit comments that have
  been addressed.

## Important

- Report in the CONSOLE only. Do not post anything to GitHub.
