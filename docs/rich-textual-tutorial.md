# Rich + Textual 新手教程（结合 GitNow 讲解）

本教程用 GitNow 项目本身当教材，带你从零理解 Rich（终端富文本渲染库）和 Textual（基于 Rich 的 TUI 框架）。读完你应该能看懂 `gitnow/` 里每个文件在做什么，并动手做小改动。

- Rich 官方文档: https://rich.readthedocs.io/
- Textual 官方文档: https://textual.textualize.io/

---

## 1. 两个库的关系

一句话：**Rich 负责画**（颜色、对齐、样式化的文本），**Textual 负责管**（布局、事件、按键、焦点、异步）。

在 GitNow 里：

| 层 | 文件 | 干什么 |
|---|---|---|
| Rich | `gitnow/theme.py` | 集中定义颜色常量 |
| Rich | `panels/tree.py` / `viewer.py` | 用 `Text` 拼出带颜色的行 |
| Textual | `app.py` | `App` 子类：布局、按键绑定、后台任务 |
| Textual | `panels/*.py` | 自定义 Widget（面板、列表、弹窗） |
| Textual | `gitnow.tcss` | 用 CSS 描述布局和配色 |

---

## 2. Rich 基础：Text 与样式

Rich 里最常用的对象是 `Text`——一段可以分段上色的字符串。

### 2.1 最小例子

```python
from rich.text import Text

t = Text("hello ")
t.append("world", style="bold red")   # 后半段红色加粗
print(t)
```

`style` 是一个"样式字符串"，语法是 `粗体 颜色 on 背景色` 的组合，例如：

- `"bold"` 加粗
- `"red"` / `"#ff0000"` 前景色（支持 256 色名和 hex）
- `"on blue"` 设置背景色
- `"bold #7aa2f7"` 可以组合

### 2.2 GitNow 的用法

`theme.py` 把所有颜色收拢成常量（Tokyo Night 配色）：

```python
ACCENT_BLUE = "#7aa2f7"
ACCENT_GREEN = "#9ece6a"
...
```

`panels/tree.py:105` 的 `_label` 是典型例子——给文件树里的每个文件名上色：

```python
def _label(self, name: str, entry: FileEntry | None) -> Text:
    if entry is None:
        return Text(name, style=theme.FG_DIM)          # 无改动 → 暗灰
    letter = entry.wt_letter                            # git 状态字母 M/A/?/D
    color = theme.WT_COLORS.get(letter, theme.FG)
    return Text.assemble((f"{letter} ", f"bold {color}"), (name, theme.FG))
```

`Text.assemble(...)` 接收若干 `(文本, 样式)` 元组，一次性拼出多段不同颜色的 Text，比逐个 `append` 简洁。

`panels/viewer.py:115` 的 `_log_line` 同理，把 git log 的一行渲染成：橙色的短 SHA + 灰色日期 + 青色作者 + 绿色分支 + 普通正文。

**记住这个模式**：Textual 的任何 widget 都能接受 Text 或带 markup 的字符串，所以"让数据好看"这件事永远在 Rich 层完成。

### 2.3 Rich Console（脱离 TUI 也能用）

`__main__.py:13` 用的 `print()` 其实就是普通 print。如果想在命令行打印彩色错误，可以：

```python
from rich.console import Console
console = Console()
console.print("[bold red]错误[/bold red]: 不是 git 仓库")
```

`[bold red]...[/bold red]` 是 Rich 的 markup 写法，与 `Text` 对象二选一。GitNow 的 `notify(..., markup=False)` 传 False 就是故意关掉 markup 解析，防止 git 报错信息里的 `[xxx]` 被误当成标签。

---

## 3. Textual 核心：App、Widget、消息

### 3.1 一个 App 的三要素

看 `app.py:24` 的 `GitNowApp`，一个 Textual 应用只需要：

```python
class GitNowApp(App):
    TITLE = "GitNow"
    CSS_PATH = "gitnow.tcss"        # 1. 样式文件

    BINDINGS = [                    # 2. 全局按键
        Binding("q", "quit", "退出"),
        Binding("r", "refresh", "刷新"),
        ...
    ]

    def compose(self) -> ComposeResult:   # 3. 布局：声明有哪些 widget
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield FileTreePanel(id="tree-panel")
                yield StagedPanel(id="staged-panel")
            yield RightViewer(id="viewer")
        yield StatusBar(id="statusbar")
```

