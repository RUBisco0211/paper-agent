# Paper Agent

Paper Agent 管理个人论文库、项目范围和基于论文证据的 Agent 阅读会话。它是多用户系统，但每个用户的数据与交互彼此隔离。

## Library

**Paper**:
按上传 PDF 文件身份全局去重的论文。它承载共享的论文事实和解析产物，但本身不授予任何用户可见性。
_Avoid_: User Paper, document copy

**User Paper**:
用户将一个 Paper 纳入个人论文库的关系，也是未来承载用户级阅读状态的边界。
_Avoid_: Paper ownership, private Paper copy

**Project**:
用户从个人论文库中逐步汇集论文的命名范围。
_Avoid_: Workspace, tenant, folder

**Project Paper**:
一个 User Paper 对所属用户 Project 的成员关系。
_Avoid_: Paper copy, embedded paper ID list

## Processing and Evidence

**Ingestion Job**:
一次把 Paper 转换为可读、可检索能力的后台处理尝试。
_Avoid_: Agent run, parse status

**Capability**:
Paper 当前已经具备的独立使用能力，例如元数据、全文、关键词索引或向量索引。
_Avoid_: Paper status

**Chunk**:
从论文原子内容合并或细分得到的可检索证据单元，保留回到原文所需的位置关系。
_Avoid_: Page, MinerU block

**Citation**:
Agent 回答对授权检索证据的稳定引用。
_Avoid_: Free-form reference, bibliography item

## Conversation

**Session**:
属于一个用户的 Agent 阅读对话边界；它可以面向个人全库，也可以受一个 Project 的论文范围约束。
_Avoid_: Chat room, Agent run

**Entry**:
Session 中一个不可变、可分支的历史节点，包括消息、工具结果、模型变化或上下文压缩等行为。
_Avoid_: Message row, event envelope, run record

**Pending Message**:
已被 Session 接受、但尚未投递给 Agent 并成为 Entry 的用户输入。
_Avoid_: User Entry, concurrent run

**Steering**:
在当前 Agent 工作的下一个安全边界投递、用于改变当前方向的 Pending Message。
_Avoid_: Hard interrupt, parallel prompt

**Follow-up**:
当前 Agent 回答原本准备结束时，作为下一轮输入投递的 Pending Message。
_Avoid_: Steering, parallel prompt
