# GitNow — Git TUI 实现大纲 v0.2（已定稿并实现）

## 1. 目标
- 单仓库交互式 TUI：状态 / 暂存 / 提交 / 历史 / 差异 / push / pull 一屏完成
- 纯调用 git CLI 子进程，不用 libgit2 / gitpython
- Windows Terminal 优先；外观参考 gitlogue（色块分区、仅活动区画框），操作参考 gitui（键位）

## 2. 已定决策
- 技术栈：Python 3.14 + Textual 8.2.8（pip editable 安装，走 TUNA 镜像）
- 命名：GitNow，命令 `gitnow`（也支持 `python -m gitnow [仓库路径]`）
- 位置：C:\Users\Administrator\Documents\Code\GitNow
- push/pull 一期就有；分支只在状态栏显示当前活动分支（含 ahead/behind），不做切换
- stash / merge / rebase 暂不做

## 3. 布局（已实现）
- 左上 文件树：默认只显示改动+新增文件（含未跟踪逐文件展开），t 键切换全部文件（未改动文件灰色）
- 左下 staged：已暂存文件（绿色系状态标 A/M/D/R）
- 右侧：选中文件→diff（树面板=工作区 diff，staged 面板=cached diff，未跟踪=全绿新增 diff）；无选中→git log（滚动到底自动分页）；log 里 Enter→提交详情（元信息+stat+patch）
- 底部状态栏：分支 + ahead/behind + busy 指示 + 计数 + 紧凑键位条（完整键位在 ? 帮助）
- 色块：文件树=深灰蓝 / staged=深绿灰 / 右侧=近黑蓝 / 状态栏=亮条；失焦面板边框与底色同色（不可见但占位，避免布局跳动），仅焦点面板显示圆角彩色边框

## 4. git 命令映射（gitbackend.py 唯一出口，已实现）
- 状态：git status --porcelain=v2 --branch -z --untracked-files=all（XY 码 + 分支/ab 解析）
- 全部文件：git ls-files -z --cached --others --exclude-standard
- diff：--no-pager diff [-cached] --no-color -U3 -- :(literal)path；未跟踪用 diff --no-index /dev/null（失败时合成全加 diff）；numstat 无需，二进制由 diff 输出识别
- log：--no-pager log --date=format-local --pretty=%H%h%an%ad%d%s（TAB 分隔），--skip 分页
- 操作：add / restore --staged / restore / rm --cached（空仓库 unstage all）/ commit -m / push（无 upstream 自动 push -u origin）/ pull --ff-only
- 统一：GIT_PAGER=cat、core.quotepath=false、utf-8+errors=replace、路径 :(literal) 防通配符、stderr 进 toast

## 5. 键位（已实现，? 帮助面板同源）
- 全局：Tab/h/l 切焦点 | t 树模式 | r 刷新 | Esc 取消选中→log | c 提交 | P push | p pull | ? 帮助 | q 退出
- 文件区：j/k/↑↓ 移动（移动即看 diff）| Space 暂存/取消 | a 全部暂存 | u 全部取消 | d 丢弃（确认弹窗）| e 编辑器
- 右侧：j/k/PgUp/PgDn 滚动 | Enter 看提交详情 | Esc 返回
- 提交弹窗：Ctrl+S（或 Ctrl+Enter）提交、Esc 取消；确认弹窗 y/n/Esc

## 6. 架构（已实现）
```
gitnow/
  __main__.py    入口
  app.py         App：布局/焦点路由/全部动作/后台 worker/自动刷新(3s)
  gitbackend.py  git 子进程封装（唯一 git 出口）
  models.py      FileEntry(xy 码) / LogEntry / RepoStatus
  theme.py       文字渲染用颜色常量
  keys.py        键位表（状态栏 + 帮助共用）
  gitnow.tcss    色块主题（改颜色只动这里）
  panels/        tree.py / staged.py / viewer.py / statusbar.py / modals.py
tests/smoke_test.py  无头冒烟测试（temp 仓库驱动真实 UI 全流程）
```
- git 调用全部在 @work(thread=True) 后台线程，UI 不卡；写操作后统一 refresh+重载 log，尽量保持选中
- log/diff 大文本截断上限 5000 行

## 7. 验证状态
- 冒烟测试通过（两次）：状态解析→高亮看 diff→Space/a 暂存→c 弹窗 Ctrl+S 提交→log 列表→push 无远端容错→Enter 提交详情→Esc→d 丢弃未跟踪文件（确认）→t 全部文件切换
- 命令入口 `gitnow`（Python314\Scripts，已在 PATH）验证：非仓库目录给出中文报错退出
- 界面截图（docs/preview.svg）经视觉检查：三区色块、仅焦点蓝色圆角边框、中文渲染正常、键位条完整不截断
- PyInstaller 打包：dist\GitNow.exe（onefile ~15MB，PyInstaller 6.22.3）；pty 实测 TUI 渲染正常（diff/状态栏键位条都在）、q 干净退出（exit 0）、非仓库路径报错退出；一键重建用 build.bat（入口包装脚本 gitnow_exe.py，--collect-all textual + gitnow 保证 .tcss 主题进包）

## 8. 已知边界与后续
- 冲突文件（UU 等）只显示状态与原文，不做三方合并器
- 空仓库可提交但 push/pull 给出提示；pull --ff-only 分叉时报错不静默合并
- 后续候选：stash、分支切换/新建、merge/rebase、log graph、ignore 文件快捷键、打包 exe