`compose` 就像写 HTML：`Horizontal`/`Vertical` 是容器（相当于 div），`yield` 出来的 widget 会被挂载。`id="..."` 相当于 HTML 的 id，之后可以用 CSS 选择器找到它。

启动入口在 `__main__.py`：

```python
GitNowApp(repo_path=str(path)).run()   # .run() 进入事件循环，阻塞直到退出
```

### 3.2 query_one：找到你的 widget

`app.py:65` 用 property 封装了查找：

```python
@property
def tree_panel(self) -> FileTreePanel:
    return self.query_one("#tree-panel", FileTreePanel)
```

`query_one("#id", 类型)` 是 Textual 的 DOM 查询，选择器语法和 CSS 一样（`#id`、`.class`、`WidgetType`）。之后代码里 `self.tree_panel.rebuild(...)` 就很自然。

### 3.3 消息（Message）：子组件向父级汇报

Textual 的事件模型是**冒泡的消息**。子 widget 遇到事情 → 发一条 Message → 沿着组件树向上传 → 父级用 `@on(...)` 接住。

GitNow 里最典型的链路：光标在文件树上移动时，右侧要显示 diff。

第 1 步，定义消息（`panels/tree.py:16`）：

```python
class FileHighlighted(Message):
    def __init__(self, panel: str, path: str) -> None:
        self.panel = panel
        self.path = path
        super().__init__()
```

第 2 步，widget 内部检测到事件后发送（`panels/tree.py:114`）：

```python
@on(Tree.NodeHighlighted)
def _node_highlighted(self, event):
    ...
    self.post_message(FileHighlighted("tree", data["path"]))
```

第 3 步，App 层接收（`app.py:163`）：

```python
@on(FileHighlighted)
def on_file_highlighted(self, event: FileHighlighted) -> None:
    self.set_selection(event.panel, event.path)   # → 触发右侧 diff 加载
```

这个"子组件发消息、App 统一调度"是 Textual 的核心设计。GitNow 里还有三条自定义消息，都在 `panels/viewer.py:19-30`：

- `CommitRequested`：用户在 log 里按 Enter → App 去拉取该 commit 的详情
- `BackRequested`：按 Esc → App 退回 log 视图
- `LogNearEnd`：光标滚到 log 末尾 3 条以内 → App 加载更多（无限滚动）

注意 `@on(Tree.NodeHighlighted)` 这种写法：Textual 内置 widget 自己也发消息，你用 `@on` 订阅即可，不用重写它的代码。

### 3.4 BINDINGS 与 action_ 方法

按键绑定约定：`Binding("space", "stage_toggle", ...)` 表示按 space 时调用 `action_stage_toggle` 方法——**action 名自动映射到 `action_<名字>` 方法**。`BINDINGS` 可以挂在 App（全局）或某个 widget（仅当它有焦点时）上，GitNow 两层都用了：`q`/`r`/`c` 是全局的，`space`/`d`/`e` 只在文件树上有焦点时生效。

widget 里通过 `self.app.xxx` 访问 App 实例（`panels/tree.py:137` 的 `self.app.stage_toggle(...)`），这是子 widget 调用业务逻辑的标准做法。

### 3.5 弹窗：push_screen + 回调

`app.py:330` 提交时弹输入框：

```python
self.push_screen(CommitModal(len(st.index_entries)), self._commit_callback)
```

`ModalScreen` 子类（见 `panels/modals.py`）盖在主界面之上；第二个参数是回调，当 screen 以 `self.dismiss(结果)` 关闭时，结果传给回调。`_commit_callback` 收到 `None` 表示用户取消，收到字符串就是 commit message。

---

## 4. 异步与后台线程：@work

Textual 是 asyncio 应用，**主线程里绝不能做慢操作**（比如调 git 子进程），否则界面卡死。Textual 提供了 `@work` 装饰器把方法丢进后台执行。

`app.py:104`：

```python
@work(thread=True, group="refresh", exclusive=True)
def refresh_all(self) -> None:
    st = gitbackend.status(self.repo_path)          # 子进程调 git，慢
    ...
    self.call_from_thread(self._apply_status, st, all_files)   # 回主线程
```

三个参数的含义：

- `thread=True`：放到线程池跑（不写则是协程）
- `group="refresh"`：任务分组
- `exclusive=True`：同组旧任务没跑完时，新调用会取消旧的——防止连续按 r 堆积一堆重复刷新

