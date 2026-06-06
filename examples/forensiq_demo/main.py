#!/usr/bin/env python3
"""
Sanctum Cognitive UI Demo - Textual TUI Version
A native terminal interface representing cognitive AI layers.

Copyright (C) 2025 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import re
import random
import textwrap
import time

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, RichLog, Input
from textual.screen import Screen
from textual.reactive import reactive
from textual.timer import Timer
from textual.message import Message
from textual import events
from rich.text import Text
from rich.console import Console
from rich.markup import escape

# Global flags for testing and debugging
TEST_MODE = False
AUTO_CLOSE = False
AUTO_CLOSE_SECONDS = 0.0
DEBUG_VISUAL = False
SCREENSHOT_MODE = False
SCENARIO = "forensiq"

# Memory pane: wrap inside bordered column (240 terminal / 3 columns minus border+padding).
MEMORY_WRAP_WIDTH = 68

class SSHLoginSimulator:
    """Handles the fake SSH login sequence with MOTD"""
    
    def __init__(self, app):
        self.app = app
        self.login_complete = False
        self.motd_lines = [
            "",
            "  ╔═══════════════════════════════════════════════════════════════════════╗",
            "  ║                                                                       ║",
            "  ║   ███████  █████  ███    ██  ██████ ████████ ██    ██ ███    ███     ║",
            "  ║   ██      ██   ██ ████   ██ ██         ██    ██    ██ ████  ████     ║",
            "  ║   ███████ ███████ ██ ██  ██ ██         ██    ██    ██ ██ ████ ██     ║",
            "  ║        ██ ██   ██ ██  ██ ██ ██         ██    ██    ██ ██  ██  ██     ║",
            "  ║   ███████ ██   ██ ██   ████  ██████    ██     ██████  ██      ██     ║",
            "  ║                                                                       ║",
            "  ║                     Security Suite v3.7.2                           ║",
            "  ║                                                                       ║",
            "  ║                 Cognitive Threat Analysis Platform                   ║",
            "  ║                                                                       ║",
            "  ╚═══════════════════════════════════════════════════════════════════════╝",
            "",
            "  [CLASSIFIED] Remote Access Terminal",
            "  Connected to: sanctum-core-01.secure.local (10.0.0.100)",
            "  Session ID: SSH-2024-12-19-001337",
            "",
            "  WARNING: This system is monitored. Unauthorized access is prohibited.",
            "           All activities are logged and subject to audit.",
            "",
            "  Active Cognitive Modules:",
            "  ├─ Thalamus Input Processor      [ONLINE]",
            "  ├─ Cerebellum Reflex Engine      [ONLINE]",
            "  ├─ Prime Analysis Core           [ONLINE]",
            "  └─ Memory Block Manager          [ONLINE]",
            "",
            "  System Status: All subsystems operational",
            "  Threat Level: GREEN",
            "  Last Maintenance: 2024-12-18 03:00 UTC",
            "",
            "  Type 'help' for available commands or 'monitor' to enter cognitive view.",
            "",
        ]
    
    def start_login_sequence(self):
        """Start the SSH login simulation"""
        self.app.push_screen(SSHLoginScreen(self))
    
    def complete_login(self):
        """Mark login as complete and proceed to main app"""
        self.login_complete = True
        self.app.pop_screen()
        
        # Update title and start the main demo
        self.app.title = "Sanctum Cognitive UI Demo"
        self.app.set_timer(1.0, self.app.event_engine.start_demo)

class SSHLoginScreen(Screen):
    """Screen for SSH login simulation"""
    
    def __init__(self, ssh_simulator):
        super().__init__()
        self.ssh_simulator = ssh_simulator
        self.current_line = 0
        self.login_timer = None
        self.typing_timer = None
        self.current_typing_line = ""
        self.typing_index = 0
        self._ssh_partial = ""
        
    def compose(self) -> ComposeResult:
        yield Container(
            RichLog(
                id="ssh-output",
                highlight=False,
                markup=False,
                wrap=True,
                auto_scroll=True,
            ),
            Input(placeholder="", id="ssh-input", disabled=True),
            id="ssh-container"
        )
    
    def on_mount(self):
        """Start the SSH login sequence when mounted"""
        self.styles.background = "black"
        self.query_one("#ssh-container").styles.height = "100%"
        self.query_one("#ssh-container").styles.width = "100%"
        ssh_output = self.query_one("#ssh-output", RichLog)
        ssh_output.styles.color = "green"
        ssh_output.styles.background = "black"
        self.query_one("#ssh-input").styles.background = "black"
        self.query_one("#ssh-input").styles.color = "green"
        
        # Start the login sequence
        self.start_connection_sequence()
    
    def start_connection_sequence(self):
        """Simulate SSH connection process"""
        output = self.query_one("#ssh-output")
        
        # Initial connection messages
        connection_msgs = [
            "Connecting to sanctum-core-01.secure.local...",
            "Connection established.",
            "Server fingerprint: SHA256:3f7a8b2c9d1e6f4a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a",
            "Warning: Permanently added 'sanctum-core-01.secure.local' (RSA) to the list of known hosts.",
            "",
        ]
        
        for i, msg in enumerate(connection_msgs):
            self.set_timer(max(0.1, i * 0.3), lambda m=msg: self.add_line(m))
        
        # Start username prompt after connection messages
        self.set_timer(len(connection_msgs) * 0.3 + 0.5, self.prompt_username)
    
    def prompt_username(self):
        """Prompt for username"""
        output = self.query_one("#ssh-output")
        ssh_input = self.query_one("#ssh-input")
        
        self.add_line("Username: ", newline=False)
        ssh_input.placeholder = ""
        ssh_input.disabled = False
        ssh_input.focus()
        
        # Auto-type username after a short delay
        self.set_timer(0.8, lambda: self.type_text("admin"))
    
    def type_text(self, text):
        """Simulate typing text"""
        ssh_input = self.query_one("#ssh-input")
        self.current_typing_line = text
        self.typing_index = 0
        
        if self.typing_timer:
            self.typing_timer.stop()
        
        self.typing_timer = self.set_interval(0.1, self.type_next_char)
    
    def type_next_char(self):
        """Type the next character"""
        ssh_input = self.query_one("#ssh-input")
        
        if self.typing_index < len(self.current_typing_line):
            char = self.current_typing_line[self.typing_index]
            current_value = ssh_input.value
            ssh_input.value = current_value + char
            self.typing_index += 1
        else:
            if self.typing_timer:
                self.typing_timer.stop()
            # Simulate pressing enter
            self.set_timer(0.5, self.handle_username_entered)
    
    def handle_username_entered(self):
        """Handle username being entered"""
        ssh_input = self.query_one("#ssh-input")
        username = ssh_input.value
        
        self.add_line(username)
        ssh_input.value = ""
        ssh_input.password = True
        ssh_input.placeholder = ""
        
        self.add_line("Password: ", newline=False)
        
        # Auto-type password (shown as asterisks)
        self.set_timer(0.8, lambda: self.type_password("********"))
    
    def type_password(self, password_display):
        """Simulate typing password"""
        ssh_input = self.query_one("#ssh-input")
        
        for i, char in enumerate(password_display):
            self.set_timer(max(0.1, i * 0.1), lambda c=char: self.add_password_char(c))
        
        # Submit password
        self.set_timer(len(password_display) * 0.1 + 0.5, self.handle_password_entered)
    
    def add_password_char(self, char):
        """Add a password character"""
        ssh_input = self.query_one("#ssh-input")
        ssh_input.value += char
    
    def handle_password_entered(self):
        """Handle password being entered"""
        ssh_input = self.query_one("#ssh-input")
        self.add_line("*" * len(ssh_input.value))
        
        ssh_input.disabled = True
        ssh_input.value = ""
        
        # Show authentication success and MOTD
        self.set_timer(0.5, self.show_auth_success)
    
    def show_auth_success(self):
        """Show authentication success and MOTD"""
        self.add_line("")
        self.add_line("Authentication successful.")
        self.add_line("")
        
        # Display MOTD line by line
        for i, line in enumerate(self.ssh_simulator.motd_lines):
            self.set_timer(max(0.1, i * 0.1), lambda l=line: self.add_line(l))
        
        # Finish login sequence
        total_delay = len(self.ssh_simulator.motd_lines) * 0.1 + 2.0
        self.set_timer(total_delay, self.finish_login)
    
    def finish_login(self):
        """Complete the login sequence"""
        self.add_line("Initializing cognitive interface...")
        self.add_line("")
        self.set_timer(1.5, self.ssh_simulator.complete_login)
    
    def add_line(self, text, newline=True):
        """Append a line to the SSH RichLog (Static collapsed MOTD to one row)."""
        output = self.query_one("#ssh-output", RichLog)
        if not newline:
            self._ssh_partial += text
            return
        output.write(self._ssh_partial + text)
        self._ssh_partial = ""

def _timeline_shared_prefix() -> List[Dict]:
    """Opening incidents and false-positive refusals (both scenarios)."""
    return [
        {"type": "console", "level": "INFO", "message": "System initialization complete", "process": "CORE"},
        {"type": "console", "level": "INFO", "message": "Loading cognitive modules...", "process": "INIT"},
        {"type": "console", "level": "INFO", "message": "Thalamus input stream: ACTIVE", "process": "THAL"},
        {"type": "console", "level": "WARN", "message": "Unusual file access pattern detected", "process": "MON", "highlight": True},
        {"type": "console", "level": "INFO", "message": "HR directory accessed outside business hours", "process": "FS", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Unusual file access pattern detected"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Flagging after-hours HR access - pattern analysis required"},
        {"type": "escalation", "message": "Potential data exfiltration attempt detected - requesting analysis"},
        {"type": "prime_response", "message": "Analyzing access patterns and user behavior history"},
        {"type": "prime_tool", "action": "flag_investigation", "message": "Flagging incident for security team investigation - user john.doe@company.com"},
        {"type": "prime_tool", "action": "create_memory_block", "message": "Analysis complete. This incident requires documentation."},
        {"type": "prime_tool", "action": "write_block", "message": "Creating incident report: SECURITY INCIDENT"},
        {"type": "memory", "data": {
            "title": "SECURITY INCIDENT",
            "content": "After-hours access to HR directory detected. User: john.doe@company.com. Files accessed: employee_records.xlsx, salary_data.csv. Time: 23:47 UTC. Flagged for investigation."
        }},
        {"type": "console", "level": "WARN", "message": "Network traffic spike detected", "process": "NET", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Network traffic spike detected - potential DDoS"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Analyzing traffic patterns... scheduled backup sync. Dismissing alert."},
        {"type": "console", "level": "WARN", "message": "Elevated file system activity", "process": "FS", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Elevated file system activity - potential data exfiltration"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Cross-referencing with maintenance window... automated log rotation. False positive."},
        {"type": "console", "level": "WARN", "message": "Unusual authentication pattern", "process": "AUTH", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Unusual authentication pattern detected"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Checking user context... legitimate mobile app sync. No threat detected."},
    ]


def _timeline_forensiq_late() -> List[Dict]:
    """Default security demo: brute force + active breach."""
    return [
        {"type": "console", "level": "WARN", "message": "Multiple failed login attempts", "process": "AUTH", "highlight": True},
        {"type": "console", "level": "ERROR", "message": "Brute force attack detected from IP 192.168.1.157", "process": "SEC", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Brute force attack detected from IP 192.168.1.157"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Blocking suspicious IP immediately - auto-defense engaged"},
        {"type": "escalation", "message": "Coordinated attack pattern identified - multiple vectors detected"},
        {"type": "prime_response", "message": "Cross-referencing with threat intelligence databases"},
        {"type": "inter_agent", "sender": "Prime", "message": "Request additional network logs from past hour"},
        {"type": "inter_agent", "sender": "Cerebellum", "message": "Retrieving network activity logs - 847 events found"},
        {"type": "prime_tool", "action": "block_ip", "message": "Blocking source IP 192.168.1.157 across all network segments"},
        {"type": "prime_tool", "action": "create_memory_block", "message": "Threat analysis complete. Documenting attack pattern."},
        {"type": "prime_tool", "action": "write_block", "message": "Creating incident report: BRUTE FORCE ATTEMPT"},
        {"type": "memory", "data": {
            "title": "BRUTE FORCE ATTEMPT",
            "content": "Coordinated brute force attack detected. Source IP: 192.168.1.157. Target accounts: admin, root, service. Attack duration: 4 minutes. Status: BLOCKED."
        }},
        {"type": "console", "level": "WARN", "message": "Administrative command executed", "process": "PRIV", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Administrative command executed outside normal hours"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Verifying user credentials... authorized system administrator. Legitimate action."},
        {"type": "console", "level": "WARN", "message": "Large data transfer initiated", "process": "NET", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Large data transfer initiated - potential exfiltration"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Checking destination... approved cloud backup provider. Normal operations."},
        {"type": "console", "level": "CRITICAL", "message": "Privilege escalation attempt detected", "process": "PRIV", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Privilege escalation attempt detected"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "URGENT: Root access attempt via exploit - immediate containment"},
        {"type": "escalation", "message": "Critical security breach in progress - root compromise attempt"},
        {"type": "prime_response", "message": "Initiating lockdown protocols and forensic capture"},
        {"type": "prime_tool", "action": "system_lockdown", "message": "Initiating emergency system lockdown - all non-essential services stopped"},
        {"type": "prime_tool", "action": "capture_forensics", "message": "Starting forensic data capture from production server"},
        {"type": "prime_tool", "action": "notify_authorities", "message": "Contacting law enforcement - security breach notification sent"},
        {"type": "prime_tool", "action": "create_memory_block", "message": "CRITICAL BREACH: Immediate documentation required."},
        {"type": "prime_tool", "action": "write_block", "message": "Creating critical alert: ACTIVE BREACH"},
        {"type": "memory", "data": {
            "title": "CRITICAL ALERT",
            "content": "ACTIVE BREACH: Privilege escalation exploit detected. Attack vector: CVE-2024-1337. Target: production server. Response: System lockdown initiated. Law enforcement notified."
        }},
    ]


def _timeline_mitm_late() -> List[Dict]:
    """Hospital MITM / token-abuse narrative (AuthLokr interim demo)."""
    return [
        {"type": "console", "level": "INFO", "message": "Sign-in success: donnie.reed@uho.org from Denver, CO (WIN-LAPTOP-HR01)", "process": "AUTH", "highlight": True},
        {"type": "console", "level": "WARN", "message": "Refresh token reuse: same session ID on second device", "process": "AUTH", "highlight": True},
        {"type": "console", "level": "ERROR", "message": "Same token used from Toledo, OH 4 min later (Unknown-Android)", "process": "AUTH", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Concurrent session anomaly — refresh token reused across geographies"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Impossible travel: Denver → Toledo in 4 min — no flight window"},
        {"type": "escalation", "message": "Token abuse pattern — potential session hijack / MITM"},
        {"type": "prime_response", "message": "Correlating Entra sign-in logs, device compliance, and token fingerprint"},
        {"type": "inter_agent", "sender": "Prime", "message": "Pull last 30 min auth events for donnie.reed@uho.org"},
        {"type": "inter_agent", "sender": "Cerebellum", "message": "Retrieved 12 auth events — 2 active refresh tokens, 2 countries"},
        {"type": "prime_tool", "action": "flag_investigation", "message": "Flagging donnie.reed@uho.org for immediate session review"},
        {"type": "prime_tool", "action": "create_memory_block", "message": "Token abuse indicators documented for security team."},
        {"type": "prime_tool", "action": "write_block", "message": "Creating incident report: TOKEN ABUSE INDICATOR"},
        {"type": "memory", "data": {
            "title": "TOKEN ABUSE INDICATOR",
            "content": "User donnie.reed@uho.org authenticated Denver, CO then same refresh token used Toledo, OH 4 minutes later. Device mismatch: WIN-LAPTOP-HR01 vs Unknown-Android. Impossible geo velocity — investigate session hijack / MITM."
        }},
        {"type": "console", "level": "WARN", "message": "VPN endpoint change detected", "process": "VPN", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "VPN endpoint change — potential tunnel hijack"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Matches change ticket CHG-4421 — planned maintenance. Dismissing."},
        {"type": "console", "level": "WARN", "message": "Group membership added: Privileged-Ops for donnie.reed@uho.org", "process": "IAM", "highlight": True},
        {"type": "console", "level": "CRITICAL", "message": "Global Administrator role assigned outside change window", "process": "IAM", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Privileged group + Global Admin role change on flagged account"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "URGENT: Account modification follows token abuse — likely active MITM"},
        {"type": "escalation", "message": "Critical: privileged account takeover pattern — MITM escalation"},
        {"type": "prime_response", "message": "Revoking active sessions and opening incident bridge"},
        {"type": "prime_tool", "action": "revoke_sessions", "message": "Revoking all refresh tokens for donnie.reed@uho.org"},
        {"type": "prime_tool", "action": "block_ip", "message": "Blocking Toledo endpoint 198.51.100.44 pending investigation"},
        {"type": "prime_tool", "action": "create_memory_block", "message": "CRITICAL: MITM pattern complete — document for hospital SOC."},
        {"type": "prime_tool", "action": "write_block", "message": "Creating critical alert: POTENTIAL MAN-IN-THE-MIDDLE"},
        {"type": "memory", "data": {
            "title": "CRITICAL ALERT",
            "content": "POTENTIAL MAN-IN-THE-MIDDLE: Session token reused Denver CO → Toledo OH (4 min). Post-auth changes: Privileged-Ops group + Global Administrator role on donnie.reed@uho.org. Recommend immediate session revoke, credential rotation, and SOC review."
        }},
    ]


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "authlokr_graph_fixtures"


def _load_fixture(name: str) -> Dict:
    with (_fixture_dir() / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _short_ts(ts: str) -> str:
    return ts.replace("T", " ").replace("Z", " UTC")


def _geo(evt: Dict) -> str:
    loc = evt.get("location") or {}
    return f"{loc.get('city', '?')}, {loc.get('countryOrRegion', '?')}"


def _timeline_fixture_baseline() -> List[Dict]:
    fixture = _load_fixture("fixture_01_behavioral_baseline.json")
    events = sorted(fixture.get("value", []), key=lambda e: e.get("createdDateTime", ""))
    user = events[0].get("userPrincipalName", "unknown-user") if events else "unknown-user"
    out: List[Dict] = [
        {"type": "console", "level": "INFO", "message": f"Fixture loaded: {fixture.get('scenario', 'Baseline')}", "process": "FIXTURE"},
        {"type": "console", "level": "INFO", "message": f"User behavioral profile: {user}", "process": "AUTH"},
    ]
    for evt in events:
        out.append(
            {
                "type": "console",
                "level": "INFO",
                "message": f"Observed sign-in {_short_ts(evt.get('createdDateTime', ''))} from {_geo(evt)} using {evt.get('deviceDetail', {}).get('displayName', 'unknown-device')}",
                "process": "AUTH",
            }
        )
    out.extend(
        [
            {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Repeated after-hours sign-ins detected for finance account"},
            {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Pattern matches learned month-end baseline. Suppressing false positive."},
            {"type": "prime_tool", "action": "write_block", "message": "Documenting baseline suppression decision"},
            {
                "type": "memory",
                "data": {
                    "title": "BASELINE LEARNED - NO ALERT",
                    "content": f"{user} recurrent sign-in pattern is consistent by hour, IP, location, and managed device. AuthLokr suppression active.",
                },
            },
        ]
    )
    return out


def _timeline_fixture_token_replay() -> List[Dict]:
    fixture = _load_fixture("fixture_02_token_replay.json")
    events = sorted(fixture.get("value", []), key=lambda e: e.get("createdDateTime", ""))
    first = events[0]
    second = events[1]
    user = second.get("userPrincipalName", "unknown-user")
    out: List[Dict] = [
        {"type": "console", "level": "INFO", "message": f"Fixture loaded: {fixture.get('scenario', 'Token replay')}", "process": "FIXTURE"},
        {"type": "console", "level": "INFO", "message": f"Legit sign-in {_short_ts(first.get('createdDateTime', ''))} from {_geo(first)}", "process": "AUTH"},
        {"type": "console", "level": "WARN", "message": f"Token/session reuse detected for {user}", "process": "AUTH", "highlight": True},
        {"type": "console", "level": "ERROR", "message": f"Replay event {_short_ts(second.get('createdDateTime', ''))} from {_geo(second)} (non-interactive, unmanaged)", "process": "AUTH", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Same token/session appears across impossible geography delta"},
        {"type": "cerebellum_internal", "sender": "Cerebellum", "message": "Escalating replay anomaly as active session hijack risk"},
        {"type": "escalation", "message": "CRITICAL token replay pattern detected - immediate containment requested"},
        {"type": "prime_response", "message": "Correlating uniqueTokenIdentifier + sessionId + MFA downgrade"},
        {"type": "prime_tool", "action": "revoke_sessions", "message": f"Revoking active sessions for {user}"},
        {"type": "prime_tool", "action": "write_block", "message": "Creating critical alert: TOKEN REPLAY"},
        {
            "type": "memory",
            "data": {
                "title": "CRITICAL ALERT - TOKEN REPLAY",
                "content": f"{user}: same unique token/session replayed {_geo(first)} -> {_geo(second)} in minutes with MFA downgrade and unmanaged device.",
            },
        },
    ]
    return out


def _timeline_fixture_session_hijack() -> List[Dict]:
    fixture = _load_fixture("fixture_03_session_hijacking.json")
    events = sorted(fixture.get("value", []), key=lambda e: e.get("createdDateTime", ""))
    first, second, third = events[0], events[1], events[2]
    user = second.get("userPrincipalName", "unknown-user")
    out: List[Dict] = [
        {"type": "console", "level": "INFO", "message": f"Fixture loaded: {fixture.get('scenario', 'Session hijacking')}", "process": "FIXTURE"},
        {"type": "console", "level": "INFO", "message": f"Session start {_short_ts(first.get('createdDateTime', ''))} from {_geo(first)}", "process": "AUTH"},
        {"type": "console", "level": "CRITICAL", "message": f"Mid-session IP/location jump {_geo(first)} -> {_geo(second)} using same sessionId", "process": "AUTH", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Session continuity from impossible location detected"},
        {"type": "escalation", "message": "CRITICAL session hijacking pattern - terminate session"},
        {"type": "prime_response", "message": "Executing conditional access enforcement workflow"},
        {"type": "prime_tool", "action": "terminate_session", "message": f"Terminating {second.get('sessionId', 'session-id')} for {user}"},
        {"type": "console", "level": "WARN", "message": f"Follow-up event blocked with errorCode {third.get('status', {}).get('errorCode', 'unknown')} ({third.get('status', {}).get('failureReason', 'blocked')})", "process": "AUTH", "highlight": True},
        {"type": "prime_tool", "action": "write_block", "message": "Creating critical alert: SESSION HIJACKING"},
        {
            "type": "memory",
            "data": {
                "title": "CRITICAL ALERT - SESSION HIJACKING",
                "content": f"{user}: sessionId {second.get('sessionId', 'unknown')} moved {_geo(first)} -> {_geo(second)} in minutes; access blocked by policy.",
            },
        },
    ]
    return out


def _audit_detail(evt: Dict, key: str, default: str = "") -> str:
    for pair in evt.get("additionalDetails", []):
        if pair.get("key") == key:
            return str(pair.get("value", default))
    return default


def _timeline_fixture_privilege_chain() -> List[Dict]:
    fixture = _load_fixture("fixture_04_privilege_escalation.json")
    sign_in = (fixture.get("sign_in_logs", {}).get("value") or [])[0]
    audits = sorted(fixture.get("audit_logs", {}).get("value", []), key=lambda e: e.get("activityDateTime", ""))
    role_evt = next((a for a in audits if a.get("activityDisplayName") == "Add member to role"), audits[0])
    pim_evt = next((a for a in audits if a.get("activityDisplayName") == "Add eligible member to role"), audits[0])
    data_evt = next((a for a in audits if a.get("activityDisplayName") == "FileAccessed"), audits[-1])
    actor = sign_in.get("userPrincipalName", "unknown-actor")
    target = (role_evt.get("targetResources") or [{}])[0].get("userPrincipalName", "unknown-target")
    out: List[Dict] = [
        {"type": "console", "level": "INFO", "message": f"Fixture loaded: {fixture.get('scenario', 'Privilege escalation chain')}", "process": "FIXTURE"},
        {"type": "console", "level": "CRITICAL", "message": f"Risky sign-in {_short_ts(sign_in.get('createdDateTime', ''))} from {_geo(sign_in)} via anonymized IP {sign_in.get('ipAddress', '?')}", "process": "AUTH", "highlight": True},
        {"type": "console", "level": "WARN", "message": f"Role assignment {_short_ts(role_evt.get('activityDateTime', ''))}: {target} granted {_audit_detail(role_evt, 'Role.DisplayName', 'Global Administrator')}", "process": "IAM", "highlight": True},
        {"type": "console", "level": "WARN", "message": f"PIM event {_short_ts(pim_evt.get('activityDateTime', ''))}: activation type {_audit_detail(pim_evt, 'PimActivationType', 'unknown')}", "process": "PIM", "highlight": True},
        {"type": "console", "level": "CRITICAL", "message": f"Data access {_short_ts(data_evt.get('activityDateTime', ''))}: {_audit_detail(data_evt, 'FilesAccessed', '?')} files from {_audit_detail(data_evt, 'SiteUrl', 'sensitive site')}", "process": "DATA", "highlight": True},
        {"type": "cerebellum_internal", "sender": "Thalamus", "message": "Cross-source chain detected: sign-in risk -> role grant -> PIM bypass -> data access"},
        {"type": "escalation", "message": "CRITICAL privilege escalation chain confirmed"},
        {"type": "prime_response", "message": "Correlating sign-in and directory audit telemetry into single attack chain"},
        {"type": "prime_tool", "action": "suspend_accounts", "message": f"Suspending actor {actor} and target {target} pending IR"},
        {"type": "prime_tool", "action": "write_block", "message": "Creating critical alert: PRIVILEGE ESCALATION CHAIN"},
        {
            "type": "memory",
            "data": {
                "title": "CRITICAL ALERT - PRIVILEGE ESCALATION CHAIN",
                "content": f"Compromised sign-in by {actor} correlated with Global Admin grant to {target} and bulk sensitive file access from IP {sign_in.get('ipAddress', '?')}.",
            },
        },
    ]
    return out


def _timeline_graph_fixtures_all() -> List[Dict]:
    out: List[Dict] = [
        {"type": "console", "level": "INFO", "message": "Graph fixture bundle loaded (4 scenarios)", "process": "FIXTURE"},
        {"type": "console", "level": "INFO", "message": "Running baseline, token replay, session hijack, and privilege chain narratives", "process": "FIXTURE"},
    ]
    for section in [
        _timeline_fixture_baseline(),
        _timeline_fixture_token_replay(),
        _timeline_fixture_session_hijack(),
        _timeline_fixture_privilege_chain(),
    ]:
        out.extend(section)
    return out


def build_timeline(scenario: str) -> List[Dict]:
    if scenario == "graph-baseline":
        return _timeline_fixture_baseline()
    if scenario == "graph-token-replay":
        return _timeline_fixture_token_replay()
    if scenario == "graph-session-hijack":
        return _timeline_fixture_session_hijack()
    if scenario == "graph-privilege-chain":
        return _timeline_fixture_privilege_chain()
    if scenario == "graph-fixtures":
        return _timeline_graph_fixtures_all()
    if scenario == "mitm":
        return _timeline_shared_prefix() + _timeline_mitm_late()
    return _timeline_shared_prefix() + _timeline_forensiq_late()


class EventEngine:
    """Manages the demo timeline and events"""
    
    def __init__(self, app):
        self.app = app
        self.event_index = 0
        self.timeline_timer: Optional[Timer] = None
        self.background_timer: Optional[Timer] = None
        self.background_index = 0
        self.test_mode = TEST_MODE
        
        # Continuous background chatter (cycles continuously)
        self.background_chatter = [
            {"type": "console", "level": "INFO", "message": "Database connection pool: 47/50 active", "process": "DB"},
            {"type": "console", "level": "INFO", "message": "Active user sessions: 1,247", "process": "AUTH"},
            {"type": "console", "level": "DEBUG", "message": "API calls/min: 8,934", "process": "API"},
            {"type": "console", "level": "INFO", "message": "Email queue processing: 156 messages", "process": "MAIL"},
            {"type": "console", "level": "DEBUG", "message": "CDN cache hit ratio: 94.7%", "process": "CDN"},
            {"type": "console", "level": "INFO", "message": "VPN connections: 312 active", "process": "VPN"},
            {"type": "console", "level": "DEBUG", "message": "File system I/O: 2.3GB/s read, 890MB/s write", "process": "FS"},
            {"type": "console", "level": "INFO", "message": "Cloud backup sync: 78% complete", "process": "CLOUD"},
            {"type": "console", "level": "DEBUG", "message": "Memory usage: 67% across 24 servers", "process": "SYS"},
            {"type": "console", "level": "INFO", "message": "SSL certificate validation: 1,456 checks/min", "process": "SSL"},
            {"type": "console", "level": "INFO", "message": "User authentication: sarah.johnson@company.com", "process": "AUTH"},
            {"type": "console", "level": "DEBUG", "message": "Network latency: 12ms avg", "process": "NET"},
            {"type": "console", "level": "INFO", "message": "Firewall rules updated: 3 new entries", "process": "FW"},
            {"type": "console", "level": "DEBUG", "message": "Load balancer health check: all nodes green", "process": "LB"},
            {"type": "console", "level": "DEBUG", "message": "CPU utilization: web01=23%, web02=31%, web03=28%", "process": "SYS"},
            {"type": "console", "level": "INFO", "message": "User logout: mike.chen@company.com", "process": "AUTH"},
            {"type": "console", "level": "DEBUG", "message": "Redis cache operations: 45,678/min", "process": "CACHE"},
            {"type": "console", "level": "INFO", "message": "S3 bucket sync: 892 files transferred", "process": "CLOUD"},
            {"type": "console", "level": "DEBUG", "message": "DNS queries resolved: 12,456/min", "process": "DNS"},
            {"type": "console", "level": "INFO", "message": "Application deployment: v2.4.1 to staging", "process": "DEPLOY"},
            {"type": "console", "level": "DEBUG", "message": "WebSocket connections: 1,834 active", "process": "WS"},
            {"type": "console", "level": "INFO", "message": "Database query performance: avg 45ms", "process": "DB"},
            {"type": "console", "level": "INFO", "message": "User login: admin@company.com from 10.0.1.45", "process": "AUTH"},
            {"type": "console", "level": "DEBUG", "message": "Elasticsearch indexing: 23,445 docs/min", "process": "SEARCH"},
            {"type": "console", "level": "INFO", "message": "Container health check: 47/48 healthy", "process": "DOCKER"},
            {"type": "console", "level": "DEBUG", "message": "Message queue depth: RabbitMQ 234 msgs", "process": "MQ"},
            {"type": "console", "level": "INFO", "message": "Log rotation completed: 15GB archived", "process": "LOG"},
            {"type": "console", "level": "INFO", "message": "System health check: All services nominal", "process": "SYS"},
            {"type": "console", "level": "DEBUG", "message": "Cache hit ratio: 94.2%", "process": "CACHE"},
            {"type": "console", "level": "INFO", "message": "Kubernetes pods: 156 running, 3 pending", "process": "K8S"},
            {"type": "console", "level": "DEBUG", "message": "Nginx access logs: 89,456 requests/min", "process": "WEB"},
            {"type": "console", "level": "INFO", "message": "User session timeout: 12 users auto-logged out", "process": "AUTH"},
            {"type": "console", "level": "DEBUG", "message": "Disk I/O wait time: 2.3ms avg", "process": "DISK"},
            {"type": "console", "level": "INFO", "message": "API rate limiting: 3 clients throttled", "process": "API"},
            {"type": "console", "level": "DEBUG", "message": "TCP connections: 45,678 established", "process": "NET"},
            {"type": "console", "level": "DEBUG", "message": "JVM heap usage: 68% across app servers", "process": "JVM"},
            {"type": "console", "level": "INFO", "message": "Backup verification: 847 files validated", "process": "BACKUP"},
            {"type": "console", "level": "INFO", "message": "SSL handshake success rate: 99.7%", "process": "SSL"},
            {"type": "console", "level": "DEBUG", "message": "MongoDB operations: 12,345 reads, 567 writes/min", "process": "MONGO"},
            {"type": "console", "level": "INFO", "message": "CDN edge cache refresh: 234 objects updated", "process": "CDN"},
            {"type": "console", "level": "DEBUG", "message": "Thread pool utilization: 76% avg", "process": "THREAD"},
        ]

        self.timeline = build_timeline(SCENARIO)
    def start_demo(self):
        """Start both the demo timeline and background chatter"""
        if not self.timeline_timer:
            self.timeline_timer = self.app.set_interval(1.5, self.next_timeline_event)  # 1.5s between timeline events
        # Start background chatter with first random delay
        self.schedule_next_background_event()
    
    def next_timeline_event(self):
        """Process the next event in the main timeline"""
        if self.event_index >= len(self.timeline):
            if self.timeline_timer:
                self.timeline_timer.stop()
            self.app.post_message(DemoComplete())
            return
        
        event = self.timeline[self.event_index]
        if self.test_mode:
            print(f"[DEBUG] Processing timeline event {self.event_index}: {event['type']}")
        self.event_index += 1
        self._process_event(event)
    
    def schedule_next_background_event(self):
        """Schedule the next background event with random timing"""
        # Random delay between 100ms and 800ms for realistic bursts
        delay = random.uniform(0.1, 0.8)
        
        # Occasionally add longer pauses (10% chance of 1-3 second pause)
        if random.random() < 0.1:
            delay = random.uniform(1.0, 3.0)
        
        self.app.set_timer(delay, self.next_background_event)
    
    def next_background_event(self):
        """Process the next background chatter event (cycles continuously)"""
        event = self.background_chatter[self.background_index % len(self.background_chatter)].copy()
        self.background_index += 1
        
        # Add some randomization to make logs feel more dynamic
        event = self._randomize_log_message(event)
        
        self._process_event(event)
        
        # Schedule the next background event with random timing
        self.schedule_next_background_event()
    
    def _randomize_log_message(self, event):
        """Add some randomization to numeric values in log messages"""
        if event["type"] != "console":
            return event
        
        message = event["message"]
        
        # Randomize common patterns in log messages
        replacements = [
            (r'(\d+)/(\d+) active', lambda m: f"{random.randint(int(m.group(1))-5, int(m.group(1))+5)}/{m.group(2)} active"),
            (r'(\d+,\d+)', lambda m: f"{random.randint(1000, 9999):,}"),
            (r'(\d+) messages', lambda m: f"{random.randint(100, 300)} messages"),
            (r'(\d+\.\d+)%', lambda m: f"{random.uniform(90, 99):.1f}%"),
            (r'(\d+) active', lambda m: f"{random.randint(int(m.group(1))-50, int(m.group(1))+50)} active"),
            (r'(\d+\.\d+)GB/s', lambda m: f"{random.uniform(1.8, 2.8):.1f}GB/s"),
            (r'(\d+)MB/s', lambda m: f"{random.randint(800, 1200)}MB/s"),
            (r'(\d+)ms avg', lambda m: f"{random.randint(8, 20)}ms avg"),
            (r'(\d+) servers', lambda m: f"{random.randint(20, 28)} servers"),
            (r'(\d+) running', lambda m: f"{random.randint(150, 170)} running"),
            (r'(\d+) pending', lambda m: f"{random.randint(1, 8)} pending"),
        ]
        
        # Apply randomization with 30% chance to keep some predictability
        if random.random() < 0.3:
            for pattern, replacement in replacements:
                if re.search(pattern, message):
                    try:
                        message = re.sub(pattern, replacement, message)
                        break  # Only apply one randomization per message
                    except:
                        pass  # If randomization fails, keep original
        
        event["message"] = message
        return event
    
    def _process_event(self, event):
        
        if event["type"] == "console":
            self.app.post_message(ConsoleLog(
                level=event["level"],
                message=event["message"],
                process=event["process"],
                highlight=event.get("highlight", False)
            ))
        elif event["type"] == "cerebellum_internal":
            self.app.post_message(CerebellumInternalMessage(
                sender=event["sender"],
                message=event["message"]
            ))
        elif event["type"] == "escalation":
            self.app.post_message(EscalationMessage(
                message=event["message"]
            ))
        elif event["type"] == "prime_response":
            self.app.post_message(PrimeResponseMessage(
                message=event["message"]
            ))
        elif event["type"] == "inter_agent":
            self.app.post_message(InterAgentMessage(
                sender=event["sender"],
                message=event["message"]
            ))
        elif event["type"] == "prime_tool":
            self.app.post_message(PrimeToolMessage(
                action=event["action"],
                message=event["message"]
            ))
        elif event["type"] == "memory":
            if self.test_mode:
                with open("debug.log", "a") as f:
                    f.write(f"[DEBUG] Posting memory block message: {event['data'].get('title', 'NO TITLE')}\n")
            self.app.post_message(MemoryBlock(data=event["data"]))

# Custom messages for inter-widget communication
class ConsoleLog(Message):
    def __init__(self, level: str, message: str, process: str, highlight: bool = False):
        self.level = level
        self.message = message
        self.process = process
        self.highlight = highlight  # True if this message is sent to Cerebellum
        super().__init__()

class CerebellumInternalMessage(Message):
    def __init__(self, sender: str, message: str):
        self.sender = sender
        self.message = message
        super().__init__()

class EscalationMessage(Message):
    def __init__(self, message: str):
        self.message = message
        super().__init__()

class PrimeResponseMessage(Message):
    def __init__(self, message: str):
        self.message = message
        super().__init__()

class InterAgentMessage(Message):
    def __init__(self, sender: str, message: str):
        self.sender = sender
        self.message = message
        super().__init__()

class PrimeToolMessage(Message):
    def __init__(self, action: str, message: str):
        self.action = action
        self.message = message
        super().__init__()

class MemoryBlock(Message):
    def __init__(self, data: Dict):
        self.data = data
        super().__init__()

class DemoComplete(Message):
    pass

class ConsolePane(RichLog):
    """Right column - Console log output"""
    
    def __init__(self):
        super().__init__(
            name="console",
            id="console-pane",
            highlight=True,
            markup=True,
            wrap=False,
            auto_scroll=True
        )
        self.border_title = "THALAMUS (INPUT STREAM)"
        
    def add_log(self, level: str, message: str, process: str, highlight: bool = False):
        """Add a log entry with proper formatting"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Color coding for different log levels
        level_colors = {
            "DEBUG": "bright_black",
            "INFO": "bright_blue", 
            "WARN": "yellow",
            "ERROR": "red",
            "CRITICAL": "bright_red"
        }
        
        color = level_colors.get(level, "white")
        
        # Format: [timestamp] [LEVEL] process: message
        log_line = Text()
        log_line.append(f"[{timestamp}] ", style="bright_black")
        
        if highlight:
            # Highlighted messages sent to Cerebellum
            log_line.append(f"[{level:>8}] >>> ", style=f"bold bright_yellow")
            log_line.append(f"{process:>6}: ", style="bright_yellow")
            log_line.append(message, style="bright_white")
            log_line.append(" <<< [→ CEREBELLUM]", style="bold bright_yellow")
        else:
            # Regular system logs
            log_line.append(f"[{level:>8}] ", style=f"bold {color}")
            log_line.append(f"{process:>6}: ", style="bright_green")
            log_line.append(message, style="white")
        
        self.write(log_line)

