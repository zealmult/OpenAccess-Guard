"""
title: OpenAccess Guard Pro
author: zealmult
author_url: https://github.com/zealmult
funding_url: https://breathai.top/
homepage: https://github.com/zealmult/OpenAccess-Guard/
version: 0.2.0
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
    "priority": {"user_priority": False},  # Legacy: for backwards compatibility
    "global_limit": {"enabled": False},
    
    # === NEW: Group System (v0.2.0+) ===
    "model_groups": [],
    "user_groups": [],
    
    # === LEGACY: Tier System (v0.1.x, deprecated) ===
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
        # NEW: Group system messages
        "group_no_permission": "Access Denied: User group '{u_group}' cannot access model group '{m_group}'",
    },
}

# Initialize default Model Group
DEFAULT_CONFIG["model_groups"].append({
    "id": "default",
    "name": "Default Models",
    "models": []
})

# Initialize default User Group
DEFAULT_CONFIG["user_groups"].append({
    "id": "default",
    "name": "Default Users",
    "priority": 0,
    "emails": [],  # Empty = catch-all default group
    "default_permissions": {
        "enabled": False,
        "rpm": 0,
        "rph": 0,
        "win_time": 0,
        "win_limit": 0,
        "clip": 0
    },
    "permissions": {}  # model_group_id -> limits override
})

# Initialize default User Tier 0 (LEGACY - for backwards compatibility)
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

# Initialize default Model Tier 0 (LEGACY - for backwards compatibility)
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

    def _migrate_config_to_groups(self, cfg):
        """
        Automatically migrate old tier-based configuration to new group-based configuration.
        This ensures backwards compatibility with v0.1.x configs.
        """
        # Check if already using group system
        if cfg.get("user_groups") and len(cfg["user_groups"]) > 0:
            # Already migrated or new config
            return cfg
        
        # Check if using old tier system
        if not cfg.get("user_tiers") or len(cfg["user_tiers"]) == 0:
            # No config to migrate
            return cfg
        
        self._log(cfg, "OAG", "Migration", "Detected v0.1.x config, migrating to Group system...")
        
        # === Migrate Model Tiers to Model Groups ===
        model_groups = []
        for tier in cfg.get("model_tiers", []):
            tier_id = tier.get("tier_id", 0)
            model_groups.append({
                "id": f"tier_{tier_id}",
                "name": tier.get("tier_name", f"Tier {tier_id}"),
                "models": tier.get("models", [])
            })
        
        # === Migrate User Tiers to User Groups ===
        user_groups = []
        for tier in cfg.get("user_tiers", []):
            tier_id = tier.get("tier_id", 0)
            
            # Build permissions for each model group
            permissions = {}
            for mg in model_groups:
                mg_id = mg["id"]
                
                # Check access based on old match_tiers logic
                # Safe tier_id extraction from mg_id
                try:
                    mg_tier_id = int(mg_id.split("_")[1]) if "_" in mg_id else 0
                except (IndexError, ValueError):
                    mg_tier_id = 0
                
                if cfg.get("model_tiers_config", {}).get("match_tiers", False):
                    # Strict tier matching: only same tier_id
                    enabled = (tier_id == mg_tier_id)
                else:
                    # Check model tier access list
                    # Find corresponding model tier
                    mt = next((t for t in cfg.get("model_tiers", []) if t.get("tier_id") == mg_tier_id), None)
                    if mt:
                        access_list = mt.get("access_list", [])
                        mode_wl = mt.get("mode_whitelist", False)
                        
                        if not access_list:
                            enabled = True  # No restrictions
                        elif mode_wl:
                            # Whitelist mode
                            user_emails = tier.get("emails", [])
                            if not user_emails:  # Default tier (empty emails)
                                enabled = False  # Default users not in whitelist
                            else:
                                enabled = any(email in access_list for email in user_emails)
                        else:
                            # Blacklist mode
                            user_emails = tier.get("emails", [])
                            if not user_emails:  # Default tier (empty emails)
                                enabled = True  # Default users not in blacklist
                            else:
                                enabled = not any(email in access_list for email in user_emails)
                    else:
                        enabled = True
                
                # Use user tier limits (user_priority logic)
                permissions[mg_id] = {
                    "enabled": enabled,
                    "rpm": tier.get("rpm", 0),
                    "rph": tier.get("rph", 0),
                    "win_time": tier.get("win_time", 0),
                    "win_limit": tier.get("win_limit", 0),
                    "clip": tier.get("clip", 0)
                }
            
            user_groups.append({
                "id": f"tier_{tier_id}",
                "name": tier.get("tier_name", f"Tier {tier_id}"),
                "priority": tier_id,  # Higher tier_id = higher priority
                "emails": tier.get("emails", []),
                "default_permissions": {
                    "enabled": False,
                    "rpm": 0,
                    "rph": 0,
                    "win_time": 0,
                    "win_limit": 0,
                    "clip": 0
                },
                "permissions": permissions
            })
        
        # Update config
        cfg["model_groups"] = model_groups
        cfg["user_groups"] = user_groups
        
        self._log(cfg, "OAG", "Migration", f"Migrated {len(user_groups)} user groups, {len(model_groups)} model groups")
        return cfg

    def _get_user_group(self, cfg, email):
        """
        Find the user group for a given email.
        Returns the group with highest priority that contains this email.
        If no match, returns the default group (emails=[]).
        """
        groups = cfg.get("user_groups", [])
        if not groups:
            raise Exception("Configuration Error: No user groups defined.")
        
        # Sort by priority (descending)
        sorted_groups = sorted(groups, key=lambda g: g.get("priority", 0), reverse=True)
        
        # Find first group containing this email
        for group in sorted_groups:
            if email in group.get("emails", []):
                return group
        
        # Return default group (empty emails = catch-all)
        for group in groups:
            emails = group.get("emails", [])
            if isinstance(emails, list) and len(emails) == 0:
                return group
        
        # Fallback to first group
        return groups[0]

    def _get_model_group(self, cfg, model_id):
        """
        Find the model group for a given model ID.
        Returns None if model is not in any group.
        """
        groups = cfg.get("model_groups", [])
        
        for group in groups:
            if model_id in group.get("models", []):
                return group
        
        return None

    def _get_cfg(self):
        """
        Retrieve and parse the configuration from valves.
        Auto-migrates old tier configs to new group system.
        """
        try:
            cfg = json.loads(self.valves.config_json)
            
            # Merge with defaults for any missing keys
            for key, value in DEFAULT_CONFIG.items():
                if key not in cfg:
                    cfg[key] = value
            
            # Auto-migrate old tier configs to new group system
            cfg = self._migrate_config_to_groups(cfg)
            
            return cfg
        except Exception as e:
            raise Exception(f"Configuration Parse Error: {str(e)}")

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
            # Create a copy to avoid mutating original data
            log_data = data
            if data and "user" in data and not cfg["logging"]["user_dict"]:
                log_data = data.copy()
                log_data["user"] = data["user"].get("email", "hidden")
            print(f"{prefix} [{level}] {msg} | {log_data}")

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

    def _check_rate_limit_group(self, cfg, user_id, email, model_id, user_group, model_group):
        """
        Check rate limits using new Group system.
        """
        if not model_group:
            # Model not in any group, allow access with no limits
            return False, None
        
        model_group_id = model_group["id"]
        
        # Get permissions for this model group
        permissions = user_group.get("permissions", {})
        model_perms = permissions.get(model_group_id)
        
        # If no specific permissions or empty dict, use default_permissions
        if not model_perms or (isinstance(model_perms, dict) and len(model_perms) == 0):
            model_perms = user_group.get("default_permissions", {})
        
        # Check if access is enabled (only if permissions are defined)
        if model_perms and not model_perms.get("enabled", False):
            # Access denied
            user_group_name = user_group.get("name", user_group.get("id"))
            model_group_name = model_group.get("name", model_group.get("id"))
            msg = cfg.get("custom_strings", {}).get(
                "group_no_permission",
                "Access Denied: User group '{u_group}' cannot access model group '{m_group}'"
            )
            raise Exception(msg.format(u_group=user_group_name, m_group=model_group_name))
        
        # Initialize history
        now = time.time()
        if user_id not in self.user_history:
            self.user_history[user_id] = {}
        
        # Determine history key (global or per-model-group)
        target_history_key = "GLOBAL" if cfg["global_limit"]["enabled"] else model_group_id
        
        if target_history_key not in self.user_history[user_id]:
            self.user_history[user_id][target_history_key] = []
        
        history = self.user_history[user_id][target_history_key]
        history = [t for t in history if now - t < 86400]
        self.user_history[user_id][target_history_key] = history
        
        # Check limits
        source_name = f"{user_group.get('name')} → {model_group.get('name')}"
        is_limited, reason = self._check_specific_limit(source_name, model_perms, history)
        
        return is_limited, reason

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

        # === NEW: Group System Logic (v0.2.0+) ===
        # Check if using new group system
        if cfg.get("user_groups") and len(cfg["user_groups"]) > 0:
            # Use Group system
            user_group = self._get_user_group(cfg, email)
            model_group = self._get_model_group(cfg, model_id)
            
            self._log(cfg, "OAG", "Group Match", {
                "user_group": user_group.get("name"),
                "model_group": model_group.get("name") if model_group else "Ungrouped"
            })
            
            # Check rate limits (includes permission check)
            is_limited, limit_reason = self._check_rate_limit_group(
                cfg, user_id, email, model_id, user_group, model_group
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
            
            # Record access
            if user_id not in self.user_history:
                self.user_history[user_id] = {}
            target_history_key = "GLOBAL" if cfg["global_limit"]["enabled"] else (model_group["id"] if model_group else "ungrouped")
            if target_history_key not in self.user_history[user_id]:
                self.user_history[user_id][target_history_key] = []
            self.user_history[user_id][target_history_key].append(time.time())
            
            # Context clipping
            if model_group:
                permissions = user_group.get("permissions", {})
                model_perms = permissions.get(model_group["id"], user_group.get("default_permissions", {}))
                clip = model_perms.get("clip", 0)
                if clip > 0:
                    messages = body.get("messages", [])
                    system_msgs = [m for m in messages if m.get("role") == "system"]
                    non_system_msgs = [m for m in messages if m.get("role") != "system"]
                    if len(non_system_msgs) > clip:
                        body["messages"] = system_msgs + non_system_msgs[-clip:]
        
        # === LEGACY: Tier System (v0.1.x, deprecated) ===
        else:
            # Fallback to old tier system
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
                # If access_list is empty, allow all users
                if access_list:
                    if mt_cfg.get("mode_whitelist", False):
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
                # Record access (safety check)
                target = "GLOBAL" if cfg["global_limit"]["enabled"] else model_id
                if target not in self.user_history[user_id]:
                    self.user_history[user_id][target] = []
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

        # === End of Group/Tier logic ===

        # Ads injection (applies to both systems)
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
