"""
title: OpenAccess Guard Pro
author: zealmult
author_url: https://github.com/zealmult
funding_url: https://breathai.top/
homepage: https://github.com/zealmult/OpenAccess-Guard/
version: 1.4
"""

import time
import re
import json
import threading
import random
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Awaitable, List, Dict
from pydantic import BaseModel, Field

# ============================================================
# 0. 默认配置与 HTML 模板
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
    "priority": {"user_priority": False},  # Global Priority
    "global_limit": {"enabled": False},
    "user_tiers": [],
    "model_tiers_config": {"match_tiers": False},
    "model_tiers": [],
    "ban_system": {},
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

# 初始化列表结构
for i in range(6):
    DEFAULT_CONFIG["user_tiers"].append(
        {
            "enabled": True if i == 0 else False,
            "emails": [],
            "rpm": 0,
            "rph": 0,
            "win_time": 0,
            "win_limit": 0,
            "clip": 0,
            "deny_model_enabled": False,
            "deny_models": [],
        }
    )
    # 模型 Tier 新增 user_priority 字段
    DEFAULT_CONFIG["model_tiers"].append(
        {
            "enabled": False,
            "models": [],
            "rpm": 0,
            "rph": 0,
            "win_time": 0,
            "win_limit": 0,
            "clip": 0,
            "mode_whitelist": False,
            "access_list": [],
            "user_priority": False,  # New per-tier priority override
        }
    )

for i in range(1, 11):
    DEFAULT_CONFIG["ban_system"][f"reason_{i}"] = {
        "emails": [],
        "msg": f"Account Suspended: Reason {i}",
    }
    DEFAULT_CONFIG["ads"]["content"].append("")


