# GitNow

终端里的 Git 快速操作面板（Windows Terminal 优先）。纯调用 git 命令实现，无 libgit2 依赖。

布局（gitlogue 风格：色块分区，不画线框，只有活动面板有边框）：

    +------------------------+------------------------------+
    | 文件树 (左上)            | git log / 文件差异            |
    |   改动文件 + 新增文件     |  选中文件 -> 显示该文件 diff    |
    |   t 键切换为全部文件      |  无选中   -> 显示 git log      |
    +------------------------+                              |
    | 已暂存 staged (左下)     |                              |
    +------------------------+------------------------------+
    | 状态栏: 分支 / ahead-behind / 计数 / 键位提示             |
    +-------------------------------------------------------+

## 运行

    gitnow            # 在当前目录（须是 git 仓库）
    gitnow <仓库路径>  # 指定仓库
    python -m gitnow  # 等价

安装（一次性，editable 模式）：

    pip install -e C:\Users\Administrator\Documents\Code\GitNow -i https://pypi.tuna.tsinghua.edu.cn/simple

## 打包 exe

    build.bat

产物 dist\GitNow.exe（约 15 MB 单文件，免装 Python 直接跑），命令行用法与 gitnow 相同：`GitNow.exe [仓库路径]`。首次启动有几秒解压延迟属正常。重新打包：双击 build.bat（或手动执行其中的 PyInstaller 命令）。

## 键位

全局：
    Tab / h / l   切换面板（文件树 -> 已暂存 -> 右侧）
    t             文件树: 改动文件 <-> 全部文件
    r             刷新          Esc   取消选中 -> 显示 log
    c             提交（弹窗，Ctrl+S 提交）
    P             push          p     pull
    ?             帮助          q     退出

文件区（文件树 / 已暂存）：
    ↑↓ / j k      移动光标（移动即右侧显示 diff）
    Space         暂存 / 取消暂存
    a             全部暂存        u     全部取消暂存
    d             丢弃改动（需确认，未跟踪文件将被删除）
    e             用编辑器打开文件

右侧：
    j k / PgUp / PgDn  滚动（log 滚到底自动分页加载）
    Enter              log 里查看提交详情      Esc  返回 / 取消选中

## 说明

- 分支只在状态栏显示（当前活动分支 + ahead/behind），不支持切换
- 未实现：stash、分支切换/新建、merge/rebase（后续再加）
- push 无 upstream 时自动 `push -u origin <branch>`
- pull 使用 `--ff-only`，有分叉会报错提示（避免静默合并）
- 中文文件名依赖 `core.quotepath=false`（程序内部已自动加）
- 主题颜色在 `gitnow/gitnow.tcss`，文件状态色在 `gitnow/theme.py`

## 开发

    python tests\smoke_test.py   # 无头冒烟测试（临时仓库驱动 UI）
