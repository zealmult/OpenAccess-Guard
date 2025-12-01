# 🛡️ OpenAccess Guard

为 Open WebUI 提供细粒度访问控制、智能速率限制和企业级安全治理。

Open WebUI 最先进的用户权限和安全管理过滤器 — 提供其他过滤器所没有的功能。

> 🚀 **由 [BreathAI](https://breathai.top) 驱动**  
> 免费使用 Claude 4.5/Gemini 3 Pro/GPT-5.1/DeepSeek/Llama/Grok4.1 API

---

## 📋 目录

- [为什么选择 OpenAccess Guard？](#-为什么选择-openaccess-guard)
- [核心功能](#-核心功能)
- [安装](#-安装)
- [快速开始](#-快速开始)
- [配置指南](#-配置指南)
- [AI 助手](#-ai-助手)
- [使用场景](#-使用场景)
- [贡献](#-贡献)
- [许可证](#-许可证)

---

## 🚀 为什么选择 OpenAccess Guard？

Open WebUI 功能强大 — 但管理**谁可以做什么、频率如何、使用哪个模型**一直是个挑战。

**OpenAccess Guard** 通过引入完整的企业级访问控制层解决了这个问题：

✅ **治理** — 控制谁访问什么  
✅ **安全** — 封禁用户、邮箱白名单、域名审批  
✅ **公平使用** — 多层速率限制（RPM、RPH、滑动窗口）  
✅ **用户等级** — 创建免费、付费、高级用户级别  
✅ **模型控制** — 将昂贵模型限制给特定用户  
✅ **智能降级** — 将用户降级到更便宜的模型而不是直接阻止  

所有功能统一在一个开发者友好的系统中。

---

## 🔥 核心功能

### 🧩 1. 基于组的权限系统

用灵活的 **用户组** 和 **模型组** 取代僵化的等级：

- **用户组**：对用户进行分类（例如：免费、高级、管理员）
- **模型组**：对模型进行分类（例如：基础、高级、实验性）
- **权限矩阵**：精确定义哪个用户组可以访问哪个模型组，以及限制条件。

*示例*：“免费用户”可以以 10 RPM 访问“基础模型”，但无法访问“高级模型”。“高级用户”可以以更高的限制访问所有内容。

### ⚡ 2. 智能速率限制

其他过滤器不提供的多层限制：

- **每分钟请求数 (RPM)**
- **每小时请求数 (RPH)**
- **滑动窗口配额**（例如，24 小时内 100 个请求）
- **全局或按模型**执行
- **用户优先 vs 模型优先**逻辑

### 🛡️ 3. 完全可自定义的封禁系统

创建无限封禁类别，带有自定义消息：

```json
{
  "ban_reasons": [
    {
      "id": "ban_spam",
      "name": "垃圾信息违规",
      "msg": "您的账户因发送垃圾信息已被暂停。",
      "emails": ["spammer@example.com"]
    }
  ]
}
```

非常适合社区、课堂和生产环境。

### 🔑 4. 基于邮箱的访问控制

多层邮箱控制：

- **域名审批**：仅允许特定邮箱提供商（例如，`@company.com`）
- **白名单模式**：严格访问 — 仅允许列出的用户
- **豁免列表**：绕过所有限制的 VIP 用户

### 🌟 5. 智能降级系统

不是阻止达到限制的用户，而是：

- 自动将他们降级到更便宜的模型
- 可选择显示通知
- 保持服务顺畅运行

### 🎯 6. 上下文裁剪

自动限制对话历史以节省 token 和成本：

- 为每个等级配置裁剪数量
- 保留系统消息
- 降低 API 成本

### 🤖 7. 内置 AI 助手

**v0.1.0 新功能！** 获取配置即时帮助：

- 解释所有 OAG 功能
- 为您生成 JSON 配置
- 提供示例和故障排除
- 支持多个 AI 模型（Gemini、GLM 等）

---

## 📦 安装

### 前提条件

- Open WebUI 实例
- 管理员访问权限

### 步骤

1. **下载过滤器**
   ```bash
   wget https://raw.githubusercontent.com/zealmult/OpenAccess-Guard/main/oag.py
   ```

2. **在 Open WebUI 中安装**
   - 进入 **管理员面板** → **函数**
   - 点击 **+** 添加新函数
   - 上传 `oag.py` 或复制粘贴其内容
   - 保存并启用过滤器

3. **通过 Web UI 配置**
   - 在浏览器中打开 `index.html`（[在线版本](https://oag.breathai.top)）
   - 使用可视化界面配置设置
   - 复制生成的 JSON
   - 粘贴到 Open WebUI → 函数 → OpenAccess Guard → Valves → `config_json`

---

## 🚀 快速开始

### 基本设置（5 分钟）

1. **启用过滤器**
   ```json
   {
     "base": {"enabled": true, "admin_effective": false}
   }
   ```

2. **配置组**
   ```json
   {
     "model_groups": [{
       "id": "basic_models",
       "name": "基础模型",
       "models": ["gpt-3.5-turbo", "gemini-flash"]
     }],
     "user_groups": [{
       "id": "free_users",
       "name": "免费用户",
       "emails": [],
       "default_permissions": {
         "enabled": true,
         "rpm": 10,
         "rph": 100
       }
     }]
   }
   ```

3. **完成！** 所有用户现在在基础模型上限制为 10 请求/分钟。

### 高级：付费 vs 免费
   ```json
   {
     "user_groups": [
       {
         "id": "free",
         "name": "免费用户",
         "default_permissions": {"enabled": true, "rpm": 5}
       },
       {
         "id": "premium",
         "name": "高级用户",
         "emails": ["vip@example.com"],
         "priority": 10,
         "default_permissions": {"enabled": true, "rpm": 100}
       }
     ]
   }
   ```

---

## ⚙️ 配置指南

### 用户组

定义用户类别及其权限：

| 字段 | 描述 | 示例 |
|-------|-------------|---------|
| `id` | 唯一标识符 | `"free_users"` |
| `name` | 显示名称 | `"免费等级"` |
| `priority` | 数字越大优先级越高 | `10` |
| `emails` | 此组中的用户 | `["user@example.com"]` |
| `default_permissions` | 所有模型的默认限制 | `{ "rpm": 10 }` |
| `permissions` | 特定模型组的限制 | `{ "gpt4_group": { "rpm": 2 } }` |

### 模型组

对模型进行分类：

```json
{
  "model_groups": [{
    "id": "expensive_models",
    "name": "GPT-4 & Claude 3",
    "models": ["gpt-4", "claude-3-opus"]
  }]
}
```

### 封禁系统

创建自定义封禁类别：

```json
{
  "ban_reasons": [{
    "id": "ban_abuse",
    "name": "滥用",
    "msg": "账户因违反政策已被暂停。",
    "emails": ["baduser@example.com"]
  }]
}
```

### 降级系统

优雅降级而不是阻止：

```json
{
  "fallback": {
    "enabled": true,
    "model": "gpt-3.5-turbo",
    "notify": true,
    "notify_msg": "已达到速率限制。切换到基础模型。"
  }
}
```

---

## 🤖 AI 助手

**v0.1.0 新功能！** 用于配置帮助的内置 AI 助手。

### 功能

- **24/7 配置帮助**：询问任何 OAG 功能的问题
- **JSON 生成**：自动生成配置
- **示例库**：获取实际设置示例
- **故障排除**：调试配置问题

### 使用

1. 在 `index.html` 打开配置器
2. 点击侧边栏中的 **AI 助手**
3. 询问问题，例如：
   - "如何创建付费 vs 免费等级？"
   - "为 3 个用户级别生成配置"
   - "解释优先级系统"

### 配置

默认设置：
- **API**：`api.breathai.top`
- **模型**：`gemini-2.5-flash`、`glm-4.5-air`
- **流式传输**：已启用

点击 ⚙ **设置** 以自定义或添加更多模型。

---

## 💡 使用场景

### 1. 免费 vs 付费 SaaS

```
Tier 0（免费）：10 RPM，仅基础模型
Tier 1（专业版）：100 RPM，所有模型
Tier 2（企业版）：无限制
```

### 2. 课堂/大学

```
- 仅将 @university.edu 邮箱列入白名单
- 限制学生每天 50 次查询
- 教授获得无限访问权限（豁免）
```

### 3. 社区/Discord 机器人

```
- 自动封禁垃圾信息发送者
- 速率限制以防止滥用
- 繁忙时降级到免费模型
```

### 4. 成本控制

```
- 仅将 GPT-4 限制给高级用户
- 将上下文裁剪为 10 条消息（节省 token）
- 达到限制时自动降级到 GPT-3.5
```

---

## 🛠 高级配置

### 优先级系统

控制用户限制还是模型限制优先：

- **用户优先**：用户等级限制覆盖模型等级限制
- **模型优先**（默认）：应用最严格的限制

### 全局限制

在所有模型中共享限制：

```json
{
  "global_limit": {"enabled": true},
  "user_tiers": [{
    "rph": 100  // 所有模型总共每小时 100 个请求
  }]
}
```

### 上下文裁剪

通过限制对话历史节省成本：

```json
{
  "user_tiers": [{
    "clip": 10  // 仅保留最后 10 条消息
  }]
}
```

---

## 🤝 贡献

欢迎 Pull Request、功能建议和安全讨论！

1. Fork 仓库
2. 创建功能分支（`git checkout -b feature/amazing`）
3. 提交更改（`git commit -m '添加惊人功能'`）
4. 推送到分支（`git push origin feature/amazing`）
5. 打开 Pull Request

---

## ❤️ 支持

喜欢这个项目？以下是您可以提供帮助的方式：

- ⭐ **给仓库加星**
- 🐛 **通过 Issues 报告错误**
- 💡 **通过 Discussions 建议功能**
- 📖 **通过 Pull Requests 改进文档**

---

## 📝 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)

---

## 🔗 链接

- **GitHub**：[zealmult/OpenAccess-Guard](https://github.com/zealmult/OpenAccess-Guard)
- **Web 配置器**：[oag.breathai.top](https://oag.breathai.top)
- **作者**：[zealmult](https://github.com/zealmult)
- **驱动方**：[BreathAI](https://breathai.top) — 免费 AI API 访问

---

**为 Open WebUI 社区用 ❤️ 制作**
