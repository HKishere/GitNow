"""Headless smoke test: drives GitNowApp against a temp repo via textual's pilot."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sh(*args: str, cwd) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def commit_count(cwd) -> int:
    return int(sh("rev-list", "--count", "HEAD", cwd=cwd))


async def wait_for(cond, pilot, timeout: float = 15.0, what: str = ""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond():
                return
        except Exception:
            pass
        await pilot.pause(0.05)
    raise AssertionError(f"timeout waiting for: {what or cond}")


async def main() -> None:
    from gitnow.app import GitNowApp
    from gitnow.panels.staged import StagedPanel
    from gitnow.panels.viewer import RightViewer
    from textual.widgets import OptionList

    tmp = Path(tempfile.mkdtemp(prefix="gitnow_smoke_"))
    try:
        sh("init", "-b", "main", cwd=tmp)
        sh("config", "user.email", "t@example.com", cwd=tmp)
        sh("config", "user.name", "T", cwd=tmp)
        (tmp / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
        sh("add", ".", cwd=tmp)
        sh("commit", "-m", "init", cwd=tmp)
        # worktree changes: modified + untracked + untracked in subdir
        (tmp / "a.txt").write_text("line1\nline2 changed\n", encoding="utf-8")
        (tmp / "b_new.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp / "src").mkdir()
        (tmp / "src" / "c.txt").write_text("nested new file\n", encoding="utf-8")

        app = GitNowApp(repo_path=str(tmp))
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_for(
                lambda: app.status is not None and app.status.entries, pilot,
                what="initial status",
            )
            st = app.status
            paths = {e.path for e in st.worktree_entries}
            assert {"a.txt", "b_new.py", "src/c.txt"} <= paths, paths
            assert st.head == "main"

            # cursor movement -> diff view (first row may be a directory node)
            app.set_focus(app.tree_panel)
            for _ in range(8):
                await pilot.press("j")
                try:
                    await wait_for(
                        lambda: app.viewer.mode == "diff", pilot, timeout=1.5
                    )
                    break
                except AssertionError:
                    continue
            else:
                await wait_for(
                    lambda: app.viewer.mode == "diff", pilot, what="diff shown"
                )
            assert app.selected is not None and app.selected[0] == "tree"

            # stage the highlighted file
            await pilot.press("space")
            await wait_for(
                lambda: app.status and len(app.status.index_entries) == 1, pilot,
                what="one staged file",
            )
            await wait_for(
                lambda: app.query_one("#staged-panel", StagedPanel).option_count == 1,
                pilot, what="staged panel updated",
            )

            # stage all
            await pilot.press("a")
            await wait_for(
                lambda: app.status and len(app.status.index_entries) == 3, pilot,
                what="all staged",
            )

            # commit via modal
            await pilot.press("c")
            await wait_for(lambda: app.screen.__class__.__name__ == "CommitModal", pilot, what="commit modal")
            await pilot.press(*list("smoke-commit"))
            await pilot.press("ctrl+s")
            await wait_for(lambda: commit_count(tmp) == 2, pilot, what="commit created")

            # esc -> log view with 2 entries
            await pilot.press("escape")
            await wait_for(lambda: app.viewer.mode == "log", pilot, what="back to log")
            log_list = app.viewer.log_list
            await wait_for(lambda: log_list.option_count >= 2, pilot, what="log entries")
            assert isinstance(log_list, OptionList)

            # push with no remote -> error toast, but must not crash / stay busy
            await pilot.press("P")
            await wait_for(lambda: app._busy == 0, pilot, what="push finished")
            await pilot.pause(0.2)

            # open commit detail from log
            await pilot.press("enter")
            await wait_for(lambda: app.viewer.mode == "commit", pilot, what="commit detail")
            await pilot.press("escape")
            await wait_for(lambda: app.viewer.mode == "log", pilot, what="back to log 2")

            # discard untracked file via confirm modal
            (tmp / "d_tmp.txt").write_text("x\n", encoding="utf-8")
            app.refresh_all()
            await wait_for(
                lambda: app.status and any(e.path == "d_tmp.txt" for e in app.status.entries),
                pilot, what="new untracked visible",
            )
            app.discard_request("tree", "d_tmp.txt")
            await pilot.pause(0.2)
            await pilot.press("y")
            await wait_for(lambda: not (tmp / "d_tmp.txt").exists(), pilot, what="file discarded")

            # tree mode toggle (changes -> all)
            await pilot.press("t")
            await wait_for(
                lambda: app.tree_panel.mode == "all"
                and app.tree_panel._file_nodes.get("a.txt") is not None,
                pilot, what="all-files mode",
            )
            await pilot.press("t")

            # screenshot for humans
            docs = ROOT / "docs"
            docs.mkdir(exist_ok=True)
            if hasattr(app, "save_screenshot"):
                app.save_screenshot(str(docs / "preview.svg"))
                print("screenshot:", docs / "preview.svg")

        print("SMOKE PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
