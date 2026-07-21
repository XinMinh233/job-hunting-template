# START HERE · 从这里开始

Welcome! This folder is a complete job-search system that runs inside
**Claude Code**. You don't need to know how to program to use it — you
talk to it, it does the bookkeeping.

欢迎！这个文件夹是一套完整的求职系统，运行在 **Claude Code** 里。
你不需要会编程 —— 你只管和它对话，记录和整理由它来做。

## 1. Install the two things you need · 安装两个必需工具

1. **Claude Code** — follow the official guide at
   https://code.claude.com/docs/en/quickstart (you'll need a Claude
   account). It gives you a terminal window where you talk to Claude.
2. **Git** (usually already installed on Mac; on Windows install from
   https://git-scm.com). Git is the system's memory — every change to
   your data is saved as a snapshot you can always go back to. Claude
   handles the git commands for you.

<!-- -->

1. **Claude Code** — 按官方指南 https://code.claude.com/docs/en/quickstart
   安装（需要一个 Claude 账号）。它提供一个可以和 Claude 对话的终端窗口。
2. **Git**（Mac 一般自带；Windows 从 https://git-scm.com 安装）。Git 是
   系统的记忆 —— 你的每次数据变动都会存成随时可回退的快照。git 命令由
   Claude 代劳，你不用学。

## 2. Open this folder in Claude Code · 用 Claude Code 打开本文件夹

In your terminal:

```
cd path/to/this/folder
claude
```

That's it — the folder IS the system. Every command below is something
you type into that Claude window.

就这样 —— 这个文件夹就是系统本身。下面所有命令都是在那个 Claude
窗口里输入的。

## 3. Run the onboarding interview · 运行入门访谈

Type:

```
/onboard
```

Claude will interview you — your background, work history, projects,
what jobs you want, where, in which languages, your salary floor, how
many hours a week you can spend. One question at a time; answer in
English or Chinese, whichever is comfortable. From your answers it
builds your personal files (they start as empty skeletons):

- `master.md` — your career fact base. Everything on any resume must
  trace back to here. **It only contains what you tell it — the system
  never invents facts about you.**
- `data/rubric.md` — how job postings get scored 0-100 *for you*.
- `data/scout-lanes.md` — where to hunt for postings in your market.
- your first base resume in `base/`.

输入 `/onboard`，Claude 会逐题访谈你 —— 背景、工作经历、项目、想找
什么工作、在哪里、用什么语言、薪资底线、每周能投入几小时。用中文或
英文回答都行。它会根据你的回答生成你的个人文件（初始都是空骨架）：

- `master.md` — 你的职业事实库。任何简历上的内容都必须能追溯到这里。
  **它只记录你亲口说的事实 —— 系统绝不替你编造。**
- `data/rubric.md` — 为你定制的职位打分规则（0-100）。
- `data/scout-lanes.md` — 在你的市场里去哪儿找职位。
- `base/` 里你的第一份基础简历。

## 4. The everyday rhythm · 日常节奏

After onboarding, the daily loop is a handful of commands:

| When | Type | What happens |
| ---- | ---- | ------------ |
| Morning | `/daily` | Reviews what changed, gives you 3 priorities for today |
| Found a posting yourself? | `/match <paste the JD>` | Scores it against your rubric, logs it |
| Ready to apply to one? | `/tailor <company>` | Writes a resume tailored to that posting |
| Once a day-ish | `/scout` | Claude searches the web for new postings in your lanes |
| Weekly (pick a fixed morning) | `/review` | Weekly review: what worked, one course-correction |

Everything else (mock interviews, resume audits, strategy) is in the
README's command reference — grow into it at your own pace. When
anything confuses you, just ask Claude in plain words: *"what does
/match do?"*, *"what is master.md for?"* — explaining this system is
part of its job.

入门之后，日常就是三五个命令：早上 `/daily` 看变化、拿到今天的三个
优先事项；自己看到职位就 `/match <粘贴JD>` 打分入库；决定投谁就
`/tailor <公司>` 生成定制简历；每天跑一次 `/scout` 让 Claude 上网
搜新职位；每周固定一个上午 `/review` 做周复盘。其余命令（模拟面试、
简历审计、策略）见 README 的命令速查表，按自己的节奏慢慢用起来。任何
地方看不懂，直接用大白话问 Claude："/match 是干什么的？" —— 解释这套
系统本身就是它的职责。

## The one rule that matters most · 最重要的一条规则

**Never let the system (or yourself) put anything on a resume you
can't defend out loud in an interview.** The whole design enforces
this: facts live in `master.md`, resumes only select and re-word them,
and the `/audit` command hunts for inflated claims. Trust the rule —
it is what makes the resumes this system produces safe to send.

**绝不让系统（或你自己）把面试里说不出口的内容写上简历。** 整套设计
都在强制这一点：事实只存在 `master.md`，简历只做筛选和改写，`/audit`
命令专门猎杀夸大表述。相信这条规则 —— 它是这套系统产出的简历敢投出
去的根本原因。
