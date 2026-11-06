"""Offline behavior tests for the preview-comment upsert helper."""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("upsert.sh")
MARKER = "<!-- sdf-pr-preview -->"
OLD_URL = "PR Preview: https://developers-pr-2905.example.com"


class UpsertTests(unittest.TestCase):
  def run_case(self, pages, message):
    with tempfile.TemporaryDirectory() as tmp:
      tmp = pathlib.Path(tmp)
      bin_dir = tmp / "bin"
      bin_dir.mkdir()
      mock = bin_dir / "gh"
      mock.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args[:3] == ['api', '--paginate', '--slurp']:
  print(pathlib.Path(os.environ['MOCK_COMMENTS']).read_text())
elif args[:2] == ['api', '-X']:
  with pathlib.Path(os.environ['MOCK_CALLS']).open('a') as f:
    f.write(json.dumps(args) + '\\n')
else:
  raise SystemExit('unexpected gh args: ' + repr(args))
""")
      mock.chmod(0o755)
      comments = tmp / "comments.json"
      comments.write_text(json.dumps(pages))
      calls = tmp / "calls.jsonl"
      env = dict(os.environ)
      env.update(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        GH_TOKEN="test-token",
        GH_REPO="stellar/stellar-docs",
        PR_NUMBER="2905",
        PREVIEW_MESSAGE=message,
        MOCK_COMMENTS=str(comments),
        MOCK_CALLS=str(calls),
      )
      proc = subprocess.run(["bash", str(SCRIPT)], env=env,
                            capture_output=True, text=True)
      self.assertEqual(proc.returncode, 0, proc.stderr)
      return [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

  @staticmethod
  def comment(comment_id, body, user="github-actions[bot]"):
    return {"id": comment_id, "body": body, "user": {"login": user}}

  def test_first_preview_creates_comment(self):
    calls = self.run_case([[]], OLD_URL)
    self.assertEqual(len(calls), 1)
    self.assertEqual(calls[0][1:4], ["-X", "POST", "repos/stellar/stellar-docs/issues/2905/comments"])
    self.assertIn(MARKER, calls[0][5])

  def test_legacy_comment_edited_on_teardown(self):
    calls = self.run_case([[self.comment(6061238777, OLD_URL)]], "PR Preview: torn down")
    self.assertEqual(len(calls), 1)
    self.assertEqual(calls[0][1:4], ["-X", "PATCH", "repos/stellar/stellar-docs/issues/comments/6061238777"])
    self.assertIn("PR Preview: torn down", calls[0][5])

  def test_marked_comment_preferred_across_pages(self):
    pages = [
      [self.comment(10, OLD_URL), self.comment(11, OLD_URL, "random-user")],
      [self.comment(12, OLD_URL + "\n\n" + MARKER)],
    ]
    calls = self.run_case(pages, "PR Preview: torn down")
    self.assertEqual(calls[0][3], "repos/stellar/stellar-docs/issues/comments/12")

  def test_noop_when_content_is_unchanged(self):
    self.assertEqual(self.run_case([[self.comment(12, OLD_URL + "\n\n" + MARKER)]], OLD_URL), [])

  def test_no_preview_means_no_teardown_comment(self):
    self.assertEqual(self.run_case([[]], "PR Preview: torn down"), [])

  def test_does_not_edit_other_bots_comment(self):
    calls = self.run_case([[self.comment(12, OLD_URL + "\n\n" + MARKER,
                                       "another-bot[bot]")]], OLD_URL)
    self.assertEqual(calls[0][2], "POST")

  def test_reopened_preview_edits_prior_teardown(self):
    calls = self.run_case([[self.comment(13, "PR Preview: torn down\n\n" + MARKER)]], OLD_URL)
    self.assertEqual(calls[0][2], "PATCH")
    self.assertEqual(calls[0][3], "repos/stellar/stellar-docs/issues/comments/13")


if __name__ == "__main__":
  unittest.main()
