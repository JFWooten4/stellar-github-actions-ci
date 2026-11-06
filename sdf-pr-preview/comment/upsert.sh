#!/usr/bin/env bash
# Keep the PR preview URL and teardown status in one GitHub issue comment.
set -euo pipefail

: "${GH_REPO:?}"
: "${PR_NUMBER:?}"
: "${PREVIEW_MESSAGE:?}"

marker='<!-- sdf-pr-preview -->'
body="${PREVIEW_MESSAGE}"$'\n\n'"${marker}"

# GH's --slurp produces an array of pages. Search all pages, not just the
# newest 100 comments. Only edit comments from the Actions bot.
comments="$(gh api --paginate --slurp "repos/${GH_REPO}/issues/${PR_NUMBER}/comments?per_page=100")"
comment="$(jq -c --arg marker "$marker" '
  [ .[][] | select(.user.login == "github-actions[bot]") ] as $comments
  | ([ $comments[] | select((.body // "") | contains($marker)) ] | first)
    // ([ $comments[] | select(
      ((.body // "") | startswith("PR Preview: https://"))
      or .body == "PR Preview: torn down"
    ) ] | first)
    // empty
' <<< "$comments")"

if [ -n "$comment" ]; then
  existing_body="$(jq -r '.body' <<< "$comment")"
  if [ "$existing_body" != "$body" ]; then
    comment_id="$(jq -r '.id' <<< "$comment")"
    gh api -X PATCH "repos/${GH_REPO}/issues/comments/${comment_id}" \
      -f "body=${body}" --silent
  fi
elif [ "$PREVIEW_MESSAGE" != 'PR Preview: torn down' ]; then
  # Never create a teardown-only comment for a PR that had no preview.
  gh api -X POST "repos/${GH_REPO}/issues/${PR_NUMBER}/comments" \
    -f "body=${body}" --silent
fi
