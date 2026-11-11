"""Headless test: h/l (left/right) collapse / expand folders in the file tree.

驱动临时仓库验证：
  1. 光标在已展开的文件夹上按 h/← → 折叠
  2. 光标在已折叠的文件夹上按 l/→ → 展开
  3. 光标在文件上按 h/l 仍保持全局行为（切换面板焦点）
"""

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

    tmp = Path(tempfile.mkdtemp(prefix="gitnow_fold_"))
    try:
        sh("init", "-b", "main", cwd=tmp)
        sh("config", "user.email", "t@example.com", cwd=tmp)
        sh("config", "user.name", "T", cwd=tmp)
        (tmp / "a.txt").write_text("line1\n", encoding="utf-8")
        sh("add", ".", cwd=tmp)
        sh("commit", "-m", "init", cwd=tmp)
        # 两层目录结构：src/（含子目录 sub/）+ 顶层文件，保证树里有文件夹节点
        (tmp / "src" / "sub").mkdir(parents=True)
        (tmp / "src" / "c.txt").write_text("nested\n", encoding="utf-8")
        (tmp / "src" / "sub" / "d.txt").write_text("deeper\n", encoding="utf-8")

        app = GitNowApp(repo_path=str(tmp))
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_for(
                lambda: app.status is not None and app.status.entries, pilot,
                what="initial status",
            )
            tree = app.tree_panel
            app.set_focus(tree)
            await pilot.pause(0.1)

            # 找到 src/ 目录节点（光标直接移过去）
            src_node = next(n for n in tree._dir_nodes if n.label.plain == "src")
            assert src_node.is_expanded, "rebuild 后目录应默认展开"
            tree.select_node(src_node)
            await pilot.pause(0.1)
            assert tree.cursor_node is src_node

            # 1) h / left：折叠；对已折叠的文件夹再按一次不切换焦点
            await pilot.press("h")
            await wait_for(lambda: not src_node.is_expanded, pilot, what="h collapses src/")
            await pilot.press("left")
            await pilot.pause(0.1)
            assert not src_node.is_expanded, "已折叠的文件夹不应被 left 改变状态"
            assert app.focused is tree, "文件夹上按 left 不应切走焦点"

            # 2) l / right：展开；对已展开的文件夹再按一次不切换焦点
            await pilot.press("l")
            await wait_for(lambda: src_node.is_expanded, pilot, what="l expands src/")
            await pilot.press("right")
            await pilot.pause(0.1)
            assert src_node.is_expanded, "已展开的文件夹不应被 right 改变状态"
            assert app.focused is tree, "文件夹上按 right 不应切走焦点"

            # 3) 光标在文件上时 h/l 仍是切换面板
            file_node = tree._file_nodes["src/c.txt"]
            tree.select_node(file_node)
            await pilot.pause(0.1)
            await pilot.press("h")
            await wait_for(lambda: app.focused is not tree, pilot, what="h on file cycles focus")
            focused_after_h = app.focused
            await pilot.press("l")  # 在新面板上再按 l，应继续沿循环切换面板
            await pilot.pause(0.2)
            assert app.focused is not focused_after_h, "其他面板上 l 仍应切换面板"
            app.set_focus(tree)

            # 4) 刷新重建树后默认仍全部展开，h/l 行为不变
            #    注意：refresh_all 的后台 rebuild 是异步的，必须等 _busy 归零
            #    且树非空（all([]) 恒真，不能只等 all expanded），否则会拿旧
            #    树的失效节点引用按键
            app.refresh_all()
            await wait_for(
                lambda: app._busy == 0
                and app.status
                and any(e.path == "src/c.txt" for e in app.status.entries)
                and len(tree._dir_nodes) > 0
                and all(n.is_expanded for n in tree._dir_nodes),
                pilot, what="rebuild settled, all dirs expanded",
            )
            await pilot.pause(0.3)
            src_node2 = next(n for n in tree._dir_nodes if n.label.plain == "src")
            tree.select_node(src_node2)
            await pilot.pause(0.1)
            assert tree.cursor_node is src_node2, "光标应停在新建的 src 节点上"
            await pilot.press("h")
            await wait_for(lambda: not src_node2.is_expanded, pilot, what="h works after rebuild")
            await pilot.press("l")
            await wait_for(lambda: src_node2.is_expanded, pilot, what="l works after rebuild")

        print("FOLD PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
