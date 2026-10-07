# GitHub 项目协作基本流程

本文档总结团队成员参与 GitHub 项目协作时普遍需要使用的工作流程和命令。以下命令以 Windows CMD 为例。

## 1. 克隆项目仓库

首次参与项目时，将远程仓库克隆到本地：

```cmd
git clone https://github.com/Liekkaszjh/Software-Engineering-Term-Project.git
cd Software-Engineering-Term-Project
```

克隆操作会下载项目文件、提交历史和远程分支信息。

## 2. 查看仓库状态

开始工作前，查看当前分支和文件状态：

```cmd
git status
git branch --show-current
```

- `git status` 用于查看未跟踪、已修改和已暂存的文件。
- `git branch --show-current` 用于查看当前所在分支。

## 3. 同步主分支

切换到主分支并获取远程最新内容：

```cmd
git switch main
git pull --ff-only
```

在创建新工作分支前同步 `main`，可以减少后续发生代码冲突的可能性。

## 4. 创建工作分支

不要直接在 `main` 分支上开发。每项任务都应创建独立的工作分支：

```cmd
git switch -c 分支名称
```

例如：

```cmd
git switch -c feature/user-login
```

常见的分支名称前缀包括：

- `feature/`：开发新功能。
- `fix/`：修复缺陷。
- `docs/`：修改文档。
- `test/`：添加或调整测试。
- `refactor/`：重构代码。

分支名称应简短、清晰，并能够说明任务内容。

## 5. 修改并检查文件

完成代码或文档修改后，查看当前变化：

```cmd
git status
git diff
```

提交前应检查修改内容，避免提交无关文件、临时文件、密码、密钥或个人配置。

## 6. 将修改加入暂存区

添加指定文件或目录：

```cmd
git add 文件路径
git add 目录路径
```

例如：

```cmd
git add docs/requirements/functional_spec.md
```

添加完成后再次检查：

```cmd
git status
```

出现在 `Changes to be committed` 下的文件将被包含在下一次提交中。

## 7. 创建本地提交

将暂存区中的修改保存为一次本地提交：

```cmd
git commit -m "提交说明"
```

例如：

```cmd
git commit -m "docs: add functional specification"
```

常见的提交说明前缀包括：

- `feat:`：新增功能。
- `fix:`：修复问题。
- `docs:`：修改文档。
- `test:`：修改测试。
- `refactor:`：重构代码。
- `chore:`：调整配置、依赖或其他辅助内容。

一次提交应尽量只完成一项明确的修改，提交说明应简洁描述本次修改内容。

## 8. 推送工作分支

第一次推送当前工作分支时执行：

```cmd
git push -u origin 分支名称
```

例如：

```cmd
git push -u origin feature/user-login
```

`origin` 是远程仓库的默认名称，`-u` 用于建立本地分支与远程分支的跟踪关系。建立关系后，后续通常只需执行：

```cmd
git push
```

## 9. 创建 Pull Request

推送分支后，在 GitHub 仓库页面创建 Pull Request：

1. 打开项目仓库页面。
2. 点击 **Compare & pull request**，或者进入 **Pull requests** 页面后点击 **New pull request**。
3. 确认目标分支 `base` 为 `main`。
4. 确认来源分支 `compare` 为自己的工作分支。
5. 填写清晰的 PR 标题和描述。
6. 点击 **Create pull request**。

PR 描述一般应说明：

- 本次完成了什么工作。
- 修改了哪些主要模块。
- 如何验证修改结果。
- 是否存在需要审查者特别关注的内容。

## 10. 根据审查意见修改

如果审查者提出修改意见，继续在原工作分支中修改文件，然后执行：

```cmd
git add 文件路径
git commit -m "修改说明"
git push
```

新的提交会自动加入原来的 PR，不需要重新创建 PR。

## 11. 合并 PR

PR 通常需要满足以下条件后再合并：

- 代码或文档审查通过。
- 自动化测试和其他检查通过。
- 审查意见已经处理。
- 不存在尚未解决的合并冲突。

确认无误后，由具有权限的成员将 PR 合并到 `main` 分支。

## 12. 合并后同步本地仓库

PR 合并后，切换回本地主分支并获取最新内容：

```cmd
git switch main
git pull --ff-only
```

已经完成并合并的本地工作分支可以删除：

```cmd
git branch -d 分支名称
```

完成同步后，可以从最新的 `main` 分支创建下一个任务分支。

## 13. 工作流程总览

```text
首次克隆仓库
    ↓
同步本地 main
    ↓
为任务创建工作分支
    ↓
修改并检查文件
    ↓
git add 将修改加入暂存区
    ↓
git commit 创建本地提交
    ↓
git push 推送工作分支
    ↓
创建 Pull Request
    ↓
团队审查并根据意见修改
    ↓
合并到 main
    ↓
同步本地 main
```
