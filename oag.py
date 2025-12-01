"""
title: OpenAccess Guard Pro
author: zealmult
author_url: https://github.com/zealmult
funding_url: https://breathai.top/
homepage: https://github.com/zealmult/OpenAccess-Guard/
version: 0.1.0
"""

import time
import re
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Awaitable, List, Dict
from pydantic import BaseModel, Field

# ============================================================
# Default Configuration
# ============================================================

DEFAULT_CONFIG = {
    "base": {"enabled": True, "admin_effective": False},
    "auth": {
        "enabled": False,
        "providers": ["outlook.com", "gmail.com", "qq.com"],
        "deny_msg": "Access Denied: Your email provider is not supported.",
    },
    "whitelist": {"enabled": False, "emails": []},
    "exemption": {"enabled": False, "emails": []},
    "priority": {"user_priority": False},
    "global_limit": {"enabled": False},
    "user_tiers": [],
    "model_tiers_config": {"match_tiers": False},
    "model_tiers": [],
    "ban_reasons": [],
    "fallback": {
        "enabled": False,
        "model": "qwen2:0.5b",
        "notify": True,
        "notify_msg": "Rate limit exceeded. Switched to fallback model.",
    },
    "logging": {
        "enabled": True,
        "oag_log": True,
        "inlet": False,
        "outlet": False,
        "stream": False,
        "user_dict": False,
    },
    "ads": {"enabled": False, "content": []},
    "custom_strings": {
        "whitelist_deny": "Access Denied: Not in whitelist.",
        "tier_mismatch": "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
        "user_deny_model": "Tier {u_tier} users cannot use model {model_id}",
        "model_wl_deny": "Access Denied to Tier {m_tier} Model (Whitelist)",
        "model_bl_deny": "Access Denied to Tier {m_tier} Model (Blacklist)",
        "rate_limit_deny": "Rate Limit Exceeded: {reason}",
    },
}

# Initialize default User Tier 0
DEFAULT_CONFIG["user_tiers"].append(
    {
        "tier_id": 0,
        "tier_name": "Default",
        "enabled": True,
        "emails": [],
        "rpm": 0,
        "rph": 0,
        "win_time": 0,
        "win_limit": 0,
        "clip": 0,
        "deny_model_enabled": False,
        "deny_models": [],
        "user_priority": False,
    }
)

# Initialize default Model Tier 0
DEFAULT_CONFIG["model_tiers"].append(
    {
        "tier_id": 0,
        "tier_name": "Default",
        "enabled": False,
        "models": [],
        "rpm": 0,
        "rph": 0,
        "win_time": 0,
        "win_limit": 0,
        "clip": 0,
        "mode_whitelist": False,
        "access_list": [],
    }
)

# ============================================================
# Filter Logic
# ============================================================


