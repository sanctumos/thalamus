# AuthLokr Demo Fixture Files
**For:** Mark (rizzn)  
**From:** John  
**Date:** 2026-06-05  
**Purpose:** Detection engine validation — 4 mandatory demo scenarios

---

## Lab Tenant

- **Tenant ID:** `29db4772-d8c8-4a72-a081-b475fb5978ad`
- **Domain:** `Lab709.onmicrosoft.com`

You'll need an App Registration with `AuditLog.Read.All` and `Directory.Read.All` to pull live logs. I'll set that up and send creds separately. For now, use these fixtures to validate detection rules.

---

## Fixture Files

### fixture_01_behavioral_baseline.json
**Graph endpoint:** `GET /auditLogs/signIns`  
**Scenario:** Maria Rainwaters — finance user with recurring 2AM sign-ins during month-end close.  
**Detection goal:** AuthLokr should learn this is normal and NOT fire. P2 fires HIGH risk every time. This is our false positive reduction demo.  
**Key fields to baseline:** `userPrincipalName`, `ipAddress`, `location.city`, `createdDateTime` (hour), `deviceDetail.deviceId`

---

### fixture_02_token_replay.json
**Graph endpoint:** `GET /auditLogs/signIns`  
**Scenario:** Eddie Pergola — legitimate sign-in from Denver, token replayed from Moscow 4 minutes later.  
**Detection goal:** Fire CRITICAL on second event.  
**Key detection logic:**
- Same `uniqueTokenIdentifier` across both events
- Same `sessionId` across both events  
- Location delta: Denver (39.7, -104.9) → Moscow (55.7, 37.6) in 4 minutes = impossible
- Second event: `isInteractive: false`, no MFA, unmanaged device
- `authenticationRequirement` drops from `multiFactorAuthentication` to `singleFactorAuthentication`

---

### fixture_03_session_hijacking.json
**Graph endpoint:** `GET /auditLogs/signIns`  
**Scenario:** Austin Ivaska — session starts Denver, continues from Shanghai 6 minutes later. Third event shows AuthLokr blocking further access (errorCode 53003).  
**Detection goal:** Fire CRITICAL on second event, trigger PIM workflow that produces third event.  
**Key detection logic:**
- Same `sessionId` (`HIJACK-SESSION-ID-ZP4418`) across all 3 events
- IP change mid-session: `24.116.88.142` (Denver) → `116.228.100.45` (Shanghai)
- Denver→Shanghai impossible in 6 minutes
- Device changes from managed Windows 11 to unmanaged Linux
- `riskEventTypes` includes `impossibleTravel`

---

### fixture_04_privilege_escalation.json
**Graph endpoint (sign-ins):** `GET /auditLogs/signIns`  
**Graph endpoint (audit):** `GET /auditLogs/directoryAudits`  
**Scenario:** Dwain Martinex compromised account → grants Global Admin to bridgett.maleonado → bulk data access from HR site. Full 4-event attack chain over 6 minutes.  
**Detection goal:** Correlate sign-in risk + audit log role assignment + data access into single CRITICAL chain alert.  
**Key detection logic:**
- Sign-in: `riskLevelAggregated: high`, Tor exit node IP `185.220.101.34`, 2AM, no MFA
- Audit: `activityDisplayName: "Add member to role"` + `Role.DisplayName: "Global Administrator"` — same IP as risky sign-in, 4 min later
- Audit: PIM direct assignment bypass (permanent grant, no approval)
- Audit: 47 files accessed from HR-Confidential site 2 min after role grant
- All events share IP `185.220.101.34` — correlation anchor

---

## Detection Rule Validation Checklist

| Scenario | Expected Alert | Severity | Trigger Fields |
|---|---|---|---|
| Baseline (2AM normal) | NO ALERT after 30-day learning | - | `userPrincipalName` + `location` + `hour` pattern |
| Token Replay | CRITICAL | CRITICAL | `uniqueTokenIdentifier` match + location delta |
| Session Hijacking | CRITICAL | CRITICAL | `sessionId` match + IP change + impossible travel |
| Privilege Escalation Chain | CRITICAL | CRITICAL | Sign-in risk + audit role grant + same IP within time window |

---

## Notes

- All fixtures use real Microsoft Graph API schema (`/auditLogs/signIns` and `/auditLogs/directoryAudits`)
- `_authlokr_note` fields are metadata for your reference — strip before production
- `authlokr_attack_chain_summary` in fixture_04 shows the expected chain output format for the dashboard
- Users referenced (maria.rainwaters, eddie.pergola, austin.ivaska, dwain.martinex, bridgett.maleonado) match the Lab tenant entities BadZure will populate
