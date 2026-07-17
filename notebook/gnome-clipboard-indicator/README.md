# GNOME Shell Clipboard Indicator — GNOME 50 修复

## 问题

在 GNOME Shell 50.3 + Wayland 环境下，Clipboard Indicator 扩展的菜单内条目选择功能异常：

1. **鼠标点击条目** — 无反应，指示器不移动，剪贴板不更新
2. **方向键 + Enter 选择条目** — 同样不生效
3. **全局快捷键 Ctrl+F11/F12** — 正常工作

预期行为（Win+V 风格）：点击/选择哪个条目，该条目就成为新的默认项，后续 Ctrl+V 都粘贴该项。

## 根因分析

### 根因 1：鼠标点击不触发 activate 信号

GNOME 50 中 `PopupBaseMenuItem` 改用 `Clutter.ClickGesture` 处理点击。当条目位于 `St.ScrollView` 内部时，ScrollView 的滚动手势与点击手势冲突，`ClickGesture` 无法正常识别，导致 `activate` 信号永远不触发。

### 根因 2：剪贴板在 Popup Grab 期间更新失败

`_onMenuItemSelectedAndMenuClose` 在菜单打开（Popup Grab 持有）期间调用 `St.Clipboard.set_content()`。Wayland 下 Popup Grab 可能阻止剪贴板更新生效。

全局快捷键工作是因为菜单未打开，无 Grab 干扰。

## 修复方案

涉及文件：`extension.js`（扩展源码）

### 修改 1：新增 button-press-event 处理器

在 `_addEntry` 中为每个条目的 actor 直接连接 `button-press-event`，绕过 `ClickGesture`：

```js
menuItem.actor.connect('button-press-event', (actor, event) => {
    if (event.get_button() !== Clutter.BUTTON_PRIMARY)
        return Clutter.EVENT_PROPAGATE;
    if (PASTE_ON_SELECT) {
        this.#pasteItem(menuItem, true);
        this._onMenuItemSelectedAndMenuClose(menuItem, false);
    } else {
        this._onMenuItemSelectedAndMenuClose(menuItem, true);
    }
    return Clutter.EVENT_STOP;
});
```

### 修改 2：剪贴板更新移至菜单关闭后

`_onMenuItemSelectedAndMenuClose` 中先关闭菜单，再用 `setTimeout(50ms)` 延后调用 `_selectMenuItem`（与全局快捷键走完全相同的代码路径）：

```js
menuItem.menu.close();

if (autoSet !== false)
    setTimeout(() => this._selectMenuItem(menuItem), 50);
```

### 修改 3：#pasteItem 增加 keepSelection 参数

PASTE_ON_SELECT 模式下，选择条目后不应恢复旧剪贴板：

```js
#pasteItem (menuItem, keepSelection = false) {
    this.menu.close();
    const currentlySelected = keepSelection ? null : this._getCurrentlySelectedItem();
    // ... 粘贴逻辑 ...
    // 末尾：keepSelection=true 时跳过剪贴板恢复
    if (currentlySelected && currentlySelected.entry)
        this.#updateClipboard(currentlySelected.entry);
}
```

点击/Enter/V 键调用 `#pasteItem(menuItem, true)`（保留选择），粘贴按钮仍用 `#pasteItem(menuItem)`（一次性粘贴）。

### 修改 4：文本剪贴板统一使用 UTF-8 mimetype

`#updateClipboard` 写系统剪贴板时，对文本条目统一用 Wayland 标准 `text/plain;charset=utf-8`，而不是保留原始捕获时的 mimetype。防止某些终端（如 Ghostty）因 `text/plain` 缺少 charset 而将 UTF-8 多字节字符显示为 hex 转义序列。

```js
#updateClipboard (entry) {
    const mimetype = entry.isText() ? "text/plain;charset=utf-8" : entry.mimetype();
    this.extension.clipboard.set_content(CLIPBOARD_TYPE, mimetype, entry.asBytes());
    this.#updateIndicatorContent(entry);
}
```

## 部署

```bash
# 扩展安装路径
cp extension.js ~/.local/share/gnome-shell/extensions/clipboard-indicator@tudmotu.com/extension.js

# 重启 GNOME Shell
# Alt+F2 → r → 回车
```
