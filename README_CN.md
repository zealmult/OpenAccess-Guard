# 🛡️ OpenAccess Guard

为 Open WebUI 提供细粒度访问控制、智能限流和治理能力，并且**通过一个可视化 JSON 配置器一键管理**。

> 🚀 **由 [BreathAI](https://breathai.top) 驱动**  
> 免费使用 Claude 4.5 / Gemini 3 Pro / GPT‑5.1 / DeepSeek / Llama / Grok4.1 API

---

## 📌 OpenAccess Guard 是什么？

OpenAccess Guard（简称 **OAG**）是一个运行在 Open WebUI 中的 **过滤器函数**。

它位于「用户 → 模型」的中间层，用一份 JSON 做到：

- 控制 **谁** 可以访问（邮箱 / 域名 / 用户组 / 封禁）
- 控制 **能用什么**（模型组 / 高级模型）
- 控制 **调用频率**（RPM / RPH / 滑动窗口）
- 控制 **成本 & 风险**（上下文裁剪 / 智能降级 / 日志）

所有配置都在一份 JSON 里完成，并可以通过 `index.html` 可视化编辑。

---

## ✨ 主要特性

### 1. 基于「用户组 × 模型组」的权限矩阵

- **用户组**：例如 `free`、`pro`、`enterprise`、`admin`
- **模型组**：例如 `basic_models`、`premium_models`、`experimental`
- **权限矩阵**：对每一个「用户组 × 模型组」设置：
  - 是否允许访问
  - 每分钟 / 每小时请求数
  - 滑动时间窗限制
  - 上下文裁剪数量

不再被死板的「Tier 等级」绑死，你可以自由搭积木设计自己的权限体系。

### 2. 多层限流系统

- 每分钟请求数（`rpm`）
- 每小时请求数（`rph`）
- 滑动窗口配额（`win_time` + `win_limit`）
- 支持默认权限 + 针对某一模型组单独覆盖

非常适合做 SaaS 配额、试用限制、防滥用等场景。

### 3. 邮箱 / 身份管控

- **认证邮箱域名**（`auth.providers`）  
  仅允许 `@company.com`、`@university.edu` 等登录使用。
- **白名单模式**（`whitelist.emails`）  
  完全严格：只有白名单里的用户可以访问任何模型。
- **豁免用户**（`exemption.emails`）  
  超级 VIP / 管理员，绕过所有限制。

### 4. 可配置封禁系统

- 支持多条「封禁理由」，每条有独立的提示语。
- 每条理由下可挂多个用户邮箱。
- 命中后直接短路请求，返回你设置的封禁提示。

适合：社区、学校机房、共享服务、收费产品等场景。

### 5. 智能降级（Smart Fallback）

当用户触发限流时：

- 自动将请求切换到一个更便宜/更安全的模型（如从 GPT‑4 降到 GPT‑3.5）。
- 可选显示自定义提示语。

体验上不「直接拒绝」，而是「悄悄降级」，既友好又省钱。

### 6. 上下文裁剪（Context Clip）

- 限制对话中最多保留多少条历史消息。
- 自动跳过系统消息，避免破坏系统提示。
- 有效降低 token 使用 & API 成本。

### 7. 内置 AI 配置助手

在 `index.html` 里有一个独立的 **AI 助手** 页面：

- 用自然语言描述你想要的「权限模型」。
- 由 AI 自动生成一份完整的 OAG JSON 配置。
- 也可以把现有 JSON 丢进去让它帮你解释。

后端默认调用 BreathAI，可在设置中自定义 API 地址 / Key / 模型列表。

---

## 📦 安装步骤

### 1. 获取过滤器脚本

```bash
wget https://raw.githubusercontent.com/zealmult/OpenAccess-Guard/main/oag.py
```

### 2. 安装到 Open WebUI

1. 打开 **Admin 管理面板 → Functions**。
2. 点击 **+** 新增一个函数 / 过滤器。
3. 将 `oag.py` 的内容粘贴进去（或上传文件）。
4. 保存，并确保过滤器 **已启用**。

### 3. 打开可视化配置器

两种方式：

- 本地：在浏览器中直接打开 `index.html`  
- 在线：访问 **[oag.breathai.top](https://oag.breathai.top)**

然后：

1. 在左侧选择 **配置（Settings）** 页面。
2. 配置用户组 / 模型组 / 权限矩阵 / 封禁 / 降级 / 日志等。
3. 滚动到页面底部，复制 **JSON Configuration**。
4. 回到 Open WebUI：  
   **Admin → Functions → OpenAccess Guard → Valves → `config_json`**  
   将 JSON 粘贴进去并保存。

之后如果想改配置，只要：

- 把当前 JSON 粘贴回配置器  
- 点击 **「从 JSON 重载 UI」**  
- 继续可视化编辑即可。

---

## ⚡ 快速示例

### 示例 1：基础免费用户

限制所有默认用户在基础模型上 10 RPM。

```json
{
  "base": { "enabled": true, "admin_effective": false },
  "auth": { "enabled": false, "providers": [], "deny_msg": "" },
  "user_groups": [
    {
      "id": "default",
      "name": "默认用户",
      "priority": 0,
      "emails": [],
      "default_permissions": {
        "enabled": true,
        "rpm": 10,
        "rph": 100,
        "win_time": 0,
        "win_limit": 0,
        "clip": 0
      },
      "permissions": {}
    }
  ],
  "model_groups": [
    {
      "id": "basic_models",
      "name": "基础模型",
      "models": ["gpt-3.5-turbo", "gemini-flash"]
    }
  ]
}
```

### 示例 2：免费 vs 高级

```json
{
  "user_groups": [
    {
      "id": "free",
      "name": "免费用户",
      "priority": 0,
      "emails": [],
      "default_permissions": {
        "enabled": true,
        "rpm": 5,
        "rph": 50,
        "win_time": 0,
        "win_limit": 0,
        "clip": 8
      },
      "permissions": {}
    },
    {
      "id": "premium",
      "name": "高级用户",
      "priority": 10,
      "emails": ["vip@example.com"],
      "default_permissions": {
        "enabled": true,
        "rpm": 60,
        "rph": 600,
        "win_time": 0,
        "win_limit": 0,
        "clip": 20
      },
      "permissions": {}
    }
  ],
  "model_groups": [
    {
      "id": "basic",
      "name": "基础模型",
      "models": ["gpt-3.5-turbo", "gemini-flash"]
    },
    {
      "id": "premium_models",
      "name": "高级模型",
      "models": ["gpt-4.1", "claude-3-opus"]
    }
  ]
}
```

你可以在 UI 的「权限矩阵」中，为 `premium` 用户组在 `premium_models` 上单独设置更高的限流。

---

## 🧩 配置结构（概览）

完整 JSON 大致包含：

- `base`：开关、是否对管理员生效。
- `auth`：邮箱域名认证。
- `whitelist` / `exemption`：白名单 / 豁免用户列表。
- `user_groups[]`：用户组 & 默认 + 按模型组的权限。
- `model_groups[]`：模型分组。
- `ban_reasons[]`：封禁理由 + 用户列表。
- `fallback`：智能降级目标模型 + 文案。
- `logging`：日志开关（OAG / inlet / outlet / stream / user_dict）。
- `ads`：可选广告内容（通过 event emitter 注入）。
- `custom_strings`：内部拒绝 / 提示文案的自定义。

通常不需要手写所有字段，推荐通过 UI + AI 助手生成。

---

## 🤖 AI 助手使用

1. 打开 `index.html`。
2. 点击侧边栏的 **AI 助手**。
3. 可以这样提问：
   - 「帮我设计一个 免费 / 专业 / 企业 三个等级的配置。」
   - 「限制所有普通用户每天最多 100 次请求。」
   - 「解释这份 JSON 每一段在干什么。」

默认会使用 BreathAI 的 API，你可以在 ⚙ 设置 中填写自己的 API 地址和 Key，并自定义模型列表。

---

## 💡 典型场景

- **SaaS / 内部工具**
  - 免费 / 专业 / 团队版分级
  - 针对团队 / 部门设置不同限流
  - 高级模型仅对付费用户开放
- **学校 / 实验室 / 机房**
  - 仅允许学校邮箱登录
  - 学生每天固定配额
  - 老师 / 助教在豁免组
- **社区 / 机器人 / 公共面板**
  - 防滥用 / 防刷屏限流
  - 主动封禁恶意用户
  - 忙碌时自动降级到便宜模型

---

## 🤝 贡献方式

欢迎：

- 提交 Pull Request
- 在 Issues 中反馈 bug / 提需求
- 改进文档 / 补充示例配置

开发流程：

1. Fork 本仓库
2. 创建分支（`git checkout -b feature/xxx`）
3. 提交改动
4. 提交 Pull Request 简要说明。

---

## 📝 许可证 & 链接

- 许可证：**MIT**（详见 `LICENSE`）
- GitHub：`zealmult/OpenAccess-Guard`
- Web 配置器：`https://oag.breathai.top`
- 作者：`@zealmult`

英文说明请参见 `README.md`。

- **驱动方**：[BreathAI](https://breathai.top) — 免费 AI API 访问

---

**为 Open WebUI 社区用 ❤️ 制作**