# 压缩的 HTML/JS 界面代码
HTML_UI = """
<!DOCTYPE html>
<html lang="zh-CN">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenAccess Guard Configurator</title>
    <style>
        :root {
            --primary: #007AFF;
            --primary-hover: #0062cc;
            --bg-body: #F2F2F7;
            --bg-sidebar: #FFFFFF;
            --bg-card: #FFFFFF;
            --text-main: #1C1C1E;
            --text-secondary: #8E8E93;
            --border: #E5E5EA;
            --danger: #FF3B30;
            --success: #34C759;
            --radius: 12px;
            --shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
            --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-body: #000000;
                --bg-sidebar: #1C1C1E;
                --bg-card: #1C1C1E;
                --text-main: #FFFFFF;
                --text-secondary: #98989D;
                --border: #38383A;
            }
        }

        * {
            box-sizing: border-box;
            outline: none;
            -webkit-tap-highlight-color: transparent;
        }

        body {
            margin: 0;
            font-family: var(--font-stack);
            background: var(--bg-body);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            overflow: hidden;
        }

        /* --- Layout --- */
        .app-container {
            display: flex;
            width: 100%;
            height: 100%;
        }

        /* Sidebar */
        .sidebar {
            width: 260px;
            background: var(--bg-sidebar);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 20px;
            flex-shrink: 0;
            transition: all 0.3s ease;
            z-index: 100;
            position: relative;
        }

        .sidebar.collapsed {
            width: 70px;
            padding: 20px 10px;
        }

        .sidebar.collapsed .brand span:not(.icon),
        .sidebar.collapsed .nav-item span:not(.icon),
        .sidebar.collapsed .lang-switch {
            display: none;
        }

        .sidebar.collapsed .brand {
            justify-content: center;
        }

        .sidebar.collapsed .nav-item {
            justify-content: center;
            padding: 12px 8px;
        }

        .sidebar.collapsed .icon {
            margin: 0 auto;
        }

        .sidebar-toggle {
            position: absolute;
            right: -12px;
            top: 50%;
            transform: translateY(-50%);
            width: 24px;
            height: 24px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 101;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: all 0.2s;
        }

        .sidebar-toggle:hover {
            background: var(--primary);
            border-color: var(--primary);
        }

        .sidebar-toggle::before {
            content: '';
            width: 6px;
            height: 6px;
            border-left: 2px solid var(--text-main);
            border-bottom: 2px solid var(--text-main);
            transform: rotate(45deg);
            margin-left: 2px;
        }

        .sidebar-toggle:hover::before {
            border-color: white;
        }

        .sidebar.collapsed .sidebar-toggle::before {
            transform: rotate(-135deg);
            margin-left: -2px;
        }

        .mobile-menu-btn {
            display: none;
            position: fixed;
            top: 15px;
            left: 15px;
            z-index: 200;
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1.2rem;
            line-height: 1;
        }

        .icon {
            display: inline-block;
            width: 24px;
            text-align: center;
            font-style: normal;
            font-size: 1.1rem;
            line-height: 1;
        }

        .brand {
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-main);
        }


        .nav-item {
            padding: 12px 16px;
            border-radius: 8px;
            cursor: pointer;
            color: var(--text-main);
            font-weight: 500;
            margin-bottom: 4px;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .nav-item:hover {
            background: rgba(0, 0, 0, 0.05);
        }

        .nav-item.active {
            background: var(--primary);
            color: white;
        }

        .lang-switch {
            margin-top: auto;
            display: flex;
            background: var(--border);
            padding: 4px;
            border-radius: 8px;
        }

        .lang-btn {
            flex: 1;
            border: none;
            background: transparent;
            padding: 6px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 600;
        }

        .lang-btn.active {
            background: var(--bg-card);
            color: var(--text-main);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        /* Main Content */
        .main-content {
            flex: 1;
            overflow-y: auto;
            padding: 30px;
            position: relative;
        }

        .page {
            display: none;
            max-width: 800px;
            margin: 0 auto;
            padding-bottom: 60px;
        }

        .page.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }

        /* --- Components --- */
        h1 {
            margin: 0 0 20px 0;
            font-size: 2rem;
        }

        h2 {
            font-size: 1.4rem;
            margin-top: 30px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }

        h3 {
            font-size: 1.1rem;
            margin: 0;
            font-weight: 600;
        }

        p {
            line-height: 1.6;
            color: var(--text-secondary);
            margin-bottom: 15px;
        }

        /* Cards */
        .card {
            background: var(--bg-card);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            margin-bottom: 20px;
            overflow: hidden;
            transition: 0.3s;
        }

        .card-header {
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
            background: rgba(0, 0, 0, 0.01);
        }

        .card-header:hover {
            background: rgba(0, 0, 0, 0.03);
        }

        .card-body {
            padding: 0 20px 20px 20px;
            display: none;
        }

        .card.open .card-body {
            display: block;
        }

        .chevron {
            transition: transform 0.3s;
            width: 20px;
            height: 20px;
            opacity: 0.5;
        }

        .card.open .chevron {
            transform: rotate(180deg);
        }

        /* Controls */
        .control-group {
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
        }

        .control-group:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .toggle-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .label-text {
            font-weight: 500;
            font-size: 1rem;
        }

        .description {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 4px;
            display: block;
            line-height: 1.4;
        }

        /* iOS Switch */
        .switch {
            position: relative;
            display: inline-block;
            width: 50px;
            height: 30px;
            flex-shrink: 0;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 34px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 2px;
            bottom: 2px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        input:checked+.slider {
            background-color: var(--primary);
        }

        input:checked+.slider:before {
            transform: translateX(20px);
        }

        /* Inputs */
        input[type="text"],
        input[type="number"],
        textarea {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-body);
            color: var(--text-main);
            font-size: 1rem;
            margin-top: 8px;
            transition: 0.2s;
        }

        input:focus,
        textarea:focus {
            border-color: var(--primary);
            background: var(--bg-card);
        }

        .input-row {
            display: flex;
            gap: 15px;
            margin-top: 15px;
            flex-wrap: wrap;
        }

        .input-col {
            flex: 1;
            min-width: 120px;
        }

        .input-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 4px;
            display: block;
        }

        /* Tags Input */
        .tag-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            padding: 8px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg-body);
            min-height: 48px;
            margin-top: 8px;
        }

        .tag {
            background: var(--primary);
            color: white;
            padding: 4px 10px;
            border-radius: 16px;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .tag span {
            cursor: pointer;
            opacity: 0.7;
            font-weight: bold;
        }

        .tag span:hover {
            opacity: 1;
        }

        .tag-input-wrapper {
            display: flex;
            gap: 10px;
            margin-top: 8px;
        }

        .btn-add {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--primary);
            width: 40px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .btn-add:hover {
            background: var(--border);
        }

        /* JSON Editor Area */
        .json-section {
            margin-top: 40px;
            border-top: 1px solid var(--border);
            padding-top: 20px;
        }

        #json-editor {
            font-family: monospace;
            font-size: 0.85rem;
            height: 300px;
            background: #282c34;
            color: #abb2bf;
            border: none;
        }

        .btn-copy {
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            margin-top: 10px;
        }

        .btn-copy:hover {
            background: var(--primary-hover);
        }

        .btn-secondary {
            background: var(--bg-body);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            flex: 1;
            transition: 0.2s;
            font-weight: 500;
        }

        .btn-secondary:hover {
            background: var(--border);
        }

        /* Ad Card */
        .ad-banner {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin-top: 20px;
        }

        .ad-banner a {
            color: #fff;
            text-decoration: underline;
            font-weight: bold;
        }

        /* Warning Banner */
        .warning-banner {
            background: #FFF4E5;
            border: 1px solid #FFD4A8;
            color: #663C00;
            padding: 15px;
            border-radius: var(--radius);
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.95rem;
            line-height: 1.4;
        }

        .dark .warning-banner {
            background: #3E2C18;
            border-color: #5D4018;
            color: #FFD4A8;
        }

        /* Danger Button */
        .btn-danger {
            background: transparent;
            border: 1px solid var(--danger);
            color: var(--danger);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            margin-top: 10px;
            transition: 0.2s;
        }

        .btn-danger:hover {
            background: var(--danger);
            color: white;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .app-container {
                flex-direction: row;
                /* Keep row but handle sidebar differently */
            }

            .sidebar {
                position: fixed;
                left: 0;
                top: 0;
                bottom: 0;
                transform: translateX(-100%);
                width: 260px;
                border-right: 1px solid var(--border);
                box-shadow: 2px 0 10px rgba(0, 0, 0, 0.1);
            }

            .sidebar.mobile-open {
                transform: translateX(0);
            }

            .sidebar-toggle {
                display: none;
            }

            .mobile-menu-btn {
                display: block;
            }

            .main-content {
                padding-top: 60px;
                /* Space for mobile menu btn */
                width: 100%;
            }

            .main-content {
                padding: 15px;
            }
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .sub-section {
            margin-top: 15px;
            padding-left: 15px;
            border-left: 2px solid var(--border);
        }

        .hidden {
            display: none !important;
        }

        .tutorial-block {
            margin-bottom: 20px;
        }

        .tutorial-block h3 {
            margin-bottom: 8px;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tutorial-block p {
            margin-top: 0;
            font-size: 0.95rem;
        }
    </style>
</head>

<body>

    <div class="mobile-menu-btn" onclick="toggleMobileMenu()">
        <span class="icon">☰</span>
    </div>

    <div class="app-container">
        <nav class="sidebar" id="sidebar">
            <div class="sidebar-toggle" onclick="toggleSidebar()"></div>
            <div class="brand">
                <span class="icon">●</span> <span>OAG Config</span>
            </div>
            <div class="nav-item active" onclick="router('settings')">
                <span class="icon">⚙</span> <span data-i18n="nav_settings">Settings</span>
            </div>
            <div class="nav-item" onclick="router('tutorial')">
                <span class="icon">?</span> <span data-i18n="nav_tutorial">Tutorial</span>
            </div>
            <div class="nav-item" onclick="router('info')">
                <span class="icon">i</span> <span data-i18n="nav_about">About</span>
            </div>

            <div class="lang-switch">
                <button class="lang-btn" id="btn-en" onclick="setLang('en')">EN</button>
                <button class="lang-btn active" id="btn-zh" onclick="setLang('zh')">中文</button>
            </div>
        </nav>

        <main class="main-content">
            <!-- SETTINGS PAGE -->
            <div id="settings" class="page active">
                <h1 data-i18n="page_settings_title">Configuration</h1>

                <!-- New Tutorial Banner -->
                <div class="warning-banner">
                    <span class="icon">⚠️</span>
                    <span data-i18n="settings_banner_hint" onclick="router('tutorial')"
                        style="cursor:pointer">Important: Please read the Tutorial first!</span>
                </div>

                <!-- 1. Base Settings -->
                <div class="card open">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_base">Base Settings</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="base_enabled">Enable OpenAccess Guard</div>
                                    <div class="description" data-i18n="base_enabled_desc">Master switch for the plugin.
                                    </div>
                                </div>
                                <label class="switch"><input type="checkbox" id="base_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                        </div>
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="base_admin">Admin Effective</div>
                                    <div class="description" data-i18n="base_admin_desc">Apply rules to admin accounts
                                        too.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="base_admin"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Auth Email -->
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_auth">Auth Email Settings</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="auth_enabled">Approval Required</div>
                                    <div class="description" data-i18n="auth_enabled_desc">Only allow specific email
                                        domains.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="auth_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>

                            <div id="auth_logic_area" class="sub-section hidden">
                                <label class="input-label" data-i18n="auth_providers">Allowed Providers (e.g.,
                                    gmail.com)</label>
                                <div id="auth_providers_tags" class="tag-container"></div>
                                <div class="tag-input-wrapper">
                                    <input type="text" id="auth_provider_input" placeholder="example.com"
                                        onkeydown="handleTagInput(event, 'auth.providers', 'auth_providers_tags')">
                                    <button class="btn-add"
                                        onclick="addTagFromInput('auth_provider_input', 'auth.providers', 'auth_providers_tags')">+</button>
                                </div>

                                <label class="input-label" style="margin-top:15px" data-i18n="auth_msg">Deny
                                    Message</label>
                                <input type="text" id="auth_msg" oninput="updateConfig()">
                                <div class="description" data-i18n="auth_msg_desc">Message shown to unverified email
                                    users.</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 3. Whitelist & Exemption -->
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_lists">Whitelist & Exemption</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <!-- Whitelist -->
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="wl_enabled">Enable Whitelist System</div>
                                    <div class="description" data-i18n="wl_enabled_desc">Strict mode: Only listed users
                                        can access.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="wl_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                            <div id="wl_area" class="sub-section hidden">
                                <label class="input-label" data-i18n="wl_users">Whitelist Emails</label>
                                <div id="wl_tags" class="tag-container"></div>
                                <div class="tag-input-wrapper">
                                    <input type="text" id="wl_input" placeholder="user@email.com"
                                        onkeydown="handleTagInput(event, 'whitelist.emails', 'wl_tags')">
                                    <button class="btn-add"
                                        onclick="addTagFromInput('wl_input', 'whitelist.emails', 'wl_tags')">+</button>
                                </div>
                            </div>
                        </div>
                        <!-- Exemption -->
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="ex_enabled">Enable Exemption System</div>
                                    <div class="description" data-i18n="ex_enabled_desc">These users bypass all limits
                                        and checks.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="ex_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                            <div id="ex_area" class="sub-section hidden">
                                <label class="input-label" data-i18n="ex_users">Exempt Emails</label>
                                <div id="ex_tags" class="tag-container"></div>
                                <div class="tag-input-wrapper">
                                    <input type="text" id="ex_input" placeholder="vip@email.com"
                                        onkeydown="handleTagInput(event, 'exemption.emails', 'ex_tags')">
                                    <button class="btn-add"
                                        onclick="addTagFromInput('ex_input', 'exemption.emails', 'ex_tags')">+</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 4. Priority System -->
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_priority">Priority System</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <div class="toggle-row">
                            <div>
                                <div class="label-text" data-i18n="prio_user">User Limit Priority</div>
                                <div class="description" data-i18n="prio_user_desc">If enabled, as long as the user has
                                    quota in their User Tier, they can access even if the Model limit is reached.</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="prio_user" onchange="updateConfig()"><span
                                    class="slider"></span></label>
                        </div>
                    </div>
                </div>

                <!-- 5. User Tiers -->
                <h2 data-i18n="sec_user_tiers">User Tier System</h2>
                <p data-i18n="sec_user_tiers_desc">Categorize users into Tier 0-5. Default is Tier 0.</p>

                <div class="card">
                    <div class="card-body" style="display:block; padding-top:20px;">
                        <div class="toggle-row">
                            <div>
                                <div class="label-text" data-i18n="global_limit">Global Limit</div>
                                <div class="description" data-i18n="global_limit_desc">Limits apply across all models
                                    cumulatively.</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="global_limit"
                                    onchange="updateConfig()"><span class="slider"></span></label>
                        </div>
                    </div>
                </div>

                <div id="user_tiers_container">
                    <!-- JS will inject Tier 0-5 Cards here -->
                </div>

                <!-- 6. Model Tiers -->
                <h2 data-i18n="sec_model_tiers">Model Tier System</h2>
                <div class="card">
                    <div class="card-body" style="display:block; padding-top:20px;">
                        <div class="toggle-row">
                            <div>
                                <div class="label-text" data-i18n="match_tiers">Match Model & User Tiers</div>
                                <div class="description" data-i18n="match_tiers_desc">If ON, Tier X Users can ONLY use
                                    Tier X Models.</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="match_tiers"
                                    onchange="updateConfig()"><span class="slider"></span></label>
                        </div>
                    </div>
                </div>

                <div id="model_tiers_container">
                    <!-- JS will inject Model Tier Cards here -->
                </div>

                <!-- 7. Ban System -->
                <h2 data-i18n="sec_ban">Ban System</h2>
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_ban_reasons">Ban Reasons & Users</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body" id="ban_container">
                        <!-- JS Injects Ban Reasons -->
                    </div>
                </div>

                <!-- 8. Fallback -->
                <h2 data-i18n="sec_fallback">Fallback System</h2>
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_fallback_config">Smart Downgrade (降智)</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="fb_enabled">Enable Fallback</div>
                                    <div class="description" data-i18n="fb_enabled_desc">Auto-switch model when limits
                                        reached.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="fb_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                            <div id="fb_area" class="sub-section hidden">
                                <label class="input-label" data-i18n="fb_model">Fallback Model ID</label>
                                <input type="text" id="fb_model" oninput="updateConfig()"
                                    placeholder="e.g. gpt-3.5-turbo">

                                <div class="toggle-row" style="margin-top:15px">
                                    <div>
                                        <div class="label-text" data-i18n="fb_notify">Show Notification</div>
                                    </div>
                                    <label class="switch"><input type="checkbox" id="fb_notify"
                                            onchange="updateConfig()"><span class="slider"></span></label>
                                </div>

                                <label class="input-label" data-i18n="fb_msg">Notification Message</label>
                                <input type="text" id="fb_msg" oninput="updateConfig()">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 9. Logs & Ads -->
                <h2 data-i18n="sec_misc">Logs & Ads</h2>
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_log_ads">Configuration</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <!-- Logging -->
                        <div class="control-group">
                            <div class="toggle-row">
                                <div class="label-text" data-i18n="log_enabled">Enable Logging System</div>
                                <label class="switch"><input type="checkbox" id="log_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                            <div id="log_area" class="sub-section hidden">
                                <label class="switch" style="transform:scale(0.8)"><input type="checkbox" id="log_oag"
                                        onchange="updateConfig()"><span class="slider"></span></label> <span
                                    data-i18n="log_oag">Record OAG Logs</span><br><br>
                                <label class="switch" style="transform:scale(0.8)"><input type="checkbox" id="log_inlet"
                                        onchange="updateConfig()"><span class="slider"></span></label> <span
                                    data-i18n="log_inlet">Record INLET</span><br><br>
                                <label class="switch" style="transform:scale(0.8)"><input type="checkbox"
                                        id="log_outlet" onchange="updateConfig()"><span class="slider"></span></label>
                                <span data-i18n="log_outlet">Record OUTLET</span><br><br>
                                <label class="switch" style="transform:scale(0.8)"><input type="checkbox"
                                        id="log_stream" onchange="updateConfig()"><span class="slider"></span></label>
                                <span data-i18n="log_stream">Record STREAM (Heavy)</span><br><br>
                                <label class="switch" style="transform:scale(0.8)"><input type="checkbox" id="log_dict"
                                        onchange="updateConfig()"><span class="slider"></span></label> <span
                                    data-i18n="log_dict">Record User Dictionary</span>
                            </div>
                        </div>

                        <!-- Ads -->
                        <div class="control-group">
                            <div class="toggle-row">
                                <div>
                                    <div class="label-text" data-i18n="ads_enabled">Enable Ads System</div>
                                    <div class="description" data-i18n="ads_enabled_desc">Show random messages (1-10) to
                                        users.</div>
                                </div>
                                <label class="switch"><input type="checkbox" id="ads_enabled"
                                        onchange="updateConfig()"><span class="slider"></span></label>
                            </div>
                            <div id="ads_container" class="sub-section hidden">
                                <!-- JS injects ad inputs -->
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 10. Advanced Settings (NEW) -->
                <h2 data-i18n="sec_advanced">Advanced Settings</h2>
                <div class="card">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="sec_custom_strings">Custom Strings</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <p data-i18n="sec_custom_strings_desc">Customize internal system messages. Support
                            {placeholders}.</p>

                        <label class="input-label">Whitelist Deny Message</label>
                        <input type="text" id="cs_whitelist_deny" oninput="updateConfig()">

                        <label class="input-label" style="margin-top:10px">Tier Mismatch Message</label>
                        <input type="text" id="cs_tier_mismatch" oninput="updateConfig()">
                        <div class="description">Variables: {u_tier}, {m_tier}</div>

                        <label class="input-label" style="margin-top:10px">User Tier Deny Model Message</label>
                        <input type="text" id="cs_user_deny_model" oninput="updateConfig()">
                        <div class="description">Variables: {u_tier}, {model_id}</div>

                        <label class="input-label" style="margin-top:10px">Model Whitelist Deny Message</label>
                        <input type="text" id="cs_model_wl_deny" oninput="updateConfig()">
                        <div class="description">Variables: {m_tier}</div>

                        <label class="input-label" style="margin-top:10px">Model Blacklist Deny Message</label>
                        <input type="text" id="cs_model_bl_deny" oninput="updateConfig()">
                        <div class="description">Variables: {m_tier}</div>

                        <label class="input-label" style="margin-top:10px">Rate Limit Exceeded Message</label>
                        <input type="text" id="cs_rate_limit_deny" oninput="updateConfig()">
                        <div class="description">Variables: {reason}</div>
                    </div>
                </div>

                <!-- JSON Editor -->
                <div class="json-section">
                    <h3>JSON Configuration</h3>
                    <p data-i18n="json_desc">Copy this into Open WebUI > Functions > OpenAccess Guard > Valves.</p>

                    <!-- New Buttons -->
                    <div style="display:flex; gap:10px; margin-bottom:10px;">
                        <button class="btn-secondary" onclick="updateConfig()" data-i18n="btn_gen_json">Generate
                            JSON</button>
                        <button class="btn-secondary" onclick="manualReloadJSON()" data-i18n="btn_reload_ui">Reload UI
                            from JSON</button>
                    </div>

                    <textarea id="json-editor" oninput="loadFromJSON(this.value)"></textarea>
                    <button class="btn-copy" onclick="copyJSON()">
                        <span data-i18n="btn_copy">Copy to Clipboard</span>
                    </button>
                </div>
            </div>

            <!-- TUTORIAL PAGE -->
            <div id="tutorial" class="page">
                <h1 data-i18n="tut_title">Tutorial</h1>
                <div class="card open">
                    <div class="card-body" style="display:block; padding-top:20px">
                        <h2 style="margin-top:0" data-i18n="tut_what_title">What is OpenAccess Guard?</h2>
                        <p data-i18n="tut_what_desc">OpenAccess Guard provides granular access control, smart rate
                            limiting, security governance, and banning capabilities for Open WebUI.</p>

                        <h2 data-i18n="tut_how_title">How to use OpenAccess Guard</h2>
                        <p data-i18n="tut_how_step1">1. Configure settings using this interface.</p>
                        <p data-i18n="tut_how_step2">2. Scroll down and copy the JSON code.</p>
                        <p data-i18n="tut_how_step3">3. Go to Open WebUI Admin Panel > Functions.</p>
                        <p data-i18n="tut_how_step4">4. Find "OpenAccess Guard", click the Gear/Settings icon.</p>
                        <p data-i18n="tut_how_step5">5. Locate "Config Json", change dropdown to "Custom" (if
                            applicable) and paste.</p>
                    </div>
                </div>

                <!-- New Detailed Guide Section -->
                <div class="card open">
                    <div class="card-header" onclick="toggleCard(this)">
                        <h3 data-i18n="tut_guide_title">Detailed Feature Guide</h3>
                        <span class="icon chevron">▼</span>
                    </div>
                    <div class="card-body">
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_auth_title">Auth Email Settings</h3>
                            <p data-i18n="tut_auth_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_wl_title">Whitelist System</h3>
                            <p data-i18n="tut_wl_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_ex_title">Exemption System</h3>
                            <p data-i18n="tut_ex_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="sec_priority">Priority System</h3>
                            <p data-i18n="prio_user_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_user_title">User Tier System (0-5)</h3>
                            <p data-i18n="tut_user_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_model_title">Model Tier System (0-5)</h3>
                            <p data-i18n="tut_model_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_ban_title">Ban System</h3>
                            <p data-i18n="tut_ban_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_fallback_title">Fallback (Smart Downgrade)</h3>
                            <p data-i18n="tut_fallback_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_log_title">Logs</h3>
                            <p data-i18n="tut_log_desc"></p>
                        </div>
                        <div class="tutorial-block">
                            <h3 data-i18n="tut_ads_title">Ads</h3>
                            <p data-i18n="tut_ads_desc"></p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- INFO PAGE -->
            <div id="info" class="page">
                <h1 data-i18n="info_title">About</h1>
                <div class="card open">
                    <div class="card-body" style="display:block; padding-top:20px">
                        <h3>OpenAccess Guard Pro</h3>
                        <p data-i18n="info_desc">Advanced governance for your LLM interface.</p>

                        <p><strong>GitHub:</strong> <a href="https://github.com/zealmult/OpenAccess-Guard"
                                target="_blank" style="color:var(--primary)">OpenAccess-Guard</a></p>
                        <p><strong>Author:</strong> Zealmult</p>

                        <!-- Localized Ad Banner -->
                        <div class="ad-banner">
                            <h3 style="margin-bottom:10px" data-i18n="ad_breath_title">🚀 Powered By BreathAI</h3>
                            <p style="color:rgba(255,255,255,0.9); margin-bottom:15px" data-i18n="ad_breath_desc">Get
                                free access to Claude 4.5, Gemini 3 Pro, GPT-5.1, DeepSeek, and Llama APIs.</p>
                            <a href="https://breathai.top/" target="_blank" data-i18n="ad_breath_link">Get Started at
                                breathai.top &rarr;</a>
                        </div>

                        <!-- Storage Management -->
                        <div style="margin-top: 30px; border-top: 1px solid var(--border); padding-top: 20px;">
                            <h3 data-i18n="storage_title">Storage Management</h3>
                            <p data-i18n="storage_desc">Clear local configuration cache if you encounter issues.</p>
                            <button class="btn-danger" onclick="resetConfig()" data-i18n="btn_reset">Reset
                                Config</button>
                        </div>
                    </div>
                </div>
            </div>


        </main>
    </div>

    <script>
        // --- Data & State ---
        const i18n = {
            en: {
                nav_settings: "Settings", nav_tutorial: "Tutorial", nav_about: "About",
                page_settings_title: "Configuration",
                settings_banner_hint: "Important: Please read the <b style='text-decoration:underline'>Tutorial</b> on the left sidebar before configuration!",

                sec_base: "Base Settings", base_enabled: "Enable OpenAccess Guard", base_enabled_desc: "Master Switch", base_admin: "Admin Effective", base_admin_desc: "Apply rules to admins",

                sec_auth: "Auth Email Settings", auth_enabled: "Approval Required", auth_enabled_desc: "Only allow specific email domains", auth_providers: "Allowed Providers", auth_msg: "Deny Message", auth_msg_desc: "Message shown to unverified users.",

                sec_lists: "Whitelist & Exemption", wl_enabled: "Enable Whitelist System", wl_enabled_desc: "Strict mode: Only listed users can access.", wl_users: "Whitelist Emails",
                ex_enabled: "Enable Exemption System", ex_enabled_desc: "These users bypass all limits and checks.", ex_users: "Exempt Emails",

                sec_priority: "Priority System", prio_user: "User Limit Priority",
                prio_user_desc: "If enabled, User Tier limits take precedence. If a user still has quota in their User Tier, they can continue using the AI even if the Model Tier limit is reached. Essentially, User Limits override Model Limits.",

                sec_user_tiers: "User Tier System (0-5)", sec_user_tiers_desc: "Categorize users to apply different limits. Default is Tier 0.",
                global_limit: "Global Limit", global_limit_desc: "Limits apply across all models cumulatively (e.g., 10 queries total regardless of model).",
                tier: "Tier",
                tier_enable: "Enable Tier",
                input_rpm: "Limit (RPM)", input_rph: "Limit (RPH)",
                input_win_time: "Win Time (min)", input_win_limit: "Win Limit (req)", input_clip: "Context Clip",
                deny_model_switch: "Deny Specific Models", deny_model_list: "Denied Models List", user_list: "Users in this Tier",

                sec_model_tiers: "Model Tier System (0-5)",
                match_tiers: "Match Model & User Tiers", match_tiers_desc: "Strict Mode: Tier 0 Users can ONLY use Tier 0 Models. Disabling this allows custom whitelist/blacklist logic per model tier.",
                model_list: "Models in this Tier",
                model_wl_mode: "User Access Mode", model_wl_mode_on: "Whitelist (Only allowed users)", model_wl_mode_off: "Blacklist (Block specific users)",
                access_list: "User Access List",

                sec_ban: "Ban System", sec_ban_reasons: "Ban Reasons configuration", ban_reason_label: "Ban Reason", ban_msg: "Ban Message", ban_users: "Banned Users",

                sec_fallback: "Fallback System", sec_fallback_config: "Smart Downgrade", fb_enabled: "Enable Fallback", fb_enabled_desc: "Downgrade user to a cheaper model if they hit limits.", fb_model: "Fallback Model ID", fb_notify: "Show Notification", fb_msg: "Notification Message",

                sec_misc: "Logs & Ads", sec_log_ads: "System Config", log_enabled: "Enable Logging", ads_enabled: "Enable Ads System", ads_enabled_desc: "Inject random ads into responses.", ad_placeholder: "Ad Content...",
                log_oag: "[OAG] Logic Logs", log_inlet: "Inlet Logs", log_outlet: "Outlet Logs", log_stream: "Stream Logs (Heavy)", log_dict: "User Dictionary Dump",

                sec_advanced: "Advanced Settings", sec_custom_strings: "Custom Strings", sec_custom_strings_desc: "Customize internal system messages. Support {placeholders}.",

                json_desc: "Copy the JSON below into Open WebUI settings.", btn_copy: "Copy JSON to Clipboard",
                btn_gen_json: "Generate JSON", btn_reload_ui: "Reload UI from JSON",

                tut_title: "Tutorial", tut_what_title: "What is OpenAccess Guard?", tut_what_desc: "OpenAccess Guard provides granular access control, smart rate limiting, security governance, and banning capabilities for Open WebUI.",
                tut_how_title: "How to use", tut_how_step1: "1. Configure settings here.", tut_how_step2: "2. Copy the JSON from the bottom.", tut_how_step3: "3. Go to Open WebUI Admin > Functions.", tut_how_step4: "4. Find OpenAccess Guard > Valves.", tut_how_step5: "5. Paste into 'Config Json'.",

                // Detailed Tutorial Guide
                tut_guide_title: "Detailed Feature Guide",
                tut_auth_title: "Auth Email Settings",
                tut_auth_desc: "Restricts access to specific email domains (e.g., @company.com). If enabled, only users with matching email suffixes can access AI features; others will be blocked with a custom message.",
                tut_wl_title: "Whitelist System",
                tut_wl_desc: "Enables a Strict Access Mode. When enabled, ONLY users explicitly listed in the Whitelist can use the AI. All other users are blocked regardless of other settings.",
                tut_ex_title: "Exemption System",
                tut_ex_desc: "Users in this list are Super VIPs. They bypass ALL OpenAccess Guard controls, including RPM/RPH limits, banned models, and ban lists. Use this for admins or trusted testers.",
                tut_user_title: "User Tier System (0-5)",
                tut_user_desc: "Users are categorized into Tiers 0-5. Tier 0 is the default for new users. You can set RPM (Requests Per Minute) and RPH (Requests Per Hour) for each tier. 'Global Limit' means limits count cumulatively across all models (e.g., 5 queries to GPT + 5 queries to Claude = 10 total).",
                tut_model_title: "Model Tier System (0-5)",
                tut_model_desc: "Models are also categorized. 'Match Tiers' enforces strict mapping: Tier 0 Users can ONLY use Tier 0 Models. If disabled, you can define specific Allow/Block lists for each model tier, giving you granular control over who accesses premium models.",
                tut_ban_title: "Ban System",
                tut_ban_desc: "Allows you to define up to 10 different ban reasons. You can add users to specific ban lists, and they will receive the corresponding custom message when attempting to chat.",
                tut_fallback_title: "Fallback (Smart Downgrade)",
                tut_fallback_desc: "Instead of blocking a user when they hit a rate limit, this system automatically switches them to a cheaper/free model (e.g., gpt-3.5-turbo) defined by you. You can optionally notify the user that they have been downgraded.",
                tut_log_title: "Logging System",
                tut_log_desc: "Controls what gets printed to the Open WebUI console. Useful for debugging and auditing user activity. 'Stream Logs' are very verbose and should only be used for debugging.",
                tut_ads_title: "Ads System",
                tut_ads_desc: "Injects advertisement messages into AI responses. You can define up to 10 ad messages, and the system will randomly select one to display via the event emitter during chat generation.",

                info_title: "About", info_desc: "The ultimate governance tool for Open WebUI.",
                ad_breath_title: "🚀 Powered By BreathAI",
                ad_breath_desc: "Get free access to Claude 4.5, Gemini 3 Pro, GPT-5.1, DeepSeek, and Llama APIs.",
                ad_breath_link: "Get Started at breathai.top &rarr;",
                storage_title: "Storage Management", storage_desc: "Clear local configuration cache if you encounter issues.", btn_reset: "Reset Config"
            },
            zh: {
                nav_settings: "配置", nav_tutorial: "教程", nav_about: "关于",
                page_settings_title: "配置编辑器",
                settings_banner_hint: "重要提示：配置前请务必阅读左侧侧边栏的 <b style='text-decoration:underline'>教程</b>！",

                sec_base: "基础设置", base_enabled: "启用 OpenAccess Guard", base_enabled_desc: "插件总开关", base_admin: "对管理员生效", base_admin_desc: "开启后，管理员也会受到规则限制",

                sec_auth: "认证邮箱设置", auth_enabled: "仅允许认证邮箱访问", auth_enabled_desc: "开启后，只有指定后缀的邮箱 (如 @company.com) 可使用 AI，否则抛出异常。", auth_providers: "允许的邮箱后缀", auth_msg: "拒绝访问提示语", auth_msg_desc: "不在白名单内的邮箱使用时显示的提示。",

                sec_lists: "白名单与豁免权", wl_enabled: "开启白名单系统", wl_enabled_desc: "严格模式：只有名单内的用户可以使用 AI，其他人全部拦截。", wl_users: "白名单用户邮箱",
                ex_enabled: "开启豁免权系统", ex_enabled_desc: "名单内的用户不受任何限制 (RPM/RPH/黑名单等)。请确保用户值得信任。", ex_users: "豁免权用户邮箱",

                sec_priority: "优先制度", prio_user: "以用户限制优先",
                prio_user_desc: "开启后，用户等级的限制优先级更高。假如该用户在当前模型等级（Model Tier）已达上限，但其用户等级（User Tier）仍有剩余额度，则允许继续使用。即：用户限制未到，模型限制到了也可以继续。",

                sec_user_tiers: "按用户限制系统 (Tier 0-5)", sec_user_tiers_desc: "将用户分为不同等级。默认新用户为 Tier 0 (最低权限)。",
                global_limit: "开启全局限制", global_limit_desc: "开启后，限制是对所有模型累计的。例如：限制10次，用户问了5次GPT-4，就只能再问5次Claude。",
                tier: "等级",
                tier_enable: "启用该等级限制",
                input_rpm: "每分钟限制", input_rph: "每小时限制",
                input_win_time: "动态窗口时间(分)", input_win_limit: "动态窗口限制数", input_clip: "上下文裁剪数",
                deny_model_switch: "拒绝使用特定模型", deny_model_list: "拒绝使用的模型 ID", user_list: "属于该等级的用户邮箱",

                sec_model_tiers: "按模型限制系统 (Tier 0-5)",
                match_tiers: "模型等级与用户等级对应", match_tiers_desc: "开启后：Tier 0 用户只能用 Tier 0 模型。关闭后：可自定义某类模型允许哪些用户访问。",
                model_list: "属于该等级的模型 ID",
                model_wl_mode: "用户访问模式", model_wl_mode_on: "白名单模式 (仅允许列表用户)", model_wl_mode_off: "黑名单模式 (拒绝列表用户)",
                access_list: "用户名单 (白/黑)",

                sec_ban: "封禁系统", sec_ban_reasons: "封禁理由与名单", ban_reason_label: "封禁理由", ban_msg: "提示消息", ban_users: "被封禁用户",

                sec_fallback: "降智系统", sec_fallback_config: "智能降级配置", fb_enabled: "启用降智系统", fb_enabled_desc: "当用户触发频率限制时，自动切换到更便宜的模型，而不是直接拒绝。", fb_model: "降智目标模型 ID", fb_notify: "显示提示", fb_msg: "提示内容",

                sec_misc: "日志与广告", sec_log_ads: "系统配置", log_enabled: "启用日志系统", ads_enabled: "启用广告系统", ads_enabled_desc: "在回复中随机插入广告 (概率触发)。", ad_placeholder: "广告内容...",
                log_oag: "记录 OAG 逻辑日志", log_inlet: "记录 Inlet 日志", log_outlet: "记录 Outlet 日志", log_stream: "记录 Stream 日志 (警告:数据量大)", log_dict: "记录用户字典 Dump",

                sec_advanced: "高级设置", sec_custom_strings: "自定义提示语", sec_custom_strings_desc: "自定义系统内部抛出的异常信息。支持使用 {变量} 占位符。",

                json_desc: "配置完成后，复制下方 JSON。", btn_copy: "复制 JSON 到剪贴板",
                btn_gen_json: "生成 JSON 代码", btn_reload_ui: "从 JSON 重载 UI",

                tut_title: "教程", tut_what_title: "什么是 OpenAccess Guard?", tut_what_desc: "OpenAccess Guard 为 Open WebUI 提供精细的访问控制、智能速率限制、安全治理及封号功能。",
                tut_how_title: "如何使用", tut_how_step1: "1. 在此页面配置所有选项。", tut_how_step2: "2. 复制页面底部的 JSON 代码。", tut_how_step3: "3. 进入 Open WebUI 管理员面板 > 函数 (Functions)。", tut_how_step4: "4. 找到 OpenAccess Guard 点击齿轮图标。", tut_how_step5: "5. 在 'Config Json' 处粘贴代码并保存。",

                // Detailed Tutorial Guide
                tut_guide_title: "功能详解",
                tut_auth_title: "认证邮箱设置",
                tut_auth_desc: "仅允许认证邮箱访问。开启后，只有被认证的邮箱提供商 (如 outlook.com, gmail.com) 才可以使用 AI，否则会抛出异常。您可以在此设置允许的邮箱后缀列表。",
                tut_wl_title: "白名单设置",
                tut_wl_desc: "开启白名单系统后，只有在白名单内的用户才可以使用您的 AI。OpenAccess Guard 将会阻挡任何白名单外用户对所有模型的访问权限。这是一个严格的访问控制模式。",
                tut_ex_title: "豁免权设置",
                tut_ex_desc: "开启豁免权系统后，在豁免权名单内的用户不受 OpenAccess Guard 的任何管控（包括 RPM/RPH 限制、封禁名单等）。请确保这些用户是完全可以信任的超级管理员或测试人员。",
                tut_user_title: "按用户限制系统",
                tut_user_desc: "OpenAccess Guard 会把用户分为 Tier 0 / 1 / 2 / 3 / 4 / 5，您可以用来区分不同的权限。这可以用来制定用户收费策略，例如 免费版/试用版/个人版/高级版/专业版。默认所有新注册用户是 Tier 0 用户。开启全局限制后，限制是对所有模型累计的（例如：限制10次，用户问了5次GPT-4，就只能再问5次Claude）。",
                tut_model_title: "按模型限制系统",
                tut_model_desc: "OpenAccess Guard 会把模型分为 Tier 0-5。开启'模型 Tier 与用户 Tier 对应'后，Tier 0 用户将只能使用 Tier 0 模型。关闭后可以自定义不同的模型访问权限（例如：即使是 Tier 0 用户，也可以通过白名单访问 Tier 3 的模型）。",
                tut_ban_title: "封禁系统",
                tut_ban_desc: "您可以自定义最多 10 种不同的封禁理由。将用户邮箱添加到对应的封禁理由下，该用户在使用 AI 时会直接抛出异常，并显示您设置的封禁提示语。",
                tut_fallback_title: "降智系统 (Smart Downgrade)",
                tut_fallback_desc: "开启后，用户如果触发了频率限制（RPM/RPH），将会自动切换到其他模型（例如从 GPT-4 降级到 gpt-3.5-turbo），而不是直接拒绝服务。您可以选择是否向用户展示降级提示。",
                tut_log_title: "日志系统",
                tut_log_desc: "开启后，日志将会打印在 Open WebUI 的控制台日志里面。您可以选择记录 Inlet/Outlet/Stream 日志来用于审计或调试。注意：开启 Stream 日志会导致日志量非常大。",
                tut_ads_title: "广告系统",
                tut_ads_desc: "开启后，将会使用 Open WebUI 的 event emitter 在用户向 AI 提问的时候展示广告。将会随机展示您配置的 1-10 条广告内容中的一条。",

                info_title: "关于", info_desc: "Open WebUI 的高级治理工具。",
                ad_breath_title: "🚀 由 BreathAI 驱动",
                ad_breath_desc: "免费使用 Claude 4.5, Gemini 3 Pro, GPT-5.1, DeepSeek 和 Llama API。",
                ad_breath_link: "前往 breathai.top 开始使用 &rarr;",
                storage_title: "存储管理", storage_desc: "如果遇到配置错误或缓存问题，可清除本地配置。", btn_reset: "重置所有配置"
            }
        };

        let curLang = 'zh';
        let config = {
            base: { enabled: true, admin_effective: false },
            auth: { enabled: false, providers: ["gmail.com", "outlook.com"], deny_msg: "Access Denied: Email domain not allowed." },
            whitelist: { enabled: false, emails: [] },
            exemption: { enabled: false, emails: [] },
            priority: { user_priority: false },
            global_limit: { enabled: false },
            user_tiers: [], // Generated in init
            model_tiers_config: { match_tiers: true },
            model_tiers: [], // Generated in init
            ban_system: {}, // Generated in init
            fallback: { enabled: false, model: "", notify: true, notify_msg: "Rate limit reached. Switched to basic model." },
            logging: { enabled: false, oag_log: true, inlet: false, outlet: false, stream: false, user_dict: false },
            ads: { enabled: false, content: Array(10).fill("") },
            // New Custom Strings
            custom_strings: {
                whitelist_deny: "Access Denied: Not in whitelist.",
                tier_mismatch: "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
                user_deny_model: "Tier {u_tier} users cannot use model {model_id}",
                model_wl_deny: "Access Denied to Tier {m_tier} Model (Whitelist)",
                model_bl_deny: "Access Denied to Tier {m_tier} Model (Blacklist)",
                rate_limit_deny: "Rate Limit Exceeded: {reason}"
            }
        };

        // --- Core Logic ---

        function init() {
            // Init Arrays
            for (let i = 0; i <= 5; i++) {
                config.user_tiers.push({ enabled: i === 0, rpm: 0, rph: 0, win_time: 0, win_limit: 0, clip: 0, deny_model_enabled: false, deny_models: [], emails: [] });
                config.model_tiers.push({ rpm: 0, rph: 0, win_time: 0, win_limit: 0, clip: 0, models: [], mode_whitelist: true, access_list: [] });
            }
            for (let i = 1; i <= 10; i++) {
                config.ban_system[`reason_${i}`] = { emails: [], msg: `Banned: Reason ${i}` };
            }

            // Load Storage
            const saved = localStorage.getItem('oag_config_v4');
            if (saved) {
                try {
                    const parsed = JSON.parse(saved);
                    // Simple merge for top keys to avoid errors if structure changes
                    config = { ...config, ...parsed };
                    // Ensure new keys exist if loading old config
                    if (!config.priority) config.priority = { user_priority: false };
                    if (!config.custom_strings) {
                        config.custom_strings = {
                            whitelist_deny: "Access Denied: Not in whitelist.",
                            tier_mismatch: "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
                            user_deny_model: "Tier {u_tier} users cannot use model {model_id}",
                            model_wl_deny: "Access Denied to Tier {m_tier} Model (Whitelist)",
                            model_bl_deny: "Access Denied to Tier {m_tier} Model (Blacklist)",
                            rate_limit_deny: "Rate Limit Exceeded: {reason}"
                        };
                    }
                } catch (e) { console.error("Load error", e); }
            }

            renderDynamicSections();
            syncUI();
            setLang(curLang);
        }

        function renderDynamicSections() {
            // 1. User Tiers
            const utContainer = document.getElementById('user_tiers_container');
            utContainer.innerHTML = '';
            config.user_tiers.forEach((tier, i) => {
                utContainer.innerHTML += `
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <h3>Tier ${i} <span style="font-weight:normal; font-size:0.8rem; opacity:0.7">(${i === 0 ? 'Default' : 'VIP'})</span></h3>
                    <span class="icon chevron">▼</span>
                </div>
                <div class="card-body">
                    <div class="control-group">
                        <div class="toggle-row">
                            <div class="label-text" data-i18n="tier_enable">Enable Tier</div>
                            <label class="switch"><input type="checkbox" id="ut_${i}_enabled" onchange="updateConfig()"><span class="slider"></span></label>
                        </div>
                    </div>
                    <div class="input-row">
                        <div class="input-col"><label class="input-label" data-i18n="input_rpm">RPM</label><input type="number" id="ut_${i}_rpm" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_rph">RPH</label><input type="number" id="ut_${i}_rph" onchange="updateConfig()"></div>
                    </div>
                    <div class="input-row">
                        <div class="input-col"><label class="input-label" data-i18n="input_win_time">Win Time</label><input type="number" id="ut_${i}_win_time" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_win_limit">Win Limit</label><input type="number" id="ut_${i}_win_limit" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_clip">Clip</label><input type="number" id="ut_${i}_clip" onchange="updateConfig()"></div>
                    </div>
                    
                    <div style="margin-top:20px; border-top:1px solid var(--border); padding-top:15px;">
                        <div class="toggle-row">
                            <div class="label-text" data-i18n="deny_model_switch">Deny Models</div>
                            <label class="switch"><input type="checkbox" id="ut_${i}_deny_enabled" onchange="updateConfig()"><span class="slider"></span></label>
                        </div>
                        <div id="ut_${i}_deny_area" class="sub-section hidden">
                             <label class="input-label" data-i18n="deny_model_list">Model IDs</label>
                             <div id="ut_${i}_deny_tags" class="tag-container"></div>
                             <div class="tag-input-wrapper">
                                <input type="text" id="ut_${i}_deny_input" placeholder="model_id" onkeydown="handleTagInput(event, 'user_tiers.${i}.deny_models', 'ut_${i}_deny_tags')">
                                <button class="btn-add" onclick="addTagFromInput('ut_${i}_deny_input', 'user_tiers.${i}.deny_models', 'ut_${i}_deny_tags')">+</button>
                             </div>
                        </div>
                    </div>

                    <div style="margin-top:15px;">
                        <label class="input-label" data-i18n="user_list">Users</label>
                        <div id="ut_${i}_users_tags" class="tag-container"></div>
                        <div class="tag-input-wrapper">
                            <input type="text" id="ut_${i}_users_input" placeholder="user@email.com" onkeydown="handleTagInput(event, 'user_tiers.${i}.emails', 'ut_${i}_users_tags')">
                            <button class="btn-add" onclick="addTagFromInput('ut_${i}_users_input', 'user_tiers.${i}.emails', 'ut_${i}_users_tags')">+</button>
                        </div>
                    </div>
                </div>
            </div>`;
            });

            // 2. Model Tiers
            const mtContainer = document.getElementById('model_tiers_container');
            mtContainer.innerHTML = '';
            config.model_tiers.forEach((tier, i) => {
                mtContainer.innerHTML += `
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <h3>Tier ${i} <span style="font-weight:normal; font-size:0.8rem; opacity:0.7">Model</span></h3>
                    <span class="icon chevron">▼</span>
                </div>
                <div class="card-body">
                    <div class="input-row">
                        <div class="input-col"><label class="input-label" data-i18n="input_rpm">RPM</label><input type="number" id="mt_${i}_rpm" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_rph">RPH</label><input type="number" id="mt_${i}_rph" onchange="updateConfig()"></div>
                    </div>
                    <div class="input-row">
                        <div class="input-col"><label class="input-label" data-i18n="input_win_time">Win Time</label><input type="number" id="mt_${i}_win_time" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_win_limit">Win Limit</label><input type="number" id="mt_${i}_win_limit" onchange="updateConfig()"></div>
                        <div class="input-col"><label class="input-label" data-i18n="input_clip">Clip</label><input type="number" id="mt_${i}_clip" onchange="updateConfig()"></div>
                    </div>
                    
                    <div style="margin-top:20px;">
                         <label class="input-label" data-i18n="model_list">Models</label>
                         <div id="mt_${i}_models_tags" class="tag-container"></div>
                         <div class="tag-input-wrapper">
                            <input type="text" id="mt_${i}_models_input" placeholder="model_id" onkeydown="handleTagInput(event, 'model_tiers.${i}.models', 'mt_${i}_models_tags')">
                            <button class="btn-add" onclick="addTagFromInput('mt_${i}_models_input', 'model_tiers.${i}.models', 'mt_${i}_models_tags')">+</button>
                         </div>
                    </div>

                    <!-- Dependent on Match Tiers -->
                    <div id="mt_${i}_access_area" style="margin-top:20px; border-top:1px solid var(--border); padding-top:15px;" class="hidden">
                        <div class="toggle-row">
                            <div class="label-text" data-i18n="model_wl_mode">Mode</div>
                            <div style="font-size:0.8rem; font-weight:bold" id="mt_${i}_mode_txt">Whitelist</div>
                            <label class="switch"><input type="checkbox" id="mt_${i}_wl_mode" onchange="updateConfig()"><span class="slider"></span></label>
                        </div>
                        <label class="input-label" data-i18n="access_list">Access List</label>
                        <div id="mt_${i}_access_tags" class="tag-container"></div>
                        <div class="tag-input-wrapper">
                            <input type="text" id="mt_${i}_access_input" placeholder="user@email.com" onkeydown="handleTagInput(event, 'model_tiers.${i}.access_list', 'mt_${i}_access_tags')">
                            <button class="btn-add" onclick="addTagFromInput('mt_${i}_access_input', 'model_tiers.${i}.access_list', 'mt_${i}_access_tags')">+</button>
                        </div>
                    </div>
                </div>
            </div>`;
            });

            // 3. Bans
            const banContainer = document.getElementById('ban_container');
            banContainer.innerHTML = '';
            for (let i = 1; i <= 10; i++) {
                banContainer.innerHTML += `
            <div style="border-bottom:1px solid var(--border); padding-bottom:15px; margin-bottom:15px">
                 <div style="font-weight:600; margin-bottom:10px; cursor:pointer; display:flex; justify-content:space-between" onclick="this.nextElementSibling.classList.toggle('hidden')">
                    <span>Reason #${i}</span> <span style="opacity:0.5">▼</span>
                 </div>
                 <div class="hidden">
                     <label class="input-label" data-i18n="ban_users">Banned Users</label>
                     <div id="ban_${i}_tags" class="tag-container"></div>
                     <div class="tag-input-wrapper">
                        <input type="text" id="ban_${i}_input" placeholder="user@email.com" onkeydown="handleTagInput(event, 'ban_system.reason_${i}.emails', 'ban_${i}_tags')">
                        <button class="btn-add" onclick="addTagFromInput('ban_${i}_input', 'ban_system.reason_${i}.emails', 'ban_${i}_tags')">+</button>
                     </div>
                     <label class="input-label" style="margin-top:10px" data-i18n="ban_msg">Ban Message</label>
                     <input type="text" id="ban_${i}_msg" oninput="updateConfig()">
                 </div>
            </div>`;
            }

            // 4. Ads
            const adsContainer = document.getElementById('ads_container');
            adsContainer.innerHTML = '';
            for (let i = 0; i < 10; i++) {
                adsContainer.innerHTML += `<div style="margin-bottom:10px"><label class="input-label">Ad Slot #${i + 1}</label><input type="text" id="ad_${i}" oninput="updateConfig()" data-i18n-placeholder="ad_placeholder"></div>`;
            }
        }

        function syncUI(fromJsonEditor = false) {
            // Base
            document.getElementById('base_enabled').checked = config.base.enabled;
            document.getElementById('base_admin').checked = config.base.admin_effective;

            // Auth
            document.getElementById('auth_enabled').checked = config.auth.enabled;
            document.getElementById('auth_logic_area').classList.toggle('hidden', !config.auth.enabled);
            document.getElementById('auth_msg').value = config.auth.deny_msg;
            renderTags(config.auth.providers, 'auth_providers_tags', 'auth.providers');

            // Lists
            document.getElementById('wl_enabled').checked = config.whitelist.enabled;
            document.getElementById('wl_area').classList.toggle('hidden', !config.whitelist.enabled);
            renderTags(config.whitelist.emails, 'wl_tags', 'whitelist.emails');

            document.getElementById('ex_enabled').checked = config.exemption.enabled;
            document.getElementById('ex_area').classList.toggle('hidden', !config.exemption.enabled);
            renderTags(config.exemption.emails, 'ex_tags', 'exemption.emails');

            // Priority
            document.getElementById('prio_user').checked = config.priority ? config.priority.user_priority : false;

            // User Tiers
            document.getElementById('global_limit').checked = config.global_limit.enabled;
            config.user_tiers.forEach((t, i) => {
                document.getElementById(`ut_${i}_enabled`).checked = t.enabled;
                document.getElementById(`ut_${i}_rpm`).value = t.rpm;
                document.getElementById(`ut_${i}_rph`).value = t.rph;
                document.getElementById(`ut_${i}_win_time`).value = t.win_time;
                document.getElementById(`ut_${i}_win_limit`).value = t.win_limit;
                document.getElementById(`ut_${i}_clip`).value = t.clip;
                document.getElementById(`ut_${i}_deny_enabled`).checked = t.deny_model_enabled;
                document.getElementById(`ut_${i}_deny_area`).classList.toggle('hidden', !t.deny_model_enabled);
                renderTags(t.deny_models, `ut_${i}_deny_tags`, `user_tiers.${i}.deny_models`);
                renderTags(t.emails, `ut_${i}_users_tags`, `user_tiers.${i}.emails`);
            });

            // Model Tiers
            const matchTiers = config.model_tiers_config.match_tiers;
            document.getElementById('match_tiers').checked = matchTiers;
            config.model_tiers.forEach((t, i) => {
                document.getElementById(`mt_${i}_rpm`).value = t.rpm;
                document.getElementById(`mt_${i}_rph`).value = t.rph;
                document.getElementById(`mt_${i}_win_time`).value = t.win_time;
                document.getElementById(`mt_${i}_win_limit`).value = t.win_limit;
                document.getElementById(`mt_${i}_clip`).value = t.clip;
                renderTags(t.models, `mt_${i}_models_tags`, `model_tiers.${i}.models`);

                // Access control logic visibility
                const acDiv = document.getElementById(`mt_${i}_access_area`);
                acDiv.classList.toggle('hidden', matchTiers);

                document.getElementById(`mt_${i}_wl_mode`).checked = t.mode_whitelist;
                document.getElementById(`mt_${i}_mode_txt`).innerText = t.mode_whitelist ? (curLang === 'zh' ? '白名单' : 'Whitelist') : (curLang === 'zh' ? '黑名单' : 'Blacklist');
                renderTags(t.access_list, `mt_${i}_access_tags`, `model_tiers.${i}.access_list`);
            });

            // Bans
            for (let i = 1; i <= 10; i++) {
                renderTags(config.ban_system[`reason_${i}`].emails, `ban_${i}_tags`, `ban_system.reason_${i}.emails`);
                document.getElementById(`ban_${i}_msg`).value = config.ban_system[`reason_${i}`].msg;
            }

            // Fallback
            document.getElementById('fb_enabled').checked = config.fallback.enabled;
            document.getElementById('fb_area').classList.toggle('hidden', !config.fallback.enabled);
            document.getElementById('fb_model').value = config.fallback.model;
            document.getElementById('fb_notify').checked = config.fallback.notify;
            document.getElementById('fb_msg').value = config.fallback.notify_msg;

            // Logs & Ads
            document.getElementById('log_enabled').checked = config.logging.enabled;
            document.getElementById('log_area').classList.toggle('hidden', !config.logging.enabled);
            document.getElementById('log_oag').checked = config.logging.oag_log;
            document.getElementById('log_inlet').checked = config.logging.inlet;
            document.getElementById('log_outlet').checked = config.logging.outlet;
            document.getElementById('log_stream').checked = config.logging.stream;
            document.getElementById('log_dict').checked = config.logging.user_dict;

            document.getElementById('ads_enabled').checked = config.ads.enabled;
            document.getElementById('ads_container').classList.toggle('hidden', !config.ads.enabled);
            config.ads.content.forEach((ad, i) => {
                document.getElementById(`ad_${i}`).value = ad;
            });

            // Custom Strings (New)
            if (config.custom_strings) {
                document.getElementById('cs_whitelist_deny').value = config.custom_strings.whitelist_deny;
                document.getElementById('cs_tier_mismatch').value = config.custom_strings.tier_mismatch;
                document.getElementById('cs_user_deny_model').value = config.custom_strings.user_deny_model;
                document.getElementById('cs_model_wl_deny').value = config.custom_strings.model_wl_deny;
                document.getElementById('cs_model_bl_deny').value = config.custom_strings.model_bl_deny;
                document.getElementById('cs_rate_limit_deny').value = config.custom_strings.rate_limit_deny;
            }

            // JSON Update: Only update text if change came from UI controls, NOT from JSON editor itself
            if (!fromJsonEditor) {
                document.getElementById('json-editor').value = JSON.stringify(config, null, 2);
            }
        }

        function updateConfig() {
            // Collect Data
            config.base.enabled = document.getElementById('base_enabled').checked;
            config.base.admin_effective = document.getElementById('base_admin').checked;

            config.auth.enabled = document.getElementById('auth_enabled').checked;
            config.auth.deny_msg = document.getElementById('auth_msg').value;

            config.whitelist.enabled = document.getElementById('wl_enabled').checked;
            config.exemption.enabled = document.getElementById('ex_enabled').checked;

            // Priority
            if (!config.priority) config.priority = {};
            config.priority.user_priority = document.getElementById('prio_user').checked;

            config.global_limit.enabled = document.getElementById('global_limit').checked;

            config.user_tiers.forEach((t, i) => {
                t.enabled = document.getElementById(`ut_${i}_enabled`).checked;
                t.rpm = Number(document.getElementById(`ut_${i}_rpm`).value);
                t.rph = Number(document.getElementById(`ut_${i}_rph`).value);
                t.win_time = Number(document.getElementById(`ut_${i}_win_time`).value);
                t.win_limit = Number(document.getElementById(`ut_${i}_win_limit`).value);
                t.clip = Number(document.getElementById(`ut_${i}_clip`).value);
                t.deny_model_enabled = document.getElementById(`ut_${i}_deny_enabled`).checked;
            });

            config.model_tiers_config.match_tiers = document.getElementById('match_tiers').checked;
            config.model_tiers.forEach((t, i) => {
                t.rpm = Number(document.getElementById(`mt_${i}_rpm`).value);
                t.rph = Number(document.getElementById(`mt_${i}_rph`).value);
                t.win_time = Number(document.getElementById(`mt_${i}_win_time`).value);
                t.win_limit = Number(document.getElementById(`mt_${i}_win_limit`).value);
                t.clip = Number(document.getElementById(`mt_${i}_clip`).value);
                t.mode_whitelist = document.getElementById(`mt_${i}_wl_mode`).checked;
            });

            for (let i = 1; i <= 10; i++) {
                config.ban_system[`reason_${i}`].msg = document.getElementById(`ban_${i}_msg`).value;
            }

            config.fallback.enabled = document.getElementById('fb_enabled').checked;
            config.fallback.model = document.getElementById('fb_model').value;
            config.fallback.notify = document.getElementById('fb_notify').checked;
            config.fallback.notify_msg = document.getElementById('fb_msg').value;

            config.logging.enabled = document.getElementById('log_enabled').checked;
            config.logging.oag_log = document.getElementById('log_oag').checked;
            config.logging.inlet = document.getElementById('log_inlet').checked;
            config.logging.outlet = document.getElementById('log_outlet').checked;
            config.logging.stream = document.getElementById('log_stream').checked;
            config.logging.user_dict = document.getElementById('log_dict').checked;

            config.ads.enabled = document.getElementById('ads_enabled').checked;
            for (let i = 0; i < 10; i++) {
                config.ads.content[i] = document.getElementById(`ad_${i}`).value;
            }

            // Update Custom Strings
            if (!config.custom_strings) config.custom_strings = {};
            config.custom_strings.whitelist_deny = document.getElementById('cs_whitelist_deny').value;
            config.custom_strings.tier_mismatch = document.getElementById('cs_tier_mismatch').value;
            config.custom_strings.user_deny_model = document.getElementById('cs_user_deny_model').value;
            config.custom_strings.model_wl_deny = document.getElementById('cs_model_wl_deny').value;
            config.custom_strings.model_bl_deny = document.getElementById('cs_model_bl_deny').value;
            config.custom_strings.rate_limit_deny = document.getElementById('cs_rate_limit_deny').value;

            localStorage.setItem('oag_config_v4', JSON.stringify(config));
            syncUI(false); // Update JSON editor too
        }

        // --- Helpers ---
        function resolvePath(obj, path) {
            return path.split('.').reduce((o, p) => o ? o[p] : null, obj);
        }

        function renderTags(arr, containerId, path) {
            const el = document.getElementById(containerId);
            el.innerHTML = '';
            arr.forEach((item, idx) => {
                const tag = document.createElement('div');
                tag.className = 'tag';
                tag.innerHTML = `${item} <span onclick="removeTag('${path}', ${idx})">×</span>`;
                el.appendChild(tag);
            });
        }

        function addTagFromInput(inputId, path, containerId) {
            const input = document.getElementById(inputId);
            const val = input.value.trim();
            if (val) {
                const arr = resolvePath(config, path);
                if (arr && !arr.includes(val)) {
                    arr.push(val);
                    updateConfig();
                }
            }
            input.value = '';
        }

        function handleTagInput(e, path, containerId) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addTagFromInput(e.target.id, path, containerId);
            }
        }

        function removeTag(path, idx) {
            const arr = resolvePath(config, path);
            if (arr) {
                arr.splice(idx, 1);
                updateConfig();
            }
        }

        function toggleCard(header) {
            header.parentElement.classList.toggle('open');
        }

        function router(pageId) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.getElementById(pageId).classList.add('active');

            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            // Find the nav item that calls this router logic (simplified)
            event.currentTarget.classList.add('active');
        }

        function setLang(lang) {
            curLang = lang;
            document.getElementById('btn-en').classList.toggle('active', lang === 'en');
            document.getElementById('btn-zh').classList.toggle('active', lang === 'zh');

            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (i18n[lang][key]) {
                    // If it contains HTML tags (like <b>), use innerHTML, otherwise innerText
                    if (i18n[lang][key].includes('<')) {
                        el.innerHTML = i18n[lang][key];
                    } else {
                        el.innerText = i18n[lang][key];
                    }
                }
            });

            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const key = el.getAttribute('data-i18n-placeholder');
                if (i18n[lang][key]) el.placeholder = i18n[lang][key];
            });

            // Refresh dynamic UI text (like Whitelist/Blacklist labels in loop)
            syncUI();
        }

        function resetConfig() {
            const msg = curLang === 'zh'
                ? '确定要清除所有本地配置并重置吗？这将丢失所有未保存的更改。'
                : 'Are you sure you want to clear all local settings and reset? Unsaved changes will be lost.';

            if (confirm(msg)) {
                localStorage.removeItem('oag_config_v4');
                location.reload();
            }
        }

        function loadFromJSON(val) {
            try {
                const parsed = JSON.parse(val);
                config = parsed; // Directly update config from JSON
                localStorage.setItem('oag_config_v4', JSON.stringify(config));

                // Sync UI but pass true to skip updating the JSON editor text
                // This prevents cursor jumping while typing
                syncUI(true);
            } catch (e) {
                // Syntax error expected while typing, ignore
            }
        }

        function copyJSON() {
            const el = document.getElementById('json-editor');
            el.select();
            document.execCommand('copy');
            // Simple visual feedback
            const btn = document.querySelector('.btn-copy');
            const orig = btn.innerText;
            btn.innerText = "Copied!";
            setTimeout(() => btn.innerText = orig, 1500);
        }

        function manualReloadJSON() {
            const val = document.getElementById('json-editor').value;
            loadFromJSON(val);
            const msg = curLang === 'zh' ? 'UI 已根据 JSON 更新' : 'UI updated from JSON';
            alert(msg);
        }

        function toggleSidebar() {
            const sb = document.getElementById('sidebar');
            sb.classList.toggle('collapsed');
        }

        function toggleMobileMenu() {
            document.getElementById('sidebar').classList.toggle('mobile-open');
        }

        // Expose functions to global scope for HTML inline events
        window.toggleSidebar = toggleSidebar;
        window.toggleMobileMenu = toggleMobileMenu;
        window.updateConfig = updateConfig;
        window.router = router;
        window.toggleCard = toggleCard;
        window.handleTagInput = handleTagInput;
        window.addTagFromInput = addTagFromInput;
        window.setLang = setLang;
        window.resetConfig = resetConfig;
        window.loadFromJSON = loadFromJSON;
        window.copyJSON = copyJSON;
        window.manualReloadJSON = manualReloadJSON;

        // Start
        window.onload = init;
    </script>
</body>

</html>
"""

