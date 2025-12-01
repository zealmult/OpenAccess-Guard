# 🛡️ OpenAccess Guard

**Version 0.1.0**

Fine-grained access control, intelligent rate-limiting, and enterprise-grade security governance for Open WebUI.

The most advanced user-permission & security management filter available for Open WebUI — with features no other filter offers.

> 🚀 **Powered By [BreathAI](https://breathai.top)**  
> Free Claude 4.5/Gemini 3 Pro/GPT-5.1/DeepSeek/Llama/Grok4.1 API

---

## 📋 Table of Contents

- [Why OpenAccess Guard?](#-why-openaccess-guard)
- [Core Features](#-core-features)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration Guide](#-configuration-guide)
- [AI Assistant](#-ai-assistant)
- [Use Cases](#-use-cases)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Why OpenAccess Guard?

Open WebUI is powerful — but managing **who can do what, how often, and with which model** has always been a challenge.

**OpenAccess Guard** solves this by introducing a complete, enterprise-grade access control layer:

✅ **Governance** — Control who accesses what  
✅ **Security** — Ban users, whitelist emails, approve domains  
✅ **Fair Usage** — Multi-layer rate limiting (RPM, RPH, sliding windows)  
✅ **User Tiers** — Create free, paid, premium user levels  
✅ **Model Control** — Restrict expensive models to specific users  
✅ **Smart Fallback** — Downgrade users to cheaper models instead of blocking  

All in one unified, developer-friendly system.

---

## 🔥 Core Features

### 🧩 1. Dynamic Tier System

Create **unlimited user and model tiers** with different permission levels:

- **User Tiers (0-∞)**: Define free users, paid users, premium users, etc.
- **Model Tiers (0-∞)**: Categorize models by cost/capability
- **Flexible Matching**: Strict tier matching or custom whitelist/blacklist logic

*Example*: Tier 0 users get 10 RPM, Tier 1 users get 100 RPM, Tier 2 users unlimited.

### ⚡ 2. Intelligent Rate Limiting

Multi-layer limits that no other filter provides:

- **Requests Per Minute (RPM)**
- **Requests Per Hour (RPH)**
- **Sliding Window Quotas** (e.g., 100 requests per 24 hours)
- **Global or Per-Model** enforcement
- **User Priority vs Model Priority** logic

### 🛡️ 3. Fully Customizable Ban System

Create unlimited ban categories with custom messages:

```json
{
  "ban_reasons": [
    {
      "id": "ban_spam",
      "name": "Spam Violation",
      "msg": "Your account has been suspended for spamming.",
      "emails": ["spammer@example.com"]
    }
  ]
}
```

Perfect for communities, classrooms, and production environments.

### 🔑 4. Email-Based Access Control

Multiple layers of email control:

- **Domain Approval**: Only allow specific email providers (e.g., `@company.com`)
- **Whitelist Mode**: Strict access — only listed users allowed
- **Exemption List**: VIP users who bypass all restrictions

### 🌟 5. Smart Fallback System

Instead of blocking users who hit limits:

- Automatically downgrade them to a cheaper model
- Optionally show a notification
- Keep your service running smoothly

### 🎯 6. Context Clipping

Automatically limit conversation history to save tokens and costs:

- Configure clip count per tier
- Preserves system messages
- Reduces API costs

### 🤖 7. Built-in AI Assistant

**NEW in v0.1.0!** Get instant help with configuration:

- Explains all OAG features
- Generates JSON configurations for you
- Provides examples and troubleshooting
- Supports multiple AI models (Gemini, GLM, etc.)

---

## 📦 Installation

### Prerequisites

- Open WebUI instance
- Admin access

### Steps

1. **Download the Filter**
   ```bash
   wget https://raw.githubusercontent.com/zealmult/OpenAccess-Guard/main/oag.py
   ```

2. **Install in Open WebUI**
   - Go to **Admin Panel** → **Functions**
   - Click **+** to add a new function
   - Upload `oag.py` or copy-paste its contents
   - Save and enable the filter

3. **Configure via Web UI**
   - Open `index.html` in your browser ([Online Version](https://oag.breathai.top))
   - Configure your settings using the visual interface
   - Copy the generated JSON
   - Paste into Open WebUI → Functions → OpenAccess Guard → Valves → `config_json`

---

## 🚀 Quick Start

### Basic Setup (5 minutes)

1. **Enable the Filter**
   ```json
   {
     "base": {"enabled": true, "admin_effective": false}
   }
   ```

2. **Add Rate Limiting**
   ```json
   {
     "user_tiers": [{
       "tier_id": 0,
       "tier_name": "Free Users",
       "rpm": 10,
       "rph": 100,
       "emails": []
     }]
   }
   ```

3. **Done!** All users now limited to 10 requests/min, 100/hour.

### Advanced: Paid vs Free Tiers

```json
{
  "user_tiers": [
    {
      "tier_id": 0,
      "tier_name": "Free",
      "rpm": 5,
      "rph": 20,
      "emails": []
    },
    {
      "tier_id": 1,
      "tier_name": "Premium",
      "rpm": 100,
      "rph": 1000,
      "emails": ["premium@example.com"]
    }
  ]
}
```

---

## ⚙️ Configuration Guide

### User Tier System

Define different user levels with custom limits:

| Field | Description | Example |
|-------|-------------|---------|
| `tier_id` | Unique tier identifier | `0`, `1`, `2` |
| `tier_name` | Display name | `"Free"`, `"Premium"` |
| `emails` | Users in this tier | `["user@example.com"]` |
| `rpm` | Requests per minute | `10` |
| `rph` | Requests per hour | `100` |
| `win_time` | Sliding window (minutes) | `1440` (24h) |
| `win_limit` | Requests in window | `500` |
| `clip` | Context message limit | `10` |

### Model Tier System

Control access to specific models:

```json
{
  "model_tiers": [{
    "tier_id": 1,
    "tier_name": "Premium Models",
    "models": ["gpt-4", "claude-3-opus"],
    "mode_whitelist": true,
    "access_list": ["premium@example.com"]
  }]
}
```

### Ban System

Create custom ban categories:

```json
{
  "ban_reasons": [{
    "id": "ban_abuse",
    "name": "Abuse",
    "msg": "Account suspended for policy violation.",
    "emails": ["baduser@example.com"]
  }]
}
```

### Fallback System

Graceful degradation instead of blocking:

```json
{
  "fallback": {
    "enabled": true,
    "model": "gpt-3.5-turbo",
    "notify": true,
    "notify_msg": "Rate limit reached. Switched to basic model."
  }
}
```

---

## 🤖 AI Assistant

**New in v0.1.0!** Built-in AI assistant for configuration help.

### Features

- **24/7 Configuration Help**: Ask questions about any OAG feature
- **JSON Generation**: Automatically generates configurations
- **Examples Library**: Get real-world setup examples
- **Troubleshooting**: Debug configuration issues

### Usage

1. Open the configurator at `index.html`
2. Click **AI Assistant** in the sidebar
3. Ask questions like:
   - "How do I create paid vs free tiers?"
   - "Generate a config for 3 user levels"
   - "Explain the priority system"

### Configuration

Default settings:
- **API**: `api.breathai.top`
- **Models**: `gemini-2.5-flash`, `glm-4.5-air`
- **Streaming**: Enabled

Click ⚙ **Settings** to customize or add more models.

---

## 💡 Use Cases

### 1. Free vs Paid SaaS

```
Tier 0 (Free): 10 RPM, basic models only
Tier 1 (Pro): 100 RPM, all models
Tier 2 (Enterprise): Unlimited
```

### 2. Classroom/University

```
- Whitelist only @university.edu emails
- Limit students to 50 queries/day
- Professors get unlimited access (exemption)
```

### 3. Community/Discord Bot

```
- Ban spammers automatically
- Rate limit to prevent abuse
- Fallback to free models when busy
```

### 4. Cost Control

```
- Restrict GPT-4 to premium users only
- Clip context to 10 messages (save tokens)
- Auto-downgrade to GPT-3.5 on limits
```

---

## 🛠 Advanced Configuration

### Priority System

Control whether user limits or model limits take precedence:

- **User Priority**: User tier limits override model tier limits
- **Model Priority** (default): Strictest limit applies

### Global Limits

Pool limits across all models:

```json
{
  "global_limit": {"enabled": true},
  "user_tiers": [{
    "rph": 100  // 100 requests/hour TOTAL across all models
  }]
}
```

### Context Clipping

Save costs by limiting conversation history:

```json
{
  "user_tiers": [{
    "clip": 10  // Keep only last 10 messages
  }]
}
```

---

## 🤝 Contributing

Pull requests, feature ideas, and security discussions are welcome!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## ❤️ Support

Love this project? Here's how you can help:

- ⭐ **Star** the repository
- 🐛 **Report bugs** via Issues
- 💡 **Suggest features** via Discussions
- 📖 **Improve docs** via Pull Requests

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🔗 Links

- **GitHub**: [zealmult/OpenAccess-Guard](https://github.com/zealmult/OpenAccess-Guard)
- **Web Configurator**: [oag.breathai.top](https://oag.breathai.top)
- **Author**: [zealmult](https://github.com/zealmult)
- **Powered By**: [BreathAI](https://breathai.top) — Free AI API Access

---

**Made with ❤️ for the Open WebUI community**
