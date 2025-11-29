## 🛡️ OpenAccess Guard

Fine-grained access control, intelligent rate-limiting, and world-class security governance for Open WebUI.

The most advanced user-permission & security management plugin available for Open WebUI —
with features no other plugin offers.

> (ad)
Powered By BreathAI
Free Claude 4.5/Gemini 3 Pro/GPT-5.1/DeepSeek/Llama/Grok4.1 API

---

## 🚀 Why OpenAccess Guard?

Open WebUI is powerful — but managing who can do what, how often, and with which model
has always been a challenge.

Until now.

OpenAccess Guard introduces a complete, enterprise-grade access layer that brings:
✔ Governance
✔ Security
✔ Fair usage
✔ User-tier systems
✔ Customizable restrictions
✔ Ban & approval workflows

All in one unified, developer-friendly system.

---

## 🔥 Core Features

### 🧩 1. Fine-Grained User Permissions

Control access at the highest precision:
	•	Per-email access rules
	•	Model-level permissions
	•	Custom approval requirements
	•	Bypass modes for trusted users

No more one-size-fits-all access.

### ⚡ 2. Intelligent Rate Limiting (Per User / Per Model / Sliding Window)

OpenAccess Guard is the only plugin offering multi-layer limits:
	•	Requests per minute
	•	Requests per hour
	•	Long sliding-window quotas
	•	Plus-tier limits for premium users
	•	Global or per-model enforcement

Designed for environments where stability matters.

### 🛡️ 3. Fully Customizable Ban System

Create your own categories of restriction:
	•	Temporary bans
	•	Permanent bans
	•	Custom reasons & messages
	•	Email-list driven control
	•	Automatically enforce via inlet()

Perfect for communities, classrooms, and production environments.

### 🔑 4. Email-Based Approval Mode

Enable a “whitelist-only” mode:

Only approved emails can access advanced models.

Great for:
	•	Paid customers
	•	Internal teams
	•	Restricted research models
	•	Classroom or lab access

### 🌟 5. User Tiers (Plus / Normal / Bypass)

Design your own user ecosystem:
	•	Plus users get higher limits
	•	Bypass users skip all restrictions
	•	Normal users follow default rules

Flexible, scalable, clean.

### 🧠 6. Administrator-Focused Control

Designed to solve real problems admins face daily:
	•	Abuse prevention
	•	Preventing resource hogging
	•	Protecting expensive models
	•	Ensuring fair access
	•	Enforcing platform rules

---

## 🧬 Architecture Overview

Request → OpenAccess Guard → 
    (Approval Check → Ban Check → Bypass Check → Plus Check → Rate Limit) →
        Success or fallback to backup model

Your system stays healthy, stable, and abuse-free.

---

## ⚙️ Configuration Guide

OpenAccess Guard exposes a full UI with editable settings, including:

### 🔒 Access Rules

```
approved_user_emails
approval_required
bypass_user_emails
plus_user_emails
```

### 🚦 Rate Limits

```
requests_per_minute
requests_per_hour
sliding_window_limit
sliding_window_minutes
backup_model
fallback_on_limit
```

### 🚫 Ban Categories (Fully Customizable)

```
ban_reason_1_emails
ban_reason_2_emails
...
ban_message_1
ban_message_2
...
```

Each category = its own custom ban reason.

---

### 🛠 Example: Custom Ban Message

```
ban_message_4: "Your account has been permanently restricted for violating usage policies."
```

---

## 🚧 Roadmap
	•	Full analytics dashboard
	•	IP-based controls
	•	Multi-instance syncing
	•	Auto-tier promotions
	•	Admin audit logs
	•	Webhook integration

---

## 🤝 Contributing

Pull requests, feature ideas, and security discussions are welcome!

---

## ❤️ Love this project?

A star ⭐ on GitHub helps a lot.
https://github.com/zealmult/OpenAccess-Guard

(ad)
Powered By BreathAI
Free Claude 4.5/Gemini 3 Pro/GPT-5.1/DeepSeek/Llama/Grok4.1 API