# ============================================================
# 1. 配置服务器
# ============================================================


class WebAdminServer:
    started = False

    def __init__(self, port: int = 6767):
        if WebAdminServer.started:
            return
        self.port = port

        def run_server():
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != "/":
                        self.send_error(404)
                        return

                    final_html = HTML_UI.replace(
                        "__CONFIG_JSON_PLACEHOLDER__", json.dumps(DEFAULT_CONFIG)
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(final_html.encode("utf-8"))

                def log_message(self, format, *args):
                    pass  # Silence server logs

            try:
                HTTPServer.allow_reuse_address = True
                httpd = HTTPServer(("0.0.0.0", self.port), Handler)
                print(
                    f"[OpenAccess Guard] Config UI started at http://localhost:{self.port}"
                )
                WebAdminServer.started = True
                httpd.serve_forever()
            except Exception as e:
                print(f"[OpenAccess Guard] Server Start Failed: {e}")

        t = threading.Thread(target=run_server, daemon=True)
        t.start()


# ============================================================
# 2. Filter 主逻辑
# ============================================================


class Filter:
    class Valves(BaseModel):
        config_json: str = Field(
            default=json.dumps(DEFAULT_CONFIG, indent=2),
            description="请登录到 http://<your-ip>:6767 访问 OAG 网页控制台。Please log in to http://<your-ip>:6767 to access the OAG web console.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_history = {}  # {user_id: {model_id: [timestamps]}}
        self.parsed_config = None
        WebAdminServer(port=6767)

    def _get_cfg(self):
        # 简单缓存，避免每次 parse
        try:
            return json.loads(self.valves.config_json)
        except:
            return DEFAULT_CONFIG

    def _log(self, cfg, level, msg, data=None):
        if not cfg["logging"]["enabled"]:
            return
        prefix = "[OpenAccess Guard]"

        # OAG 系统日志
        if level == "OAG" and cfg["logging"]["oag_log"]:
            print(f"{prefix} {msg} | Data: {data}")
        # Inlet/Outlet/Stream
        elif level in ["INLET", "OUTLET", "STREAM"] and cfg["logging"][level.lower()]:
            # user dict check
            if data and "user" in data and not cfg["logging"]["user_dict"]:
                data["user"] = data["user"].get("email", "hidden")
            print(f"{prefix} [{level}] {msg} | {data}")

    def _get_tier(self, cfg, email, mode="user"):
        """Determine Tier (0-5) for user or model"""
        if mode == "user":
            # 修复：tiers 是列表，使用整数索引访问
            tiers = cfg["user_tiers"]
            for i in range(5, -1, -1):
                if i < len(tiers) and email in tiers[i]["emails"]:
                    return i
            return 0  # Default Tier 0
        else:
            # Model Tier logic
            model_id = email  # passed as model_id
            tiers = cfg["model_tiers"]
            for i in range(5, -1, -1):
                if i < len(tiers) and model_id in tiers[i]["models"]:
                    return i
            return 0

    def _check_specific_limit(self, source_name, limits, history):
        """Helper to check if a specific limit config is hit"""
        now = time.time()
        rpm = limits["rpm"]
        rph = limits["rph"]
        w_lim = limits["win_limit"]
        w_time = limits["win_time"]  # mins

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
        now = time.time()

        # 修复：直接使用整数索引访问配置列表
        ut_cfg = cfg["user_tiers"][user_tier_idx]
        mt_cfg = cfg["model_tiers"][model_tier_idx]

        # Cleanup history
        if user_id not in self.user_history:
            self.user_history[user_id] = {}

        # Global limit check?
        target_history_key = "GLOBAL" if cfg["global_limit"]["enabled"] else model_id

        if target_history_key not in self.user_history[user_id]:
            self.user_history[user_id][target_history_key] = []

        history = self.user_history[user_id][target_history_key]
        # Cleanup (keep max 1 day for safety)
        history = [t for t in history if now - t < 86400]
        self.user_history[user_id][target_history_key] = history

        # --- Priority Logic ---
        # 1. Check User Tier Status
        user_hit, user_reason = self._check_specific_limit("User Tier", ut_cfg, history)

        # 2. Check Model Tier Status
        model_hit, model_reason = self._check_specific_limit(
            "Model Tier", mt_cfg, history
        )

        # 3. Determine if Blocked based on Priority (Global OR Specific Tier)
        global_prio = cfg.get("priority", {}).get("user_priority", False)
        # 获取当前模型Tier的独立优先设置，默认为False
        tier_prio = mt_cfg.get("user_priority", False)

        # 如果全局开启 或者 该模型等级单独开启，则执行用户优先逻辑
        use_user_priority = global_prio or tier_prio

        if use_user_priority:
            # Rule: "If model limit reached but user limit not, continue"
            # Means we ONLY block if User Limit is hit.
            if user_hit:
                return True, user_reason
            else:
                # Even if model_hit is True, we allow it because User Limit is not hit
                # and priority is active.
                if model_hit:
                    # Optional: Log that we bypassed model limit?
                    pass
                return False, None
        else:
            # Default Rule: Block if ANY limit is hit
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
        cfg = self._get_cfg()

        # 安全获取自定义字符串，防止老配置缺少字段
        def get_msg(key, default):
            return cfg.get("custom_strings", {}).get(key, default)

        # 1. Base Checks
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

        # Admin Bypass
        if role == "admin" and not cfg["base"]["admin_effective"]:
            return body

        # Exemption
        if cfg["exemption"]["enabled"] and email in cfg["exemption"]["emails"]:
            self._log(cfg, "OAG", "Exempted User", email)
            return body

        # Auth Provider Check
        if cfg["auth"]["enabled"]:
            domain = email.split("@")[-1] if "@" in email else ""
            if domain not in cfg["auth"]["providers"]:
                raise Exception(cfg["auth"]["deny_msg"])

        # Whitelist Check
        if cfg["whitelist"]["enabled"] and email not in cfg["whitelist"]["emails"]:
            msg = get_msg("whitelist_deny", "Access Denied: Not in whitelist.")
            raise Exception(msg)

        # Ban System
        for i in range(1, 11):
            reason_key = f"reason_{i}"
            if email in cfg["ban_system"][reason_key]["emails"]:
                raise Exception(cfg["ban_system"][reason_key]["msg"])

        # Determine Tiers
        u_tier = self._get_tier(cfg, email, "user")
        m_tier = self._get_tier(cfg, model_id, "model")

        # 修复：直接使用整数索引访问
        ut_cfg = cfg["user_tiers"][u_tier]
        mt_cfg = cfg["model_tiers"][m_tier]

        # --- Access Control Logic ---

        # 1. User Tier - Deny Models
        if ut_cfg["deny_model_enabled"] and model_id in ut_cfg["deny_models"]:
            msg = get_msg(
                "user_deny_model", "Tier {u_tier} users cannot use model {model_id}"
            )
            raise Exception(msg.format(u_tier=u_tier, model_id=model_id))

        # 2. Model Tier - Match Tier Logic
        if cfg["model_tiers_config"]["match_tiers"]:
            if u_tier != m_tier:
                msg = get_msg(
                    "tier_mismatch",
                    "Tier Mismatch. User Tier {u_tier} cannot access Model Tier {m_tier}",
                )
                raise Exception(msg.format(u_tier=u_tier, m_tier=m_tier))
        else:
            # 3. Model Tier - Specific Access List (White/Black list)
            access_list = mt_cfg["access_list"]
            if mt_cfg["mode_whitelist"]:
                if email not in access_list:
                    msg = get_msg(
                        "model_wl_deny",
                        "Access Denied to Tier {m_tier} Model (Whitelist)",
                    )
                    raise Exception(msg.format(m_tier=m_tier))
            else:
                if email in access_list:
                    msg = get_msg(
                        "model_bl_deny",
                        "Access Denied to Tier {m_tier} Model (Blacklist)",
                    )
                    raise Exception(msg.format(m_tier=m_tier))

        # --- Rate Limiting ---
        is_limited, limit_reason = self._check_rate_limit(
            cfg, user_id, email, model_id, u_tier, m_tier
        )

        if is_limited:
            self._log(cfg, "OAG", "Rate Limit Hit", limit_reason)

            if cfg["fallback"]["enabled"]:
                # Fallback Logic
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
            # Log usage (Add timestamp)
            target = "GLOBAL" if cfg["global_limit"]["enabled"] else model_id
            self.user_history[user_id][target].append(time.time())

        # --- Context Clipping ---
        clip_count = max(ut_cfg["clip"], mt_cfg["clip"])  # Take max clip
        if clip_count > 0 and "messages" in body:
            msgs = body["messages"]
            sys_msg = next((m for m in msgs if m["role"] == "system"), None)
            chat_msgs = [m for m in msgs if m["role"] != "system"]

            # Keep last N
            chat_msgs = chat_msgs[-clip_count:]

            if sys_msg:
                chat_msgs.insert(0, sys_msg)

            body["messages"] = chat_msgs
            self._log(cfg, "OAG", f"Context Clipped to {clip_count}")

        # --- Ads System ---
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
        cfg = self._get_cfg()
        self._log(cfg, "OUTLET", "Response", {"user": __user__})
        return body

    async def stream(self, event: Any, __user__: Optional[dict] = None) -> Any:
        cfg = self._get_cfg()
        # 仅在开启 stream 日志且非常确定需要时记录，防止刷屏
        if cfg["logging"]["enabled"] and cfg["logging"]["stream"]:
            # 简单转换 bytes 为 str 以便查看，不报错
            log_data = event
            if isinstance(event, bytes):
                try:
                    log_data = event.decode("utf-8")
                except:
                    log_data = "<binary>"

            self._log(cfg, "STREAM", "Chunk", {"data": log_data, "user": __user__})
        return event
