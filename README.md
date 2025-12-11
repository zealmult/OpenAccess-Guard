# 🛡️ OpenAccess Guard

Fine‑grained access control, smart rate‑limiting, and governance for Open WebUI — managed entirely through a visual JSON configurator.

> 🚀 **Powered by [BreathAI](https://breathai.top)**  
> Free Claude 4.5 / Gemini 3 Pro / GPT‑5.1 / DeepSeek / Llama / Grok4.1 API

---

## 📌 What is OpenAccess Guard?

OpenAccess Guard (OAG) is a **filter function** for Open WebUI that sits between your users and all models.

It lets you centrally control:

- **Who** can access the system (email/domain, groups, bans)
- **What** they can use (which models / model groups)
- **How often** they can call it (RPM/RPH/sliding windows)
- **How much it costs you** (context clipping, model downgrades)

Everything is configured by editing a JSON object — which you can manage visually using `index.html`.

---

## ✨ Key Features

### 1. Group‑Based Permission Matrix

- **User Groups**: e.g. `free`, `pro`, `enterprise`, `admin`
- **Model Groups**: e.g. `basic_models`, `premium_models`, `experimental`
- **Permission Matrix**: per‑(user_group × model_group) settings:
  - enable/disable access
  - RPM / RPH
  - sliding window limits
  - context clip

You no longer fight with rigid “tiers” — you design the matrix that matches your product or organization.

### 2. Multi‑Layer Rate Limiting

- Requests per minute (`rpm`)
- Requests per hour (`rph`)
- Sliding window limits (`win_time` + `win_limit`)
- Per user group, per model group, or by default

Used together, this gives you SaaS‑style quotas with almost no code.

### 3. Email & Identity Control

- **Domain allow‑list** (`auth.providers`)  
  Only allow `@company.com`, `@university.edu`, etc.
- **Whitelist system** (`whitelist.emails`)  
  “Strict mode” — only listed users can access anything.
- **Exemption list** (`exemption.emails`)  
  VIPs / admins who bypass all other checks.

### 4. Flexible Ban System

- Define multiple ban reasons with custom messages.
- Attach users (emails) to any ban reason.
- OAG will short‑circuit the request with your message.

Good for communities, classrooms, shared infra or paid products.

### 5. Smart Fallback (Downgrade Instead of Block)

When a user hits limits:

- Automatically switch them to a cheaper/safer model.
- Optionally show a custom notification.

This keeps the UX smooth while still controlling cost.

### 6. Context Clipping

- Limit how many messages are kept in the conversation.
- Keep system messages intact.
- Reduce token usage and API cost without changing your frontend.

### 7. Built‑in AI Assistant

Inside `index.html` there is an “AI Assistant” tab:

- Ask in natural language what you want (e.g. “3 user tiers, GPT‑4 only for tier 2”).
- The assistant generates a valid OAG JSON config.
- Great for learning the schema and prototyping quickly.

---

## 📦 Installation

### 1. Get the Filter Script

```bash
wget https://raw.githubusercontent.com/zealmult/OpenAccess-Guard/main/oag.py
```

### 2. Install into Open WebUI

1. Open **Admin Panel → Functions**.
2. Click **+** to add a new function/filter.
3. Paste the contents of `oag.py` (or upload the file).
4. Save and make sure the filter is **enabled**.

### 3. Open the Visual Configurator

You have two options:

- Local: open `index.html` in a browser.  
- Online: visit **[oag.breathai.top](https://oag.breathai.top)**.

Then:

1. Go to the **Settings** page in the sidebar.
2. Configure groups, permissions, bans, fallback, logging, etc.
3. Scroll to the bottom and copy the generated **JSON Configuration**.
4. In Open WebUI, go to:  
   **Admin → Functions → OpenAccess Guard → Valves → `config_json`**  
   and paste the JSON.

You can always paste an existing JSON back into the editor, click **“Reload UI from JSON”**, and continue editing visually.

---

## ⚡ Quick Examples

### Example 1 — Basic Free Tier

Limit all anonymous / default users to 10 RPM on basic models.

```json
{
  "base": { "enabled": true, "admin_effective": false },
  "auth": { "enabled": false, "providers": [], "deny_msg": "" },
  "user_groups": [
    {
      "id": "default",
      "name": "Default Users",
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
      "name": "Basic Models",
      "models": ["gpt-3.5-turbo", "gemini-flash"]
    }
  ]
}
```

### Example 2 — Free vs Premium

```json
{
  "user_groups": [
    {
      "id": "free",
      "name": "Free Users",
      "priority": 0,
      "emails": [],
      "default_permissions": { "enabled": true, "rpm": 5, "rph": 50, "win_time": 0, "win_limit": 0, "clip": 8 },
      "permissions": {}
    },
    {
      "id": "premium",
      "name": "Premium Users",
      "priority": 10,
      "emails": ["vip@example.com"],
      "default_permissions": { "enabled": true, "rpm": 60, "rph": 600, "win_time": 0, "win_limit": 0, "clip": 20 },
      "permissions": {}
    }
  ],
  "model_groups": [
    {
      "id": "basic",
      "name": "Basic",
      "models": ["gpt-3.5-turbo", "gemini-flash"]
    },
    {
      "id": "premium_models",
      "name": "Premium Models",
      "models": ["gpt-4.1", "claude-3-opus"]
    }
  ]
}
```

You can then override permissions for `premium` on `premium_models` in the UI’s permission matrix.

---

## 🧩 Config Structure (High‑Level)

The full JSON config roughly looks like:

- `base` — enable switch, include admins or not.
- `auth` — email domain approval.
- `whitelist` / `exemption` — hard allow / bypass lists.
- `user_groups[]` — user segments with default + per‑model‑group permissions.
- `model_groups[]` — named model collections.
- `ban_reasons[]` — structured ban categories with messages and emails.
- `fallback` — downgrade model & notification text.
- `logging` — what to print in Open WebUI logs.
- `ads` — optional ad messages (event emitter).
- `custom_strings` — override internal error / deny messages.

You normally never hand‑edit all of this — use the UI and AI assistant, then paste.

---

## 🤖 AI Assistant

In the **AI Assistant** tab of `index.html` you can:

- Ask for explanations of any feature.
- Describe your product (e.g. “free + pro + team”) and let it generate a full config.
- Paste an existing config and ask “what does this do?”.

The assistant talks to an external API (defaults to BreathAI).  
You can configure API URL, key, models, and streaming in the ⚙ **Settings** panel.

---

## 💡 Typical Use Cases

- **SaaS / Internal Tool**
  - Free vs paid tiers
  - Per‑team or per‑department limits
  - Premium models restricted to paying users
- **University / Classroom**
  - Allow only `@university.edu`
  - Student quotas per day
  - Professors in an exemption group
- **Community / Discord / Bot**
  - Anti‑abuse limits
  - Ban categories with clear messages
  - Smart fallback to cheaper models

---

## 🤝 Contributing

Contributions are welcome:

1. Fork the repo.
2. Create a feature branch (`git checkout -b feature/xyz`).
3. Make your changes.
4. Open a Pull Request with a clear description.

Bug reports and feature ideas via **GitHub Issues** are also appreciated.

---

## 📝 License & Links

- License: **MIT** (see `LICENSE`)
- GitHub: `zealmult/OpenAccess-Guard`
- Web Configurator: `https://oag.breathai.top`
- Author: `@zealmult`

For Chinese documentation, see `README_CN.md`.

- **Powered By**: [BreathAI](https://breathai.top) — Free AI API Access

---

**Made with ❤️ for the Open WebUI community**