**关键规则**：后台线程里不能直接改 UI，要用 `self.call_from_thread(回调, 参数)` 切回主线程再更新界面。GitNow 所有 `@work(thread=True)` 方法都严格遵守这一点。

`on_mount` 里还有个定时器（`app.py:95`）：

```python
self.set_interval(3.0, self._auto_refresh)   # 每 3 秒自动刷新一次状态
```

`set_interval` 是 Textual 的周期任务，配合 `_busy` 标志避免和手动刷新/弹窗冲突。

---

## 5. TCSS：Textual 的 CSS

`gitnow.tcss` 决定布局和配色，语法接近 Web CSS：

```css
#main { height: 1fr; }              /* fr = 剩余空间的等分单位 */
#left { width: 40%; min-width: 34; }

FileTreePanel {
  height: 62%;
  background: #151c28;
  border: round #151c28;            /* 颜色和背景相同 = 看不见的边框 */
}
FileTreePanel:focus { border: round #7aa2f7; }   /* 有焦点时才显示边框 */
```

几个 GitNow 用到的要点：

- `1fr`：占剩余高度的等份。`#main` 占满除状态栏外的全部，左右面板再分它
- `dock: bottom`：状态栏停靠底部（`StatusBar` 那段）
- 类型选择器直接写 widget 类名（`FileTreePanel`），id 选择器写 `#名字`
- **小技巧**：GitNow 让未聚焦面板的边框颜色 == 背景色，这样面板切换焦点时只有边框变色、布局纹丝不动（见文件头注释）

改样式不用重启 Python 逻辑，`textual run --dev` 还支持热重载（见下节）。

---

## 6. 动手：跑起来 + 改一点东西

### 6.1 运行

```bash
# 开发模式（带控制台看日志/报错，强烈推荐）
pip install textual-dev
textual console            # 先开控制台
textual run --dev python -m gitnow          # 另一个终端

# 或者直接跑
python -m gitnow <仓库路径>
```

### 6.2 练习清单（由易到难）

1. **改颜色**：在 `theme.py` 里把 `ACCENT_ORANGE` 换成别的颜色，重启看 log 列表变化。
2. **加一个按键**：模仿 `r` → `refresh`，在 `app.py` 的 `BINDINGS` 里加 `Binding("R", "refresh_all_force", ...)`，实现"强制刷新"并 `notify("已强制刷新")`。
3. **改状态栏**：在 `panels/statusbar.py` 的内容里加上当前时间（提示：`set_interval(1.0, ...)`）。
4. **新消息练习**：给 `StagedPanel` 加双击/Enter 触发的 `FileOpened` 消息，在 `app.py` 里接收并 `notify` 路径。

### 6.3 调试技巧

- 所有 `print()` 输出会被 TUI 吞掉——用 `textual console` 配合 `self.log(...)` 或 `from textual import log` 查看
- `self.notify("消息")` 是右下角 toast，适合临时验证代码跑没跑到
- 布局问题先在 tcss 里加 `border: round red;` 把可疑容器框出来看

---

## 7. 速查表

| 概念 | Rich | Textual |
|---|---|---|
| 定位 | 富文本渲染 | 终端应用框架（内部用 Rich 渲染） |
| 核心对象 | `Text` / `Console` | `App` / `Widget` / `Message` |
| 上色 | `Text.append(s, style="bold red")` | widget 接受 Text 或 markup 字符串 |
| 布局 | — | 容器 widget + TCSS |
| 事件 | — | `post_message` / `@on` / `on_<事件>` |
| 按键 | — | `BINDINGS` + `action_xxx()` |
| 慢操作 | — | `@work(thread=True)` + `call_from_thread` |
| 弹窗 | — | `push_screen(screen, callback)` / `dismiss` |

GitNow 文件导航：

```
gitnow/
├── __main__.py      入口：检查仓库 → GitNowApp().run()
├── app.py           App 主类：布局、全局按键、消息调度、后台任务
├── gitbackend.py    纯 git 命令封装（不含任何 UI）
├── models.py        数据类：RepoStatus / FileEntry / LogEntry
├── theme.py         Rich 颜色常量
├── gitnow.tcss      Textual 样式
└── panels/
    ├── tree.py      左上：文件树（Tree widget + 自定义消息）
    ├── staged.py    左下：已暂存列表（OptionList）
    ├── viewer.py    右侧：log / diff / commit（OptionList + Static）
    ├── statusbar.py 底部状态栏
    └── modals.py    弹窗（提交 / 确认 / 帮助，ModalScreen）
```
