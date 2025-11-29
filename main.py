"""
title: OpenAccess Guard
author: zealmult
author_url: https://github.com/zealmult
funding_url: https://breathai.top/
homepage: https://github.com/zealmult/OpenAccess-Guard/
version: 1.0
"""

import time
import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, Callable, Awaitable, Any, List
from pydantic import BaseModel, Field


class Filter:

    # ============================================================
    # 1. UI CONFIGURATION (must remain inside class for OpenWebUI)
    # ============================================================
    class Valves(BaseModel):

        # ===== Global Filter Settings =====
        priority: int = Field(default=99, description="Execution priority of this filter.")
        enabled: bool = Field(default=True, description="Enable the combined filter system.")
        enabled_for_admins: bool = Field(default=True, description="Apply rules to admin users as well.")

        # ===== Access Control (Approval System) =====
        approval_required: bool = Field(
            default=False,
            description="If enabled, only approved emails may access advanced models."
        )

        approved_user_emails: str = Field(
            default="",
            description="Emails allowed to access advanced models. Supports comma/newline/semicolon separated text."
        )

        approval_required_message: str = Field(
            default="Your account is not approved to access advanced models.",
            description="Message returned when a user is not in the approved list."
        )

        # ===== Bypass + Plus Users =====
        bypass_user_emails: str = Field(
            default="",
            description="Emails completely exempt from rate limits."
        )

        plus_user_emails: str = Field(
            default="",
            description="Emails considered Plus users. They use the Plus rate limits."
        )

        # ===== Rate Limit Rules =====
        requests_per_minute: Optional[int] = Field(default=10)
        requests_per_hour: Optional[int] = Field(default=50)
        sliding_window_limit: Optional[int] = Field(default=100)
        sliding_window_minutes: Optional[int] = Field(default=180)

        # Plus-user rate limits
        plus_requests_per_minute: Optional[int] = Field(default=None)
        plus_requests_per_hour: Optional[int] = Field(default=None)
        plus_sliding_window_limit: Optional[int] = Field(default=None)

        global_limit: bool = Field(
            default=True,
            description="If enabled, rate limits apply across all models globally."
        )

        fallback_on_limit: bool = Field(
            default=True,
            description="If true, switch to backup model when exceeding limits instead of raising an error."
        )

        backup_model: str = Field(
            default="qwen2:0.5b",
            description="Backup model used when rate limits are exceeded."
        )

        limit_exceeded_message: str = Field(
            default="Rate limit exceeded on model '{model_id}'. You have used {request_count} requests. Try again after {future_time_str}.",
            description="Error message when limit exceeded and fallback is disabled."
        )

        # ===== Ban System =====
        ban_reason_1_emails: str = Field(default="", description="Ban list for reason 1.")
        ban_reason_2_emails: str = Field(default="", description="Ban list for reason 2.")
        ban_reason_3_emails: str = Field(default="", description="Ban list for reason 3.")
        ban_reason_4_emails: str = Field(default="", description="Ban list for reason 4.")
        ban_reason_5_emails: str = Field(default="", description="Ban list for reason 5.")
        ban_reason_6_emails: str = Field(default="", description="Ban list for reason 6.")

        # Custom reason messages (fully editable)
        ban_message_1: str = Field(default="Your account has been temporarily suspended. Reason: Category 1.")
        ban_message_2: str = Field(default="Your account has been temporarily suspended. Reason: Category 2.")
        ban_message_3: str = Field(default="Your account has been temporarily suspended. Reason: Category 3.")
        ban_message_4: str = Field(default="Your account has been permanently suspended. Reason: Category 4.")
        ban_message_5: str = Field(default="Your account has been permanently suspended. Reason: Category 5.")
        ban_message_6: str = Field(default="Your account has been permanently suspended. Reason: Category 6.")

    # ============================================================
    # 2. INITIALIZATION
    # ============================================================
    def __init__(self):
        self.valves = self.Valves()
        self.user_requests = {}

        # Map reason numbers → message field names
        self.ban_messages = {
            1: "ban_message_1",
            2: "ban_message_2",
            3: "ban_message_3",
            4: "ban_message_4",
            5: "ban_message_5",
            6: "ban_message_6",
        }

        self.ban_lists = {
            1: "ban_reason_1_emails",
            2: "ban_reason_2_emails",
            3: "ban_reason_3_emails",
            4: "ban_reason_4_emails",
            5: "ban_reason_5_emails",
            6: "ban_reason_6_emails",
        }

    # ============================================================
    # 3. EMAIL PARSING UTIL
    # ============================================================
    def _parse(self, s: Optional[str]) -> List[str]:
        if not s:
            return []
        arr = re.split(r"[,\n;\s]+", s)
        return [x.strip() for x in arr if x.strip()]

    # ============================================================
    # 4. BAN CHECKING
    # ============================================================
    def check_ban(self, email: Optional[str]) -> Optional[int]:
        if not email:
            return None

        for reason, field_name in self.ban_lists.items():
            emails = self._parse(getattr(self.valves, field_name))
            if email in emails:
                return reason
        return None

    # ============================================================
    # 5. RATE LIMIT SUPPORT FUNCTIONS
    # ============================================================
    def prune_requests(self, user_id: str, model_id: str):
        now = time.time()
        retention = max(
            self.valves.sliding_window_minutes * 60,
            3600 if self.valves.requests_per_hour else 60,
        )

        if user_id not in self.user_requests:
            self.user_requests[user_id] = {}

        for m in list(self.user_requests[user_id].keys()):
            self.user_requests[user_id][m] = [
                t for t in self.user_requests[user_id][m] if now - t < retention
            ]

    def log_request(self, user_id: str, model_id: str):
        self.user_requests.setdefault(user_id, {}).setdefault(model_id, []).append(time.time())

    # ============================================================
    # 6. RATE LIMIT DECISION ENGINE
    # ============================================================
    def rate_limited(self, user_id: str, model_id: str, is_plus: bool) -> Tuple[bool, Optional[int], int]:

        self.prune_requests(user_id, model_id)

        if self.valves.global_limit:
            all_reqs = []
            for v in self.user_requests.get(user_id, {}).values():
                all_reqs.extend(v)
        else:
            all_reqs = self.user_requests.get(user_id, {}).get(model_id, [])

        now = time.time()

        # Use plus limits if applicable
        rpm = self.valves.plus_requests_per_minute if is_plus and self.valves.plus_requests_per_minute else self.valves.requests_per_minute
        rph = self.valves.plus_requests_per_hour if is_plus and self.valves.plus_requests_per_hour else self.valves.requests_per_hour
        swl = self.valves.plus_sliding_window_limit if is_plus and self.valves.plus_sliding_window_limit else self.valves.sliding_window_limit

        if rpm:
            last_minute = [t for t in all_reqs if now - t < 60]
            if len(last_minute) >= rpm:
                wait = int(60 - (now - min(last_minute)) + 1)
                return True, wait, len(last_minute)

        if rph:
            last_hour = [t for t in all_reqs if now - t < 3600]
            if len(last_hour) >= rph:
                wait = int(3600 - (now - min(last_hour)) + 1)
                return True, wait, len(last_hour)

        if swl:
            window = [t for t in all_reqs if now - t < self.valves.sliding_window_minutes * 60]
            if len(window) >= swl:
                wait = int(self.valves.sliding_window_minutes * 60 - (now - min(window)) + 1)
                return True, wait, len(window)

        return False, None, len(all_reqs)

    # ============================================================
    # 7. MAIN ENTRY HOOK (OpenWebUI)
    # ============================================================
    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __model__: dict = None,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
        **kwargs
    ) -> dict:

        # Filter disabled
        if not self.valves.enabled:
            return body

        # No user info
        if __user__ is None:
            return body

        user_id = __user__.get("id")
        role = __user__.get("role")
        email = __user__.get("email")
        model_id = __model__["id"] if __model__ else "default_model"

        # Admin bypass
        if role == "admin" and not self.valves.enabled_for_admins:
            return body

        # ======== BAN LOGIC ========
        reason = self.check_ban(email)
        if reason is not None:
            message_field = self.ban_messages[reason]
            final_msg = getattr(self.valves, message_field)

            if __event_emitter__:
                asyncio.create_task(
                    __event_emitter__({"type": "error", "data": {"description": final_msg, "done": True}})
                )
            raise Exception(final_msg)

        # ======== APPROVAL CHECK ========
        if self.valves.approval_required:
            approved = self._parse(self.valves.approved_user_emails)
            if email not in approved:
                raise Exception(self.valves.approval_required_message)

        # ======== BYPASS CHECK ========
        bypass = self._parse(self.valves.bypass_user_emails)
        if email in bypass:
            return body

        # ======== PLUS CHECK ========
        plus_list = self._parse(self.valves.plus_user_emails)
        is_plus = email in plus_list

        # ======== RATE LIMIT ========
        exceeded, wait_time, count = self.rate_limited(user_id, model_id, is_plus)

        if exceeded:
            wait_safe = max(wait_time or 1, 1)
            future = datetime.now() + timedelta(seconds=wait_safe)
            future_str = future.strftime("%I:%M %p")

            if self.valves.fallback_on_limit:
                body["model"] = self.valves.backup_model
                if __event_emitter__:
                    asyncio.create_task(
                        __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": f"Rate limit reached. You have been switched to backup model '{self.valves.backup_model}'.",
                                    "done": True,
                                },
                            }
                        )
                    )
            else:
                msg = self.valves.limit_exceeded_message.format(
                    model_id=model_id, request_count=count, future_time_str=future_str
                )
                raise Exception(msg)

        # Log the request
        self.log_request(user_id, model_id)

        return body
