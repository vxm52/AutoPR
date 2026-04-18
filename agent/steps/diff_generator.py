import difflib
import subprocess
import tempfile
import os
from agent.context import RunContext, FilePatch


def make_diff(patch: FilePatch) -> str:
    return "".join(
        difflib.unified_diff(
            patch.original_content.splitlines(keepends=True),
            patch.modified_content.splitlines(keepends=True),
            fromfile=f"a/{patch.path}",
            tofile=f"b/{patch.path}",
        )
    )


def _dry_run_passes(diff: str, patch: FilePatch, repo_path: str) -> bool:
    if not diff:
        return True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(diff)
        patch_file = f.name
    try:
        target = os.path.join(repo_path, patch.path)
        result = subprocess.run(
            ["patch", "--dry-run", "-p1", target, patch_file],
            capture_output=True,
        )
        return result.returncode == 0
    finally:
        os.unlink(patch_file)


def run(ctx: RunContext) -> None:
    for patch in ctx.patches:
        diff = make_diff(patch)
        if not diff:
            ctx.step_log.append(f"SKIP diff_generator: {patch.path} — no changes")
            continue
        if _dry_run_passes(diff, patch, ctx.repo_path):
            ctx.diffs.append(diff)
            ctx.step_log.append(f"OK   diff_generator: {patch.path}")
        else:
            ctx.step_log.append(f"WARN diff_generator: {patch.path} — dry-run failed, skipping")
