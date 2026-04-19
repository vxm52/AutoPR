import os
import re
import git
from github import Github  # PyGitHub package
from agent.context import RunContext, StepError


_SAFE_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _safe_path(repo_path: str, rel_path: str) -> str:
    """Resolve rel_path inside repo_path and raise StepError if it escapes."""
    resolved = os.path.realpath(os.path.join(repo_path, rel_path))
    root = os.path.realpath(repo_path)
    if not resolved.startswith(root + os.sep) and resolved != root:
        raise StepError(f"pr_creator: path escapes repo root: {rel_path!r}")
    return resolved


def _pick_branch_name(repo: git.Repo, base: str) -> str:
    existing = {h.name for h in repo.heads}
    if base not in existing:
        return base
    n = 1
    while f"{base}-retry-{n}" in existing:
        n += 1
    return f"{base}-retry-{n}"


def _build_pr_body(ctx: RunContext) -> str:
    files_changed = "\n".join(f"- `{p.path}`" for p in ctx.patches)
    issue_url = (
        f"https://github.com/{ctx.issue.repo_owner}/"
        f"{ctx.issue.repo_name}/issues/{ctx.issue.number}"
    )
    return (
        f"## Reasoning\n\n{ctx.plan.reasoning}\n\n"
        f"## Files changed\n\n{files_changed}\n\n"
        f"## Related issue\n\nCloses {issue_url}"
    )


def run(ctx: RunContext) -> None:
    repo = git.Repo(ctx.repo_path)

    default_branch = repo.active_branch.name
    if default_branch in ("main", "master"):
        pass  # we're on the base; that's fine — we'll branch off it

    base_branch_name = f"autopr/issue-{ctx.issue.number}"
    branch_name = _pick_branch_name(repo, base_branch_name)

    try:
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()
    except Exception as e:
        raise StepError(f"pr_creator: branch creation failed — {e}") from e

    if repo.active_branch.name in ("main", "master"):
        raise StepError(
            f"pr_creator: refusing to commit to {repo.active_branch.name}"
        )

    for patch in ctx.patches:
        full_path = _safe_path(ctx.repo_path, patch.path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(patch.modified_content)
        repo.index.add([patch.path])

    if not repo.index.diff("HEAD"):
        ctx.step_log.append("WARN pr_creator: nothing to commit, skipping PR")
        return

    repo.index.commit(
        f"[AutoPR] {ctx.issue.title}\n\nCloses #{ctx.issue.number}"
    )

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise StepError("pr_creator: GITHUB_TOKEN not set")

    origin = repo.remote("origin")
    original_url = origin.url
    auth_url = f"https://{token}@github.com/{ctx.issue.repo_owner}/{ctx.issue.repo_name}.git"
    try:
        origin.set_url(auth_url)
        origin.push(refspec=f"{branch_name}:{branch_name}")
    except Exception as e:
        safe_msg = str(e).replace(token, "<token>")
        raise StepError(f"pr_creator: push failed — {safe_msg}") from None
    finally:
        origin.set_url(original_url)

    gh = Github(token)
    gh_repo = gh.get_repo(f"{ctx.issue.repo_owner}/{ctx.issue.repo_name}")

    try:
        pr = gh_repo.create_pull(
            title=f"[AutoPR] {ctx.issue.title}",
            body=_build_pr_body(ctx),
            head=branch_name,
            base=default_branch,
        )
        ctx.pr_url = pr.html_url
        ctx.step_log.append(f"OK   pr_creator: {ctx.pr_url}")
    except Exception as e:
        raise StepError(f"pr_creator: PR creation failed — {e}") from e