class ToolMessage(Static):
    """Tool action message widget - always instant display"""
    
    def __init__(self, action: str, message: str):
        super().__init__()
        self.action = action
        self.message = message
        
    def compose(self) -> ComposeResult:
        yield Static("", id="tool-content")
        
    def on_mount(self):
        """Display tool message immediately"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_text = Text()
        formatted_text.append(f"[{timestamp}] ", style="bright_black")
        formatted_text.append(f"[Tool: {self.action}] ", style="bold yellow")
        formatted_text.append(self.message, style="yellow")
        
        content = self.query_one("#tool-content", Static)
        content.update(formatted_text)

class ChatMessage(Static):
    """Individual chat message widget with streaming capability"""
    
    def __init__(self, sender: str, message: str, sender_color: str = "white", should_stream: bool = True):
        super().__init__()
        self.sender = sender
        self.message = message
        self.sender_color = sender_color
        self.should_stream = should_stream
        self.current_text = ""
        self.char_index = 0
        self.streaming_timer: Optional[Timer] = None
        
    def compose(self) -> ComposeResult:
        yield Static("", id="message-content")
        
    def on_mount(self):
        """Start streaming the message when mounted"""
        if self.should_stream:
            self.start_streaming()
        else:
            self.display_full_message()
        
    def display_full_message(self):
        """Display the complete message immediately"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_text = self.format_complete_message(timestamp, self.sender, self.message)
        content = self.query_one("#message-content", Static)
        content.update(formatted_text)
        
    def start_streaming(self):
        """Begin character-by-character streaming of message text only"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        # Display timestamp and sender immediately
        self.static_part = f"[{timestamp}] {self.sender}: "
        self.streaming_part = self.message
        self.char_index = 0
        self.current_text = ""
        
        # Display static part immediately
        formatted_text = self.format_partial_message(self.static_part, "")
        content = self.query_one("#message-content", Static)
        content.update(formatted_text)
        
        # Start streaming timer for message text (30ms = ~33 chars/second)
        self.streaming_timer = self.set_interval(0.03, self.stream_next_char)
        
    def stream_next_char(self):
        """Add the next character of the message to the display"""
        if self.char_index < len(self.streaming_part):
            self.current_text = self.streaming_part[:self.char_index + 1]
            self.char_index += 1
            
            # Format the text with colors
            formatted_text = self.format_partial_message(self.static_part, self.current_text)
            content = self.query_one("#message-content", Static)
            content.update(formatted_text)
        else:
            # Streaming complete
            if self.streaming_timer:
                self.streaming_timer.stop()
                
    def format_complete_message(self, timestamp: str, sender: str, message: str) -> Text:
        """Format complete message with proper colors"""
        formatted = Text()
        formatted.append(f"[{timestamp}] ", style="bright_black")
        formatted.append(f"{sender}:", style=f"bold {self.sender_color}")
        formatted.append(f" {message}", style="white")
        return formatted
        
    def format_partial_message(self, static_part: str, streaming_part: str) -> Text:
        """Format partial message during streaming"""
        # Parse static part: [timestamp] sender: 
        match = re.match(r'(\[[\d:]+\])\s+([^:]+):\s*', static_part)
        if match:
            timestamp, sender = match.groups()
            
            formatted = Text()
            formatted.append(f"[{timestamp}] ", style="bright_black")
            formatted.append(f"{sender}:", style=f"bold {self.sender_color}")
            formatted.append(f" {streaming_part}", style="white")
            return formatted
        else:
            return Text(static_part + streaming_part, style="white")

def format_chat_line(sender: str, message: str, sender_color: str = "white") -> Text:
  """Format a chat line for RichLog panes (renders reliably in terminal capture)."""
  timestamp = datetime.now().strftime('%H:%M:%S')
  line = Text()
  line.append(f"[{timestamp}] ", style="bright_black")
  line.append(f"{sender}:", style=f"bold {sender_color}")
  line.append(f" {message}", style="white")
  return line


def format_tool_line(action: str, message: str) -> Text:
  timestamp = datetime.now().strftime('%H:%M:%S')
  line = Text()
  line.append(f"[{timestamp}] ", style="bright_black")
  line.append(f"[Tool: {action}] ", style="bold yellow")
  line.append(message, style="yellow")
  return line


def memory_wrap_width(app=None) -> int:
    """Estimate safe wrap width for the center memory column."""
    if app is not None and getattr(app, "size", None) and app.size.width:
        per_col = max(app.size.width // 3, 40)
        return max(per_col - 10, 44)
    try:
        cols = int(os.environ.get("COLUMNS", str(MEMORY_WRAP_WIDTH + 8)))
    except ValueError:
        cols = MEMORY_WRAP_WIDTH + 8
    return max(cols // 3 - 10, MEMORY_WRAP_WIDTH)


def format_memory_block(data: Dict, wrap_width: Optional[int] = None) -> Text:
  title = data.get("title", "MEMORY BLOCK")
  content = data.get("content", "No content available")
  width = wrap_width if wrap_width is not None else MEMORY_WRAP_WIDTH
  wrapped_title = textwrap.fill(title, width=width)
  wrapped_content = textwrap.fill(content, width=width)
  line = Text()
  line.append(f"══ {wrapped_title} ══\n", style="bold yellow")
  line.append(wrapped_content, style="white")
  line.append("\n", style="white")
  return line


class _ChatPane(RichLog):
  """Shared RichLog chat pane (ScrollView + dynamic mount does not paint in headless capture)."""

  def __init__(self, name: str, pane_id: str, title: str):
    super().__init__(
      name=name,
      id=pane_id,
      highlight=True,
      markup=True,
      wrap=True,
      auto_scroll=True,
    )
    self.border_title = title

  def write_chat(self, sender: str, message: str, sender_color: str = "white") -> None:
    self.write(format_chat_line(sender, message, sender_color))


class CerebellumPane(_ChatPane):
  def __init__(self):
    super().__init__("cerebellum", "cerebellum-pane", "CEREBELLUM (REFLEX)")


class PrimePane(_ChatPane):
  def __init__(self):
    super().__init__("prime", "prime-pane", "PRIME AGENT (COGNITION)")

  def write_tool(self, action: str, message: str) -> None:
    self.write(format_tool_line(action, message))


class MemoryPane(RichLog):
  def __init__(self):
    super().__init__(
      name="memory",
      id="memory-pane",
      highlight=True,
      markup=True,
      wrap=True,
      auto_scroll=True,
    )
    self.border_title = "MEMORY CORE"

  def add_memory_block(self, data: Dict):
    if TEST_MODE:
      print(f"[DEBUG] MemoryPane.add_memory_block called with: {data}")
    width = memory_wrap_width(self.app)
    self.write(format_memory_block(data, wrap_width=width))

class SanctumApp(App):
    """Main Textual application"""
    
    CSS = """
    Screen {
        layout: horizontal;
    }
    
    #left-column {
        width: 1fr;
        layout: vertical;
    }
    

    
    #cerebellum-pane {
        height: 1fr;
        border: solid $accent;
        border-title-color: $accent;
        border-title-style: bold;
    }
    
    #prime-pane {
        height: 1fr;
        border: solid $accent;
        border-title-color: $accent;
        border-title-style: bold;
        margin-top: 1;
    }
    
    #memory-pane {
        border: solid $warning;
        border-title-color: $warning;
        border-title-style: bold;
        padding: 0 1;
    }
    
    #console-pane {
        border: solid $success;
        border-title-color: $success;
        border-title-style: bold;
    }
    
    .memory-block {
        margin: 1;
        padding: 1;
        border: solid $warning;
        background: $surface;
    }
    
    .memory-title {
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    
    .memory-content {
        color: $text;
        text-wrap: wrap;
    }
    
    /* SSH Login Screen Styles */
    #ssh-container {
        background: black;
        color: green;
        layout: vertical;
    }
    
    #ssh-output {
        height: 1fr;
        background: black;
        color: green;
        padding: 1;
        scrollbar-gutter: stable;
    }
    
    #ssh-input {
        height: 3;
        background: black;
        color: green;
        border: none;
        margin: 0 1;
    }
    
    #ssh-input:focus {
        border: none;
        outline: none;
        background: black;
        color: green;
    }

    """
    
    TITLE = "Sanctum Cognitive UI Demo"
    
    def __init__(self):
        super().__init__()
        self.event_engine = EventEngine(self)
        self.ssh_simulator = SSHLoginSimulator(self)
        self.main_ui_ready = False
        
    def compose(self) -> ComposeResult:
        """Create the main layout"""
        with Horizontal():
            # Left column - Chat panes
            with Vertical(id="left-column"):
                yield CerebellumPane()
                yield PrimePane()
            
            # Center column - Memory blocks
            yield MemoryPane()
            
            # Right column - Console logs
            yield ConsolePane()
    
    def on_mount(self):
        """Initialize the application"""
        self.title = "Sanctum Security Suite - Remote Access"
        if TEST_MODE:
            print("[TEST] App mounted, starting SSH login...")
        
        # Start with SSH login simulation
        self.ssh_simulator.start_login_sequence()
        
        # Auto-close timer if enabled
        if AUTO_CLOSE:
            timeout_seconds = AUTO_CLOSE_SECONDS
            if timeout_seconds <= 0:
                timeout_seconds = 130.0 if SCENARIO == "graph-fixtures" else 25.0
            self.set_timer(timeout_seconds, self.exit)  # Includes SSH login pre-roll
    
    def on_console_log(self, message: ConsoleLog):
        """Handle console log messages"""
        console = self.query_one("#console-pane", ConsolePane)
        console.add_log(message.level, message.message, message.process, message.highlight)
    
    def on_cerebellum_internal_message(self, message: CerebellumInternalMessage):
        """Handle internal cerebellum messages (Thalamus → Cerebellum only)"""
        cerebellum = self.query_one("#cerebellum-pane", CerebellumPane)
        sender_color = "bright_blue" if message.sender == "Thalamus" else "bright_green"
        cerebellum.write_chat(message.sender, message.message, sender_color)
    
    def on_escalation_message(self, message: EscalationMessage):
        """Handle escalation from Cerebellum to Prime (appears in both windows)"""
        cerebellum = self.query_one("#cerebellum-pane", CerebellumPane)
        prime = self.query_one("#prime-pane", PrimePane)
        
        def add_escalation():
            cerebellum.write_chat("Cerebellum", message.message, "bright_green")
            prime.write_chat("Cerebellum", message.message, "bright_green")
            
        self.set_timer(1.0, add_escalation)  # 1 second delay
    
    def on_prime_response_message(self, message: PrimeResponseMessage):
        """Handle Prime Agent response to escalation"""
        prime = self.query_one("#prime-pane", PrimePane)
        
        def add_response():
            prime.write_chat("Prime", message.message, "bright_cyan")
            
        self.set_timer(1.5, add_response)  # 1.5 second delay
    
    def on_inter_agent_message(self, message: InterAgentMessage):
        """Handle inter-agent communication (appears in both windows)"""
        cerebellum = self.query_one("#cerebellum-pane", CerebellumPane)
        prime = self.query_one("#prime-pane", PrimePane)
        
        if message.sender == "Prime":
            prime.write_chat("Prime", message.message, "bright_cyan")
            cerebellum.write_chat("Prime", message.message, "bright_cyan")
        else:
            cerebellum.write_chat("Cerebellum", message.message, "bright_green")
            prime.write_chat("Cerebellum", message.message, "bright_green")
    
    def on_prime_tool_message(self, message: PrimeToolMessage):
        """Handle Prime Agent tool actions"""
        prime = self.query_one("#prime-pane", PrimePane)
        prime.write_tool(message.action, message.message)
    
    def on_memory_block(self, message: MemoryBlock):
        """Handle memory block creation"""
        if TEST_MODE:
            with open("debug.log", "a") as f:
                f.write(f"[DEBUG] Creating memory block: {message.data.get('title', 'NO TITLE')}\n")
        memory = self.query_one("#memory-pane", MemoryPane)
        memory.add_memory_block(message.data)
    
    def on_demo_complete(self, message: DemoComplete):
        """Handle demo completion"""
        if AUTO_CLOSE:
            self.set_timer(2.0, self.exit)
    
    def action_quit(self):
        """Quit the application"""
        self.exit()
    
    def on_key(self, event: events.Key):
        """Handle key events"""
        if event.key == "q":
            self.exit()
        elif event.key == "f11":
            # Toggle fullscreen (not really applicable in terminal)
            pass

def main():
    """Main entry point"""
    global TEST_MODE, AUTO_CLOSE, AUTO_CLOSE_SECONDS, DEBUG_VISUAL, SCREENSHOT_MODE, SCENARIO
    
    parser = argparse.ArgumentParser(description="Sanctum Cognitive UI Demo - TUI Version")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--auto-close", action="store_true", help="Auto-close after demo")
    parser.add_argument("--debug-visual", action="store_true", help="Enable visual debugging")
    parser.add_argument("--screenshot", action="store_true", help="Enable screenshot mode")
    parser.add_argument(
        "--scenario",
        choices=(
            "forensiq",
            "mitm",
            "graph-fixtures",
            "graph-baseline",
            "graph-token-replay",
            "graph-session-hijack",
            "graph-privilege-chain",
        ),
        default="forensiq",
        help="Demo incident script: legacy scenarios or Graph fixture-driven scenarios",
    )
    parser.add_argument(
        "--auto-close-seconds",
        type=float,
        default=0,
        help="Override auto-close timer in seconds (0 uses scenario default).",
    )
    
    args = parser.parse_args()
    
    TEST_MODE = args.test
    AUTO_CLOSE = args.auto_close
    AUTO_CLOSE_SECONDS = args.auto_close_seconds
    DEBUG_VISUAL = args.debug_visual
    SCREENSHOT_MODE = args.screenshot
    SCENARIO = args.scenario
    
    if TEST_MODE:
        print(f"[TEST] Starting TUI version with options: test={TEST_MODE}, auto_close={AUTO_CLOSE}, scenario={SCENARIO}")
    
    # Run the Textual app
    app = SanctumApp()
    app.run()

if __name__ == "__main__":
    main() 