class Filter:
    class Valves(BaseModel):
        config_json: str = Field(
            default=json.dumps(DEFAULT_CONFIG, indent=2),
            description="Please open https://oag.breathai.top to generate the configuration file.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_history = {}
        self.parsed_config = None

    def _get_cfg(self):
        """
        Retrieve and parse the configuration from valves.
        Returns the default configuration if parsing fails.
        """
        try:
            return json.loads(self.valves.config_json)
        except:
            return DEFAULT_CONFIG

    def _log(self, cfg, level, msg, data=None):
        """
        Internal logging helper.
        Logs messages based on the configuration settings for different levels (OAG, INLET, OUTLET, STREAM).
        """
        if not cfg["logging"]["enabled"]:
            return
        prefix = "[OpenAccess Guard]"

        if level == "OAG" and cfg["logging"]["oag_log"]:
            print(f"{prefix} {msg} | Data: {data}")
        elif level in ["INLET", "OUTLET", "STREAM"] and cfg["logging"][level.lower()]:
            if data and "user" in data and not cfg["logging"]["user_dict"]:
                data["user"] = data["user"].get("email", "hidden")
            print(f"{prefix} [{level}] {msg} | {data}")

    def _get_tier(self, cfg, email, mode="user"):
        """
        Determine the Tier index for a user or model.
        Returns the array index of the matched tier, not the tier_id.
        Prioritizes higher tier_ids.
        """
        if mode == "user":
            tiers = cfg.get("user_tiers", [])
            if not tiers:
                raise Exception("Configuration Error: No user tiers defined. Please add at least one user tier (Tier 0).")
            
            tier_indices = [(t.get("tier_id", idx), idx) for idx, t in enumerate(tiers)]
            tier_indices.sort(reverse=True, key=lambda x: x[0])
            
            for tier_id, idx in tier_indices:
                if email in tiers[idx].get("emails", []):
                    return idx
            
            for idx, t in enumerate(tiers):
                if t.get("tier_id", idx) == 0:
                    return idx
            return 0
        else:
            model_id = email
            tiers = cfg.get("model_tiers", [])
            if not tiers:
                raise Exception("Configuration Error: No model tiers defined. Please add at least one model tier (Tier 0).")
            
            tier_indices = [(t.get("tier_id", idx), idx) for idx, t in enumerate(tiers)]
            tier_indices.sort(reverse=True, key=lambda x: x[0])
            
            for tier_id, idx in tier_indices:
                if model_id in tiers[idx].get("models", []):
                    return idx
            
            for idx, t in enumerate(tiers):
                if t.get("tier_id", idx) == 0:
                    return idx
            return 0

    def _check_specific_limit(self, source_name, limits, history):
        """
        Check if a specific limit (RPM, RPH, Window) is reached.
        """
        now = time.time()
        rpm = limits.get("rpm", 0)
        rph = limits.get("rph", 0)
        w_lim = limits.get("win_limit", 0)
        w_time = limits.get("win_time", 0)

        if rpm > 0:
            count = len([t for t in history if now - t < 60])
            if count >= rpm:
                return True, f"{source_name} RPM Limit"

        if rph > 0:
            count = len([t for t in history if now - t < 3600])
            if count >= rph:
                return True, f"{source_name} RPH Limit"

        if w_lim > 0 and w_time > 0:
            count = len([t for t in history if now - t < w_time * 60])
            if count >= w_lim:
                return True, f"{source_name} Window Limit"

        return False, None

    def _check_rate_limit(
        self, cfg, user_id, email, model_id, user_tier_idx, model_tier_idx
    ):
        """
        Core rate limiting logic.
        Checks both User Tier and Model Tier limits.
        Handles priority logic (User Priority vs Model Priority).
        """
        now = time.time()

        ut_cfg = cfg["user_tiers"][user_tier_idx]
        mt_cfg = cfg["model_tiers"][model_tier_idx]

        if user_id not in self.user_history:
            self.user_history[user_id] = {}

        target_history_key = "GLOBAL" if cfg["global_limit"]["enabled"] else model_id

        if target_history_key not in self.user_history[user_id]:
            self.user_history[user_id][target_history_key] = []

        history = self.user_history[user_id][target_history_key]
        history = [t for t in history if now - t < 86400]
        self.user_history[user_id][target_history_key] = history

        user_hit, user_reason = self._check_specific_limit("User Tier", ut_cfg, history)

        model_hit, model_reason = self._check_specific_limit(
            "Model Tier", mt_cfg, history
        )

        global_prio = cfg.get("priority", {}).get("user_priority", False)
        tier_prio = mt_cfg.get("user_priority", False)

        use_user_priority = global_prio or tier_prio

        if use_user_priority:
            if user_hit:
                return True, user_reason
            else:
                if model_hit:
                    pass
                return False, None
        else:
            if user_hit:
                return True, user_reason
            if model_hit:
                return True, model_reason

        return False, None

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> dict:
        """
        Process incoming requests.
        Performs authentication, whitelist/blacklist checks, tier resolution, rate limiting, context clipping, and ad injection.
        """
        cfg = self._get_cfg()

        def get_msg(key, default):
            return cfg.get("custom_strings", {}).get(key, default)

        if not cfg["base"]["enabled"]:
            return body
        if not __user__:
            return body

        email = __user__.get("email", "")
        role = __user__.get("role", "user")
        user_id = __user__.get("id", "")
        model_id = body.get("model", "")

        self._log(
            cfg, "INLET", "Request Received", {"user": __user__, "model": model_id}
        )

        if role == "admin" and not cfg["base"]["admin_effective"]:
            return body

        if cfg["exemption"]["enabled"] and email in cfg["exemption"]["emails"]:
            self._log(cfg, "OAG", "Exempted User", email)
            return body

        if cfg["auth"]["enabled"]:
            domain = email.split("@")[-1] if "@" in email else ""
            if domain not in cfg["auth"]["providers"]:
                raise Exception(cfg["auth"]["deny_msg"])

        if cfg["whitelist"]["enabled"] and email not in cfg["whitelist"]["emails"]:
            msg = get_msg("whitelist_deny", "Access Denied: Not in whitelist.")
            raise Exception(msg)

        for reason in cfg.get("ban_reasons", []):
            if email in reason.get("emails", []):
                raise Exception(reason.get("msg", "Account Suspended"))

        u_tier_idx = self._get_tier(cfg, email, "user")
        m_tier_idx = self._get_tier(cfg, model_id, "model")

        ut_cfg = cfg["user_tiers"][u_tier_idx]
        mt_cfg = cfg["model_tiers"][m_tier_idx]
        u_tier_id = ut_cfg.get("tier_id", u_tier_idx)
        m_tier_id = mt_cfg.get("tier_id", m_tier_idx)

        if ut_cfg.get("deny_model_enabled") and model_id in ut_cfg.get("deny_models", []):
            msg = get_msg(
                "user_deny_model", "Tier {u_tier} users cannot use model {model_id}"
            )
            raise Exception(msg.format(u_tier=u_tier_id, model_id=model_id))

        if cfg["model_tiers_config"]["match_tiers"]:
            if u_tier_id != m_tier_id:
                msg = get_msg(
                    "tier_mismatch",
                    "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
                )
                raise Exception(msg.format(u_tier=u_tier_id, m_tier=m_tier_id))
        else:
            access_list = mt_cfg.get("access_list", [])
            if mt_cfg.get("mode_whitelist", True):
                if email not in access_list:
                    msg = get_msg(
                        "model_wl_deny",
                        "Access Denied to Tier {m_tier} Model (Whitelist)",
                    )
                    raise Exception(msg.format(m_tier=m_tier_id))
            else:
                if email in access_list:
                    msg = get_msg(
                        "model_bl_deny",
                        "Access Denied to Tier {m_tier} Model (Blacklist)",
                    )
                    raise Exception(msg.format(m_tier=m_tier_id))

        is_limited, limit_reason = self._check_rate_limit(
            cfg, user_id, email, model_id, u_tier_idx, m_tier_idx
        )

        if is_limited:
            self._log(cfg, "OAG", "Rate Limit Hit", limit_reason)

            if cfg["fallback"]["enabled"]:
                fallback_model = cfg["fallback"]["model"]
                body["model"] = fallback_model

                if cfg["fallback"]["notify"] and __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": cfg["fallback"]["notify_msg"],
                                "done": True,
                            },
                        }
                    )
            else:
                msg = get_msg("rate_limit_deny", "Rate Limit Exceeded: {reason}")
                raise Exception(msg.format(reason=limit_reason))
        else:
            target = "GLOBAL" if cfg["global_limit"]["enabled"] else model_id
            self.user_history[user_id][target].append(time.time())

        clip_count = max(ut_cfg.get("clip", 0), mt_cfg.get("clip", 0))
        if clip_count > 0 and "messages" in body:
            msgs = body["messages"]
            sys_msg = next((m for m in msgs if m["role"] == "system"), None)
            chat_msgs = [m for m in msgs if m["role"] != "system"]

            chat_msgs = chat_msgs[-clip_count:]

            if sys_msg:
                chat_msgs.insert(0, sys_msg)

            body["messages"] = chat_msgs
            self._log(cfg, "OAG", f"Context Clipped to {clip_count}")

        if cfg["ads"]["enabled"] and cfg["ads"]["content"] and __event_emitter__:
            valid_ads = [ad for ad in cfg["ads"]["content"] if ad.strip()]
            if valid_ads:
                ad_text = random.choice(valid_ads)
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"📢 {ad_text}", "done": True},
                    }
                )

        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """
        Process outgoing responses.
        """
        cfg = self._get_cfg()
        self._log(cfg, "OUTLET", "Response", {"user": __user__})
        return body

    async def stream(self, event: Any, __user__: Optional[dict] = None) -> Any:
        """
        Process streaming events.
        """
        cfg = self._get_cfg()
        if cfg["logging"]["enabled"] and cfg["logging"]["stream"]:
            log_data = event
            if isinstance(event, bytes):
                try:
                    log_data = event.decode("utf-8")
                except:
                    log_data = "<binary>"

            self._log(cfg, "STREAM", "Chunk", {"data": log_data, "user": __user__})
        return event
