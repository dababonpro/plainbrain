from scripts.unshipped import summary_line


def _row(**changes):
    row = {"area": "Work", "name": "app", "remote": True, "branches": [], "unpushed": 0, "trees": [], "stashes": 0,
           "last": "2026-11-10"}
    row.update(changes)
    return row


def test_a_branch_ahead_of_upstream_whose_commits_are_on_another_remote_branch_is_described():
    branch = {"branch": "main", "commits": 2, "kind": "ahead", "since": "2026-11-09"}
    line = summary_line(_row(branches=[branch]))
    assert line == "- Work/app: 1 branch ahead of upstream, commits already on a remote"


def test_unpushed_commits_and_a_dirty_tree_are_listed():
    branch = {"branch": "feature", "commits": 3, "kind": "no upstream", "since": "2026-11-01"}
    trees = [{"path": "", "changed": 2, "untracked": 1}]
    line = summary_line(_row(branches=[branch], unpushed=3, trees=trees, stashes=1))
    assert line == "- Work/app: 3 unpushed commits on 1 branch since 2026-11-01, 2 uncommitted files, 1 untracked, 1 stash"
