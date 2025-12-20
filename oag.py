"""
title: OpenAccess Guard Pro
author: zealmult
author_url: https://github.com/zealmult
funding_url: https://breathai.top/
homepage: https://github.com/zealmult/OpenAccess-Guard/
version: 0.2.2
"""

import copy
import json
import random
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

# ============================================================
# Default Configuration
# ============================================================
DEFAULT_CONFIG: Dict[str, Any] = {
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
    "model_groups": [
        {"id": "default", "name": "Default Models", "models": []},
    ],
    "user_groups": [
        {
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
                "clip": 0,
            },
            "permissions": {},  # model_group_id -> limits override
        }
    ],
    # === LEGACY: Tier System (v0.1.x, deprecated) ===
    "user_tiers": [
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
    ],
    "model_tiers_config": {"match_tiers": False},
    "model_tiers": [
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
    ],
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


# ============================================================
# Filter Logic
# ============================================================
class Filter:
    class Valves(BaseModel):
        config_json: str = Field(
            default=json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
            description="Please open https://oag.breathai.top to generate the configuration file. (Supports // and /* */ comments.)",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_history: Dict[str, Dict[str, List[float]]] = {}
        self._warned_multiple_default_groups = False

    # ----------------------------
    # Small helpers
    # ----------------------------
    @staticmethod
    def _normalize_email(email: Any) -> str:
        if email is None:
            return ""
        return str(email).strip().casefold()

    @classmethod
    def _email_in_list(cls, email: str, emails: Any) -> bool:
        if not email or not isinstance(emails, list):
            return False
        target = cls._normalize_email(email)
        for item in emails:
            if cls._normalize_email(item) == target:
                return True
        return False

    def _merge_dict_defaults(
        self, cfg: Dict[str, Any], defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        for key, default_value in defaults.items():
            if key not in cfg or cfg[key] is None:
                cfg[key] = copy.deepcopy(default_value)
                continue
            existing_value = cfg.get(key)
            if isinstance(existing_value, dict) and isinstance(default_value, dict):
                self._merge_dict_defaults(existing_value, default_value)
        return cfg

    @staticmethod
    def _strip_json_comments(raw: str) -> str:
        """
        Strip // and /* */ comments from JSON-like text (JSONC),
        without touching comment markers inside strings.
        Also supports # line comments.
        """
        if not isinstance(raw, str) or not raw:
            return raw or ""

        out: List[str] = []
        i, n = 0, len(raw)
        in_string = False
        escape = False

        while i < n:
            ch = raw[i]

            if in_string:
                out.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                i += 1
                continue

            if ch == '"':
                in_string = True
                out.append(ch)
                i += 1
                continue

            # // line comment
            if ch == "/" and i + 1 < n and raw[i + 1] == "/":
                i += 2
                while i < n and raw[i] not in "\n\r":
                    i += 1
                continue

            # /* block comment */ (keep newlines to preserve line numbers)
            if ch == "/" and i + 1 < n and raw[i + 1] == "*":
                i += 2
                while i < n:
                    if raw[i] in "\n\r":
                        out.append(raw[i])
                    if raw[i] == "*" and i + 1 < n and raw[i + 1] == "/":
                        i += 2
                        break
                    i += 1
                continue

            # # line comment (optional)
            if ch == "#":
                i += 1
                while i < n and raw[i] not in "\n\r":
                    i += 1
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    # ----------------------------
    # Migration / Validation
    # ----------------------------
    def _migrate_config_to_groups(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically migrate old tier-based configuration to new group-based configuration.
        This ensures backwards compatibility with v0.1.x configs.
        """
        # Already using group system
        if isinstance(cfg.get("user_groups"), list) and len(cfg["user_groups"]) > 0:
            return cfg

        # No tiers to migrate
        if not isinstance(cfg.get("user_tiers"), list) or len(cfg["user_tiers"]) == 0:
            return cfg

        self._log(
            cfg,
            "OAG",
            "Migration",
            "Detected v0.1.x config, migrating to Group system...",
        )

        # === Migrate Model Tiers to Model Groups ===
        model_groups: List[Dict[str, Any]] = []
        for tier in (
            cfg.get("model_tiers", [])
            if isinstance(cfg.get("model_tiers"), list)
            else []
        ):
            tier_id = tier.get("tier_id", 0)
            model_groups.append(
                {
                    "id": f"tier_{tier_id}",
                    "name": tier.get("tier_name", f"Tier {tier_id}"),
                    "models": tier.get("models", []),
                }
            )

        # === Migrate User Tiers to User Groups ===
        user_groups: List[Dict[str, Any]] = []
        for tier in (
            cfg.get("user_tiers", []) if isinstance(cfg.get("user_tiers"), list) else []
        ):
            tier_id = tier.get("tier_id", 0)
            permissions: Dict[str, Any] = {}

            for mg in model_groups:
                mg_id = mg["id"]
                try:
                    mg_tier_id = int(mg_id.split("_")[1]) if "_" in mg_id else 0
                except (IndexError, ValueError):
                    mg_tier_id = 0

                if cfg.get("model_tiers_config", {}).get("match_tiers", False):
                    enabled = tier_id == mg_tier_id
                else:
                    mt = next(
                        (
                            t
                            for t in (
                                cfg.get("model_tiers", [])
                                if isinstance(cfg.get("model_tiers"), list)
                                else []
                            )
                            if t.get("tier_id") == mg_tier_id
                        ),
                        None,
                    )
                    if mt:
                        access_list = mt.get("access_list", [])
                        mode_wl = mt.get("mode_whitelist", False)
                        if not access_list:
                            enabled = True
                        elif mode_wl:
                            user_emails = tier.get("emails", [])
                            if not user_emails:
                                enabled = False
                            else:
                                enabled = any(
                                    email in access_list for email in user_emails
                                )
                        else:
                            user_emails = tier.get("emails", [])
                            if not user_emails:
                                enabled = True
                            else:
                                enabled = not any(
                                    email in access_list for email in user_emails
                                )
                    else:
                        enabled = True

                permissions[mg_id] = {
                    "enabled": enabled,
                    "rpm": tier.get("rpm", 0),
                    "rph": tier.get("rph", 0),
                    "win_time": tier.get("win_time", 0),
                    "win_limit": tier.get("win_limit", 0),
                    "clip": tier.get("clip", 0),
                }

            user_groups.append(
                {
                    "id": f"tier_{tier_id}",
                    "name": tier.get("tier_name", f"Tier {tier_id}"),
                    "priority": tier_id,
                    "emails": tier.get("emails", []),
                    "default_permissions": {
                        "enabled": False,
                        "rpm": 0,
                        "rph": 0,
                        "win_time": 0,
                        "win_limit": 0,
                        "clip": 0,
                    },
                    "permissions": permissions,
                }
            )

        cfg["model_groups"] = model_groups
        cfg["user_groups"] = user_groups

        self._log(
            cfg,
            "OAG",
            "Migration",
            f"Migrated {len(user_groups)} user groups, {len(model_groups)} model groups",
        )
        return cfg

    def _warn_if_multiple_default_user_groups(self, cfg: Dict[str, Any]) -> None:
        if self._warned_multiple_default_groups:
            return
        groups = cfg.get("user_groups")
        if not isinstance(groups, list):
            return
        catch_alls: List[Dict[str, Any]] = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            emails = g.get("emails")
            if isinstance(emails, list) and len(emails) == 0:
                catch_alls.append(g)
        if len(catch_alls) > 1:
            self._warned_multiple_default_groups = True
            self._log(
                cfg,
                "OAG",
                "Configuration Warning",
                {
                    "issue": "multiple_catch_all_user_groups",
                    "note": "Only the first catch-all group (emails=[]) will be used as default if no explicit email match.",
                    "groups": [
                        {
                            "id": g.get("id"),
                            "name": g.get("name"),
                            "priority": g.get("priority", 0),
                        }
                        for g in catch_alls
                    ],
                },
            )

    # ----------------------------
    # Group matching
    # ----------------------------
    def _get_user_group(self, cfg: Dict[str, Any], email: str) -> Dict[str, Any]:
        """
        Find the user group for a given email.
        Returns the group with highest priority that contains this email.
        If no match, returns the default group (emails=[]).
        """
        groups = cfg.get("user_groups", [])
        if not isinstance(groups, list) or not groups:
            raise Exception("Configuration Error: No user groups defined.")
        email_norm = self._normalize_email(email)
        sorted_groups = sorted(
            groups,
            key=lambda g: (g.get("priority", 0) if isinstance(g, dict) else 0),
            reverse=True,
        )
        for group in sorted_groups:
            if not isinstance(group, dict):
                continue
            group_emails = group.get("emails", [])
            if not isinstance(group_emails, list) or not group_emails:
                continue
            if any(self._normalize_email(e) == email_norm for e in group_emails):
                return group
        for group in groups:
            if not isinstance(group, dict):
                continue
            emails = group.get("emails", [])
            if isinstance(emails, list) and len(emails) == 0:
                return group
        return (
            groups[0]
            if isinstance(groups[0], dict)
            else {"id": "unknown", "name": "unknown"}
        )

    def _get_model_group(
        self, cfg: Dict[str, Any], model_id: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Find the model group for a given model ID.
        Returns None if model is not in any group.
        """
        groups = cfg.get("model_groups", [])
        if not isinstance(groups, list):
            return None
        incoming = self._normalize_model_id(model_id)
        incoming_variants = self._model_id_variants(incoming)
        for group in groups:
            if not isinstance(group, dict):
                continue
            models = group.get("models", [])
            if not isinstance(models, list):
                continue
            for configured in models:
                configured_id = self._normalize_model_id(configured)
                if not configured_id:
                    continue
                if self._model_id_variants(configured_id) & incoming_variants:
                    return group
        return None

    @staticmethod
    def _normalize_model_id(model_field: Any) -> str:
        """
        Normalize Open WebUI model field into a string model id.
        Open WebUI versions/providers may send `body["model"]` as a string or an object.
        """
        if isinstance(model_field, str):
            return model_field
        if isinstance(model_field, dict):
            for key in ("id", "model", "name"):
                value = model_field.get(key)
                if isinstance(value, str):
                    return value
            return ""
        return str(model_field) if model_field is not None else ""

    @staticmethod
    def _model_id_variants(model_id: str) -> Set[str]:
        """
        Generate a small set of equivalent model id variants so config entries can
        match common Open WebUI / provider formats.
        """
        if not isinstance(model_id, str):
            return set()
        raw = model_id.strip()
        if not raw:
            return set()

        variants: Set[str] = {raw, raw.casefold()}
        if "/" in raw:
            tail = raw.split("/")[-1].strip()
            if tail:
                variants.add(tail)
                variants.add(tail.casefold())
        if ":" in raw:
            base = raw.split(":")[0].strip()
            if base:
                variants.add(base)
                variants.add(base.casefold())
        if "/" in raw and ":" in raw:
            tail = raw.split("/")[-1].strip()
            base = tail.split(":")[0].strip()
            if base:
                variants.add(base)
                variants.add(base.casefold())
        return variants

    # ----------------------------
    # Messages selection + clip
    # ----------------------------
    @staticmethod
    def _select_messages_with_source(body: dict) -> Tuple[List[dict], str]:
        """
        Try multiple locations to find the longest valid messages list.
        Returns (messages, source).
        """
        if not isinstance(body, dict):
            return [], "none"

        def is_valid_messages(value: Any) -> bool:
            if not isinstance(value, list):
                return False
            for item in value:
                if not isinstance(item, dict):
                    return False
                if "role" not in item:
                    return False
            return True

        candidates: List[Tuple[List[dict], str]] = []

        def add_candidate(value: Any, source: str) -> None:
            if is_valid_messages(value):
                candidates.append((value, source))

        keys = (
            "messages",
            "history",
            "chat_history",
            "conversation_messages",
            "all_messages",
        )
        for key in keys:
            add_candidate(body.get(key), f"body.{key}")

        meta = body.get("metadata")
        if isinstance(meta, dict):
            for key in keys:
                add_candidate(meta.get(key), f"body.metadata.{key}")

        chat = body.get("chat")
        if isinstance(chat, dict):
            add_candidate(chat.get("messages"), "body.chat.messages")

        conversation = body.get("conversation")
        if isinstance(conversation, dict):
            for key in keys:
                add_candidate(conversation.get(key), f"body.conversation.{key}")
            add_candidate(conversation.get("messages"), "body.conversation.messages")

        data = body.get("data")
        if isinstance(data, dict):
            for key in keys:
                add_candidate(data.get(key), f"body.data.{key}")

        if not candidates:
            return [], "none"

        messages, source = max(candidates, key=lambda item: len(item[0]))
        return messages, source

    @staticmethod
    def _select_messages(body: dict) -> List[dict]:
        return Filter._select_messages_with_source(body)[0]

    @staticmethod
    def _coerce_nonneg_int(value: Any, default: int = 0) -> int:
        try:
            parsed = int(value)
        except Exception:
            return default
        return parsed if parsed > 0 else 0

    # ----------------------------
    # Config / Logging
    # ----------------------------
    def _get_cfg(self) -> Dict[str, Any]:
        """
        Retrieve and parse the configuration from valves.
        Auto-migrates old tier configs to new group system.
        Supports JSONC comments (//, /* */ and #).
        """
        try:
            raw = self.valves.config_json
            raw = raw.lstrip("\ufeff") if isinstance(raw, str) else raw

            try:
                cfg = json.loads(raw)
            except json.JSONDecodeError:
                cfg = json.loads(self._strip_json_comments(raw))

            if not isinstance(cfg, dict):
                raise Exception("root must be an object")

            cfg = self._merge_dict_defaults(cfg, DEFAULT_CONFIG)
            cfg = self._migrate_config_to_groups(cfg)
            self._warn_if_multiple_default_user_groups(cfg)
            return cfg
        except Exception as e:
            raise Exception(f"Configuration Parse Error: {str(e)}")

    def _log(self, cfg: Dict[str, Any], level: str, msg: str, data: Any = None) -> None:
        """
        Internal logging helper.
        """
        logging_cfg = cfg.get("logging")
        if not isinstance(logging_cfg, dict) or not logging_cfg.get("enabled", False):
            return

        prefix = "[OpenAccess Guard]"
        if level == "OAG":
            if logging_cfg.get("oag_log", False):
                print(f"{prefix} {msg} | Data: {data}")
            return

        if level in ("INLET", "OUTLET", "STREAM"):
            if not logging_cfg.get(level.lower(), False):
                return

            log_data = data
            if (
                isinstance(data, dict)
                and "user" in data
                and not logging_cfg.get("user_dict", False)
            ):
                # Avoid mutating original
                log_data = data.copy()
                user_val = data.get("user")
                if isinstance(user_val, dict):
                    log_data["user"] = user_val.get("email", "hidden")
                else:
                    log_data["user"] = "hidden"

            print(f"{prefix} [{level}] {msg} | {log_data}")

    # ----------------------------
    # Legacy Tier System
    # ----------------------------
    def _get_tier(self, cfg: Dict[str, Any], email: str, mode: str = "user") -> int:
        """
        Determine the Tier index for a user or model.
        Returns the array index of the matched tier, not the tier_id.
        Prioritizes higher tier_ids.
        """
        if mode == "user":
            tiers = cfg.get("user_tiers", [])
            if not isinstance(tiers, list) or not tiers:
                raise Exception(
                    "Configuration Error: No user tiers defined. Please add at least one user tier (Tier 0)."
                )

            tier_indices = [
                (t.get("tier_id", idx), idx)
                for idx, t in enumerate(tiers)
                if isinstance(t, dict)
            ]
            tier_indices.sort(reverse=True, key=lambda x: x[0])

            for _tier_id, idx in tier_indices:
                tier_emails = tiers[idx].get("emails", [])
                if self._email_in_list(email, tier_emails):
                    return idx

            for idx, t in enumerate(tiers):
                if isinstance(t, dict) and t.get("tier_id", idx) == 0:
                    return idx

            return 0

        model_id = email
        tiers = cfg.get("model_tiers", [])
        if not isinstance(tiers, list) or not tiers:
            raise Exception(
                "Configuration Error: No model tiers defined. Please add at least one model tier (Tier 0)."
            )

        tier_indices = [
            (t.get("tier_id", idx), idx)
            for idx, t in enumerate(tiers)
            if isinstance(t, dict)
        ]
        tier_indices.sort(reverse=True, key=lambda x: x[0])

        for _tier_id, idx in tier_indices:
            if model_id in (tiers[idx].get("models", []) or []):
                return idx

        for idx, t in enumerate(tiers):
            if isinstance(t, dict) and t.get("tier_id", idx) == 0:
                return idx

        return 0

    def _check_specific_limit(
        self, source_name: str, limits: Dict[str, Any], history: List[float]
    ) -> Tuple[bool, Optional[str]]:
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
        self,
        cfg: Dict[str, Any],
        user_id: str,
        email: str,
        model_id: str,
        user_tier_idx: int,
        model_tier_idx: int,
    ) -> Tuple[bool, Optional[str]]:
        now = time.time()
        ut_cfg = cfg["user_tiers"][user_tier_idx]
        mt_cfg = cfg["model_tiers"][model_tier_idx]

        if user_id not in self.user_history:
            self.user_history[user_id] = {}

        target_history_key = (
            "GLOBAL" if cfg.get("global_limit", {}).get("enabled", False) else model_id
        )
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
            if model_hit:
                return False, None
            return False, None

        if user_hit:
            return True, user_reason
        if model_hit:
            return True, model_reason

        return False, None

    # ----------------------------
    # Group System
    # ----------------------------
    def _get_effective_group_permissions(
        self, user_group: Dict[str, Any], model_group: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str]:
        permissions = user_group.get("permissions", {})
        if not isinstance(permissions, dict):
            permissions = {}

        if model_group and isinstance(model_group, dict):
            mg_id = model_group.get("id")
            if isinstance(mg_id, str):
                model_perms = permissions.get(mg_id)
                if isinstance(model_perms, dict) and len(model_perms) > 0:
                    return model_perms, f"permissions.{mg_id}"

        default_perms = user_group.get("default_permissions", {})
        if isinstance(default_perms, dict):
            return default_perms, "default_permissions"

        return {}, "none"

    def _check_rate_limit_group(
        self,
        cfg: Dict[str, Any],
        user_id: str,
        user_group: Dict[str, Any],
        model_group: Optional[Dict[str, Any]],
        model_perms: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Check rate limits using new Group system.
        """
        if not model_group:
            return False, None

        model_group_id = model_group.get("id")
        if not isinstance(model_group_id, str) or not model_group_id:
            return False, None

        if model_perms and not model_perms.get("enabled", False):
            user_group_name = user_group.get("name", user_group.get("id"))
            model_group_name = model_group.get("name", model_group.get("id"))
            msg = cfg.get("custom_strings", {}).get(
                "group_no_permission",
                "Access Denied: User group '{u_group}' cannot access model group '{m_group}'",
            )
            raise Exception(
                msg.format(u_group=user_group_name, m_group=model_group_name)
            )

        now = time.time()
        if user_id not in self.user_history:
            self.user_history[user_id] = {}

        target_history_key = (
            "GLOBAL"
            if cfg.get("global_limit", {}).get("enabled", False)
            else model_group_id
        )
        if target_history_key not in self.user_history[user_id]:
            self.user_history[user_id][target_history_key] = []

        history = self.user_history[user_id][target_history_key]
        history = [t for t in history if now - t < 86400]
        self.user_history[user_id][target_history_key] = history

        source_name = f"{user_group.get('name')} → {model_group.get('name')}"
        is_limited, reason = self._check_specific_limit(
            source_name, model_perms, history
        )
        return is_limited, reason

    def _apply_context_clip(
        self,
        cfg: Dict[str, Any],
        body: dict,
        user_group: Dict[str, Any],
        model_group: Optional[Dict[str, Any]],
        model_perms: Dict[str, Any],
        perms_source: str,
    ) -> None:
        """
        Apply context clipping (max non-system messages) and log clip information.
        """
        clip = self._coerce_nonneg_int(model_perms.get("clip", 0))
        if clip <= 0:
            return

        messages, source = self._select_messages_with_source(body)
        if messages and body.get("messages") is not messages:
            body["messages"] = messages

        before_total = len(messages)
        before_system = len([m for m in messages if m.get("role") == "system"])
        before_non_system = before_total - before_system

        applied = False
        if before_total > 0:
            system_msgs = [m for m in messages if m.get("role") == "system"]
            non_system_msgs = [m for m in messages if m.get("role") != "system"]
            if len(non_system_msgs) > clip:
                body["messages"] = system_msgs + non_system_msgs[-clip:]
                applied = True

        out_msgs = body.get("messages", [])
        if not isinstance(out_msgs, list):
            out_msgs = []

        after_total = len(out_msgs)
        after_system = len(
            [m for m in out_msgs if isinstance(m, dict) and m.get("role") == "system"]
        )
        after_non_system = after_total - after_system

        self._log(
            cfg,
            "OAG",
            "Clip Info",
            {
                "user_group": user_group.get("name", user_group.get("id")),
                "model_group": (
                    model_group.get("name", model_group.get("id"))
                    if model_group
                    else "Ungrouped"
                ),
                "perms_source": perms_source,
                "clip": clip,
                "messages_source": source,
                "before": {
                    "total": before_total,
                    "system": before_system,
                    "non_system": before_non_system,
                },
                "after": {
                    "total": after_total,
                    "system": after_system,
                    "non_system": after_non_system,
                },
                "applied": applied,
            },
        )

    # ----------------------------
    # Open WebUI hooks
    # ----------------------------
    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> dict:
        """
        Process incoming requests.
        Performs authentication, whitelist/blacklist checks, tier/group resolution,
        rate limiting, context clipping, and ad injection.
        """
        cfg = self._get_cfg()

        def get_msg(key: str, default: str) -> str:
            cs = cfg.get("custom_strings", {})
            return cs.get(key, default) if isinstance(cs, dict) else default

        if not cfg.get("base", {}).get("enabled", True):
            return body

        if not __user__:
            return body

        email = __user__.get("email", "")
        role = __user__.get("role", "user")
        user_id = __user__.get("id") or email or "anonymous"
        model_id = self._normalize_model_id(body.get("model", ""))

        self._log(
            cfg, "INLET", "Request Received", {"user": __user__, "model": model_id}
        )

        if role == "admin" and not cfg.get("base", {}).get("admin_effective", False):
            return body

        if cfg.get("exemption", {}).get("enabled", False) and self._email_in_list(
            email, cfg.get("exemption", {}).get("emails")
        ):
            self._log(cfg, "OAG", "Exempted User", self._normalize_email(email))
            return body

        if cfg.get("auth", {}).get("enabled", False):
            domain = email.split("@")[-1].strip().casefold() if "@" in email else ""
            providers = cfg.get("auth", {}).get("providers", [])
            if not isinstance(providers, list) or domain not in [
                str(p).strip().casefold() for p in providers
            ]:
                raise Exception(cfg.get("auth", {}).get("deny_msg", "Access Denied"))

        if cfg.get("whitelist", {}).get("enabled", False) and not self._email_in_list(
            email, cfg.get("whitelist", {}).get("emails")
        ):
            raise Exception(
                get_msg("whitelist_deny", "Access Denied: Not in whitelist.")
            )

        for reason in (
            cfg.get("ban_reasons", [])
            if isinstance(cfg.get("ban_reasons"), list)
            else []
        ):
            if not isinstance(reason, dict):
                continue
            if self._email_in_list(email, reason.get("emails", [])):
                raise Exception(reason.get("msg", "Account Suspended"))

        # === NEW: Group System Logic (v0.2.0+) ===
        if isinstance(cfg.get("user_groups"), list) and len(cfg["user_groups"]) > 0:
            user_group = self._get_user_group(cfg, email)
            model_group = self._get_model_group(cfg, model_id)
            model_perms, perms_source = self._get_effective_group_permissions(
                user_group, model_group
            )

            self._log(
                cfg,
                "OAG",
                "Group Match",
                {
                    "user_group": user_group.get("name"),
                    "model_group": (
                        model_group.get("name") if model_group else "Ungrouped"
                    ),
                    "model_group_id": (model_group.get("id") if model_group else None),
                    "perms_source": perms_source,
                    "effective_clip": model_perms.get("clip"),
                },
            )

            is_limited, limit_reason = self._check_rate_limit_group(
                cfg=cfg,
                user_id=user_id,
                user_group=user_group,
                model_group=model_group,
                model_perms=model_perms,
            )

            if is_limited:
                self._log(cfg, "OAG", "Rate Limit Hit", limit_reason)
                if cfg.get("fallback", {}).get("enabled", False):
                    fallback_model = cfg.get("fallback", {}).get("model")
                    if isinstance(fallback_model, str) and fallback_model.strip():
                        body["model"] = fallback_model
                    if (
                        cfg.get("fallback", {}).get("notify", True)
                        and __event_emitter__
                    ):
                        await __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": cfg.get("fallback", {}).get(
                                        "notify_msg", ""
                                    ),
                                    "done": True,
                                },
                            }
                        )
                else:
                    raise Exception(
                        get_msg(
                            "rate_limit_deny", "Rate Limit Exceeded: {reason}"
                        ).format(reason=limit_reason)
                    )

            # Record access (per model_group or GLOBAL or ungrouped)
            if user_id not in self.user_history:
                self.user_history[user_id] = {}

            target_history_key = (
                "GLOBAL"
                if cfg.get("global_limit", {}).get("enabled", False)
                else (model_group.get("id") if model_group else "ungrouped")
            )
            if target_history_key not in self.user_history[user_id]:
                self.user_history[user_id][target_history_key] = []
            self.user_history[user_id][target_history_key].append(time.time())

            # Context clipping (even for ungrouped models -> uses default_permissions)
            self._apply_context_clip(
                cfg, body, user_group, model_group, model_perms, perms_source
            )

        # === LEGACY: Tier System (v0.1.x, deprecated) ===
        else:
            u_tier_idx = self._get_tier(cfg, email, "user")
            m_tier_idx = self._get_tier(cfg, model_id, "model")
            ut_cfg = cfg["user_tiers"][u_tier_idx]
            mt_cfg = cfg["model_tiers"][m_tier_idx]
            u_tier_id = ut_cfg.get("tier_id", u_tier_idx)
            m_tier_id = mt_cfg.get("tier_id", m_tier_idx)

            if ut_cfg.get("deny_model_enabled") and model_id in (
                ut_cfg.get("deny_models", []) or []
            ):
                raise Exception(
                    get_msg(
                        "user_deny_model",
                        "Tier {u_tier} users cannot use model {model_id}",
                    ).format(u_tier=u_tier_id, model_id=model_id)
                )

            if cfg.get("model_tiers_config", {}).get("match_tiers", False):
                if u_tier_id != m_tier_id:
                    raise Exception(
                        get_msg(
                            "tier_mismatch",
                            "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
                        ).format(u_tier=u_tier_id, m_tier=m_tier_id)
                    )
            else:
                access_list = mt_cfg.get("access_list", []) or []
                if access_list:
                    if mt_cfg.get("mode_whitelist", False):
                        if not self._email_in_list(email, access_list):
                            raise Exception(
                                get_msg(
                                    "model_wl_deny",
                                    "Access Denied to Tier {m_tier} Model (Whitelist)",
                                ).format(m_tier=m_tier_id)
                            )
                    else:
                        if self._email_in_list(email, access_list):
                            raise Exception(
                                get_msg(
                                    "model_bl_deny",
                                    "Access Denied to Tier {m_tier} Model (Blacklist)",
                                ).format(m_tier=m_tier_id)
                            )

            is_limited, limit_reason = self._check_rate_limit(
                cfg, user_id, email, model_id, u_tier_idx, m_tier_idx
            )
            if is_limited:
                self._log(cfg, "OAG", "Rate Limit Hit", limit_reason)
                if cfg.get("fallback", {}).get("enabled", False):
                    fallback_model = cfg.get("fallback", {}).get("model")
                    if isinstance(fallback_model, str) and fallback_model.strip():
                        body["model"] = fallback_model
                    if (
                        cfg.get("fallback", {}).get("notify", True)
                        and __event_emitter__
                    ):
                        await __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": cfg.get("fallback", {}).get(
                                        "notify_msg", ""
                                    ),
                                    "done": True,
                                },
                            }
                        )
                else:
                    raise Exception(
                        get_msg(
                            "rate_limit_deny", "Rate Limit Exceeded: {reason}"
                        ).format(reason=limit_reason)
                    )
            else:
                target = (
                    "GLOBAL"
                    if cfg.get("global_limit", {}).get("enabled", False)
                    else model_id
                )
                if target not in self.user_history[user_id]:
                    self.user_history[user_id][target] = []
                self.user_history[user_id][target].append(time.time())

            clip_count = max(
                self._coerce_nonneg_int(ut_cfg.get("clip", 0)),
                self._coerce_nonneg_int(mt_cfg.get("clip", 0)),
            )
            if clip_count > 0:
                messages, source = self._select_messages_with_source(body)
                if messages and body.get("messages") is not messages:
                    body["messages"] = messages
                if isinstance(body.get("messages"), list):
                    msgs = body["messages"]
                    before_total = len(msgs)
                    sys_msg = next(
                        (
                            m
                            for m in msgs
                            if isinstance(m, dict) and m.get("role") == "system"
                        ),
                        None,
                    )
                    chat_msgs = [
                        m
                        for m in msgs
                        if isinstance(m, dict) and m.get("role") != "system"
                    ]
                    chat_msgs = chat_msgs[-clip_count:]
                    if sys_msg:
                        chat_msgs.insert(0, sys_msg)
                    body["messages"] = chat_msgs
                    after_total = len(chat_msgs)
                    self._log(
                        cfg,
                        "OAG",
                        "Clip Info (Legacy)",
                        {
                            "clip": clip_count,
                            "messages_source": source,
                            "before_total": before_total,
                            "after_total": after_total,
                        },
                    )

        # Ads injection (applies to both systems)
        if (
            cfg.get("ads", {}).get("enabled", False)
            and cfg.get("ads", {}).get("content")
            and __event_emitter__
        ):
            content = cfg.get("ads", {}).get("content", [])
            if isinstance(content, list):
                valid_ads = [ad for ad in content if isinstance(ad, str) and ad.strip()]
                if valid_ads:
                    ad_text = random.choice(valid_ads)
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {"description": f"AD: {ad_text}", "done": True},
                        }
                    )

        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        cfg = self._get_cfg()
        self._log(cfg, "OUTLET", "Response", {"user": __user__})
        return body

    async def stream(self, event: Any, __user__: Optional[dict] = None) -> Any:
        cfg = self._get_cfg()
        if cfg.get("logging", {}).get("enabled", False) and cfg.get("logging", {}).get(
            "stream", False
        ):
            log_data = event
            if isinstance(event, bytes):
                try:
                    log_data = event.decode("utf-8")
                except Exception:
                    log_data = "<binary>"
            self._log(cfg, "STREAM", "Chunk", {"data": log_data, "user": __user__})
        return event
