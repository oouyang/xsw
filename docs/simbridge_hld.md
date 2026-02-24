# SimBridge — High-Level Design

> Bridge your SIM cards across devices over the internet.

**Version**: 1.0
**Date**: 2026-02-19
**Status**: Draft

---

## 1. Problem Statement

A user has two phones:

- **Phone A** — holds 2 SIM cards (personal, work, or regional numbers)
- **Phone B** — the phone they carry day-to-day

The user wants to make calls and send/receive SMS using Phone A's SIM cards **from Phone B**, without inserting those SIMs into Phone B. All communication between the two phones happens over the internet (WiFi or mobile data).

---

## 2. System Overview

SimBridge consists of three components:

| Component        | Runs On                      | Role                                             |
| ---------------- | ---------------------------- | ------------------------------------------------ |
| **Host App**     | Phone A (Android, has SIMs)  | Always-on agent that executes telephony commands |
| **Relay Server** | Cloud VPS                    | Message broker, auth, signaling                  |
| **Client App**   | Phone B (Android, WiFi only) | User-facing dialer and messenger                 |

```
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│                  │  WSS   │                  │  WSS   │                  │
│   Host App       │◄──────►│   Relay Server   │◄──────►│   Client App     │
│   (Phone A)      │        │                  │        │   (Phone B)      │
│                  │        │                  │        │                  │
│  ┌─────────────┐ │        │  - Auth & pair   │        │  - Dialer UI     │
│  │ SIM 1       │ │        │  - WebSocket hub │        │  - SMS composer  │
│  │ SIM 2       │ │        │  - Command queue │        │  - SIM selector  │
│  └──────┬──────┘ │        │  - FCM push      │        │  - Call/SMS logs │
│         ▼        │        │  - TURN/signal   │        │  - Notifications │
│  Android Telecom │        │                  │        │                  │
│  APIs            │        │                  │        │                  │
└─────────────────┘        └─────────────────┘        └─────────────────┘
```

---

## 3. Component Design

### 3.1 Host App (Phone A)

**Purpose**: Persistent agent that bridges internet commands to native telephony.

**Runtime model**: Android Foreground Service with persistent notification. Whitelisted from battery optimization to prevent OS from killing the process.

**Connectivity**: Maintains a persistent WebSocket (WSS) connection to the Relay Server. Reconnects automatically on drop. Falls back to FCM push to wake up if the socket is lost.

**Capabilities**:

| Capability            | Android API                                           | Notes                                |
| --------------------- | ----------------------------------------------------- | ------------------------------------ |
| Place outgoing call   | `TelecomManager`, `ConnectionService`                 | Select SIM via `PhoneAccountHandle`  |
| Send SMS              | `SmsManager.sendTextMessage()`                        | Select SIM via `SubscriptionManager` |
| Receive incoming call | `BroadcastReceiver` on `PHONE_STATE`                  | Forward caller ID and SIM slot       |
| Receive incoming SMS  | `BroadcastReceiver` on `SMS_RECEIVED`                 | Forward sender, body, SIM slot       |
| Bridge call audio     | `AudioRecord` + `AudioTrack` via `ConnectionService`  | Stream through WebRTC to Client      |
| Report SIM info       | `SubscriptionManager.getActiveSubscriptionInfoList()` | Carrier name, number, slot index     |

**Required permissions**:

```
CALL_PHONE
READ_PHONE_STATE
SEND_SMS
RECEIVE_SMS
READ_CALL_LOG
READ_PHONE_NUMBERS
FOREGROUND_SERVICE
INTERNET
```

**Command protocol** (received from Relay):

```json
{ "cmd": "MAKE_CALL",  "sim": 1, "to": "+886912345678", "req_id": "abc123" }
{ "cmd": "SEND_SMS",   "sim": 2, "to": "+886912345678", "body": "Hello", "req_id": "def456" }
{ "cmd": "HANG_UP",    "req_id": "abc123" }
{ "cmd": "GET_SIMS" }
```

**Event protocol** (sent to Relay):

```json
{ "event": "CALL_STATE",    "state": "dialing|ringing|active|ended", "sim": 1, "req_id": "abc123" }
{ "event": "SMS_SENT",      "status": "ok|failed", "req_id": "def456" }
{ "event": "INCOMING_CALL",  "sim": 2, "from": "+1234567890" }
{ "event": "INCOMING_SMS",   "sim": 1, "from": "+1234567890", "body": "Hi there" }
{ "event": "SIM_INFO",       "sims": [{"slot":1,"carrier":"CHT","number":"+886..."},{"slot":2,...}] }
```

---

### 3.2 Relay Server

**Purpose**: Stateless message broker that routes commands and events between paired Host and Client devices. Also serves as WebRTC signaling and TURN server for voice calls.

**Core responsibilities**:

1. **Authentication** — Account registration, login (JWT-based).
2. **Device pairing** — Link one Host to one or more Clients under the same account.
3. **WebSocket hub** — Maintain named connections (`host:<account_id>`, `client:<account_id>:<device_id>`). Route messages between them.
4. **Command queue** — If Host is temporarily offline, buffer commands in Redis. Deliver when Host reconnects.
5. **Push wakeup** — Send FCM notification to Host if its WebSocket has been disconnected for more than 30 seconds and a command arrives.
6. **WebRTC signaling** — Relay SDP offers/answers and ICE candidates between Host and Client for voice calls.
7. **TURN relay** — Provide a TURN server for cases where peer-to-peer WebRTC is not possible (symmetric NATs).

**API surface**:

| Endpoint             | Method | Purpose                                  |
| -------------------- | ------ | ---------------------------------------- |
| `/auth/register`     | POST   | Create account                           |
| `/auth/login`        | POST   | Get JWT                                  |
| `/auth/pair`         | POST   | Generate 6-digit pairing code            |
| `/auth/pair/confirm` | POST   | Client confirms pairing code             |
| `/ws/host`           | WS     | Host persistent connection               |
| `/ws/client`         | WS     | Client persistent connection             |
| `/sims`              | GET    | List SIMs on paired host (REST fallback) |
| `/call`              | POST   | Initiate call (REST fallback)            |
| `/sms`               | POST   | Send SMS (REST fallback)                 |
| `/history`           | GET    | Call and SMS history                     |

**Tech stack**: FastAPI (Python) or Node.js, Redis (pub/sub + command queue), PostgreSQL (accounts, history), coturn (TURN server).

**Deployment**: Single VPS or container. Lightweight — primarily WebSocket relay with minimal compute.

---

### 3.3 Client App (Phone B)

**Purpose**: User-facing Android app that provides a dialer and messaging UI. All telephony operations are routed through the Relay to the Host's SIMs. No local SIM card is used.

**Screens**:

| Screen           | Description                                   |
| ---------------- | --------------------------------------------- |
| **Pairing**      | Enter pairing code or scan QR to link to Host |
| **Dashboard**    | SIM status, recent calls, recent messages     |
| **Dialer**       | Dial pad with SIM selector (SIM 1 / SIM 2)    |
| **SMS Composer** | Recipient, body, SIM selector, send button    |
| **SMS Inbox**    | Incoming messages grouped by contact          |
| **Call Log**     | Outgoing and incoming call history            |
| **Active Call**  | In-call screen with mute, speaker, hang up    |
| **Settings**     | Account, default SIM, notifications           |

**Communication model**: Persistent WebSocket to Relay. Sends commands, receives events. Falls back to REST endpoints if WebSocket is temporarily unavailable.

**Voice calls**: Uses WebRTC (`PeerConnection`) to establish an audio stream with the Host app. The Relay acts as signaling server (and TURN server when needed). Audio plays through the phone's earpiece/speaker.

**Notifications**: Incoming calls and SMS from Host trigger local notifications via a foreground service or FCM data messages.

---

## 4. Voice Call Architecture

SMS is a simple command/response exchange. Voice calls require real-time bidirectional audio, which is the most complex part of the system.

### 4.1 Call Flow

```
Client App              Relay Server            Host App                Cell Network
    │                       │                       │                       │
    ├─ MAKE_CALL ──────────►│                       │                       │
    │  {sim:1, to:"+886.."} ├─ MAKE_CALL ──────────►│                       │
    │                       │                       ├─ TelecomManager ──────►│
    │                       │                       │  .placeCall()          │
    │                       │  CALL_STATE:dialing ◄─┤                       │
    │  CALL_STATE:dialing ◄─┤                       │                       │
    │                       │                       │           connected ◄──┤
    │                       │  CALL_STATE:active ◄──┤                       │
    │  CALL_STATE:active ◄──┤                       │                       │
    │                       │                       │                       │
    │◄═══════ WebRTC audio (peer-to-peer or TURN) ═══════►│                 │
    │  mic ──► WebRTC ──► Host ──► call audio       │◄──── cell audio ──────┤
    │  spk ◄── WebRTC ◄── Host ◄── call audio       │──── cell audio ──────►│
    │                       │                       │                       │
    ├─ HANG_UP ────────────►│                       │                       │
    │                       ├─ HANG_UP ────────────►│                       │
    │                       │                       ├─ disconnect() ────────►│
    │                       │  CALL_STATE:ended ◄───┤                       │
    │  CALL_STATE:ended ◄───┤                       │                       │
```

### 4.2 Audio Bridge on Host

The Host app uses Android's `ConnectionService` API to manage the cell call and capture audio:

1. Cell call audio is captured via `AudioRecord` (call audio source).
2. Captured audio is fed into a WebRTC `PeerConnection` as a local audio track.
3. Remote audio from WebRTC (the Client's microphone) is played into the cell call via `AudioTrack`.

This creates a full-duplex audio bridge: **Client mic → WebRTC → Host → cell call → remote party** and back.

### 4.3 WebRTC Signaling

```
Client                     Relay                      Host
  │                          │                          │
  ├── SDP Offer ────────────►│── SDP Offer ────────────►│
  │                          │                          │
  │◄── SDP Answer ───────────│◄── SDP Answer ───────────┤
  │                          │                          │
  ├── ICE Candidate ────────►│── ICE Candidate ────────►│
  │◄── ICE Candidate ────────│◄── ICE Candidate ────────┤
  │                          │                          │
  │◄════════════ P2P or TURN audio stream ═════════════►│
```

---

## 5. SMS Flow

### 5.1 Outgoing SMS

```
Client App              Relay Server            Host App
    │                       │                       │
    ├─ SEND_SMS ───────────►│                       │
    │  {sim:2, to:"+886..", ├─ SEND_SMS ───────────►│
    │   body:"Hello"}       │                       ├─ SmsManager
    │                       │                       │  .sendTextMessage()
    │                       │  SMS_SENT:ok ◄────────┤
    │  SMS_SENT:ok ◄────────┤                       │
```

### 5.2 Incoming SMS

```
Host App                Relay Server            Client App
    │                       │                       │
    ├─ INCOMING_SMS ───────►│                       │
    │  {sim:1, from:"+1..", ├─ INCOMING_SMS ───────►│
    │   body:"Hi there"}    │                       ├─ Show notification
    │                       │                       │
```

---

## 6. Pairing Protocol

Pairing links a Client device to a Host device under the same account.

```
Host App                Relay Server            Client App
    │                       │                       │
    │  (logged in)          │                       │  (logged in, same account)
    │                       │                       │
    ├─ POST /auth/pair ────►│                       │
    │                       ├─ Generate code: 482916│
    │  {code: "482916"} ◄───┤                       │
    │                       │                       │
    │  Display code on      │                       │  User enters "482916"
    │  Host screen          │                       │
    │                       │◄── POST /pair/confirm ─┤
    │                       │    {code: "482916"}    │
    │                       │                       │
    │                       ├─ Validate, link devices│
    │                       │                       │
    │  PAIRED ◄─────────────┤──────────── PAIRED ──►│
```

The pairing code expires after 5 minutes. A Host can be paired with multiple Clients. A Client pairs with exactly one Host.

---

## 7. Security

| Layer            | Mechanism                                                          |
| ---------------- | ------------------------------------------------------------------ |
| Transport        | WSS (TLS 1.3) for all WebSocket connections                        |
| Authentication   | JWT tokens (access + refresh), bcrypt password hashing             |
| Device pairing   | One-time 6-digit code, expires in 5 minutes                        |
| Voice encryption | WebRTC DTLS-SRTP (encrypted by default)                            |
| SMS content      | Optional E2E encryption (NaCl/libsodium, key derived from pairing) |
| Token storage    | Android Keystore on both Host and Client                           |
| Remote revoke    | Client can unpair / revoke Host from server                        |

---

## 8. Offline and Reliability

| Scenario                 | Handling                                                                            |
| ------------------------ | ----------------------------------------------------------------------------------- |
| Host temporarily offline | Commands queued in Redis (TTL 5 min). FCM push sent to wake Host.                   |
| Host offline > 5 min     | Client shown "Host offline" status. Commands rejected with error.                   |
| Client offline           | Incoming call/SMS events queued. Delivered on reconnect.                            |
| WebSocket dropped        | Auto-reconnect with exponential backoff (1s, 2s, 4s, ... max 30s).                  |
| Server restart           | Clients and Host reconnect automatically. Queued messages in Redis survive restart. |
| Host app killed by OS    | FCM high-priority push restarts the foreground service.                             |

---

## 9. Technology Stack

| Component     | Technology               | Rationale                                        |
| ------------- | ------------------------ | ------------------------------------------------ |
| Host App      | Kotlin, Android SDK      | Native telephony API access required             |
| Client App    | Kotlin, Jetpack Compose  | Modern Android UI toolkit                        |
| Relay Server  | FastAPI (Python)         | Async WebSocket support, fast to develop         |
| Database      | PostgreSQL               | Accounts, pairing, call/SMS history              |
| Message Queue | Redis                    | Command buffering, pub/sub for WebSocket routing |
| Push          | Firebase Cloud Messaging | Wake Host when WebSocket is disconnected         |
| Voice         | WebRTC (via `libwebrtc`) | Industry standard for real-time audio            |
| TURN Server   | coturn                   | Open-source, handles NAT traversal               |
| Deployment    | Docker Compose on VPS    | Simple, single-machine deployment                |

---

## 10. Known Challenges and Risks

| Challenge                       | Impact                                                         | Mitigation                                                               |
| ------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Android background restrictions | Host app killed by OS battery optimization                     | Foreground service + FCM wakeup + user-guided whitelist                  |
| Call audio capture              | Android restricts call recording; varies by OEM                | Use `ConnectionService` API (Android 6+); test on target devices         |
| Dual SIM API fragmentation      | `SubscriptionManager` behavior differs across OEMs             | Device-specific testing; fallback to default SIM if slot selection fails |
| Voice latency                   | WebRTC relay adds 100-300ms                                    | Use STUN for P2P when possible; TURN only as fallback                    |
| Carrier restrictions            | Programmatic `placeCall()` may trigger carrier fraud detection | Rate limiting; normal usage patterns only                                |
| NAT traversal failures          | Some networks block peer-to-peer UDP                           | TURN server as mandatory fallback                                        |

---

## 11. Future Considerations

- **iOS Client App** — Client app could be ported to iOS (Host must remain Android due to telephony API requirements).
- **Multi-Host** — Support multiple Host phones per account (e.g., one for personal SIMs, one for work SIMs).
- **Call recording** — Record calls with consent, store encrypted on server.
- **USSD forwarding** — Forward USSD/operator menu interactions to Client.
- **Web Client** — Browser-based client using the same WebSocket + WebRTC protocol.
- **SMS scheduling** — Queue SMS to be sent at a specified time.

how to make it more popular to have more traffic, and how to handle big traffic

● Growing Traffic

Content & SEO

- The OG meta tags you already have are good for social sharing. Make sure each book/chapter page has unique <title> and <meta description> with the book name, author, and chapter  
  title — this is what Google indexes.
- Add a sitemap.xml (/sitemap.xml) that lists all books. Search engines need this to discover your pages. You can generate it from the books table.
- Server-side render (or prerender) book/chapter pages. Right now your SPA serves an empty <div id="q-app"> to crawlers — Google may not index the content. The OG middleware you
  have helps social crawlers, but consider extending it to serve full HTML for Googlebot too.
- Structured data (JSON-LD Book / Article schema) helps with rich search results.  


User retention

- Push notifications (web push via service worker) when followed books update new chapters.
- The reading progress sync you built is already strong for cross-device retention.
- Consider a "daily recommendation" or "trending now" section powered by your new analytics data.  


Distribution

- Share to LINE, Facebook groups, PTT (for Taiwanese audience) — your share feature already supports this.
- Build a Telegram or Discord bot that posts new chapter updates for popular books.

---

Handling Big Traffic

Your current architecture has clear bottlenecks. Here's what matters at each scale:

~100-1K concurrent users (first priority)

SQLite is the bottleneck. It allows only one writer at a time.

1. Switch the analytics DB to a separate SQLite file — isolates analytics writes from cache reads:
   ANALYTICS_DB_PATH=xsw_analytics.db # separate from xsw_cache.db
2. Move to PostgreSQL when SQLite write contention becomes noticeable. This is the single biggest scaling unlock. PostgreSQL handles concurrent reads/writes well. Your SQLAlchemy
   models port over with minimal changes (just change the connection string).
3. Add response caching at the HTTP level — most chapter content is immutable. Add Cache-Control: public, max-age=86400 headers to chapter content responses. This lets browsers and
   CDNs cache without hitting your server at all.

~1K-10K concurrent users

4. Put a CDN (Cloudflare free tier) in front — caches static assets and cacheable API responses at edge locations. This alone can absorb 90%+ of traffic for a read-heavy site like
   yours.
5. Run multiple backend workers — switch from single uvicorn to:
   gunicorn main_optimized:app -w 4 -k uvicorn.workers.UvicornWorker
6. This requires PostgreSQL (SQLite can't handle multiple processes writing).
7. Add Redis for the memory cache layer — replaces your in-process TTL cache so all workers share one cache. Your CacheManager already has the right abstraction; just swap the
   memory tier implementation.

~10K+ concurrent users

7. Separate read and write paths — serve chapter content from a read replica or even pre-generated static files (chapters rarely change). The scraping/writing backend can be a
   separate service.
8. Queue the scraping — right now a cache miss triggers a synchronous scrape. Under load, 100 users hitting the same uncached chapter = 100 scrapes. Add a lock so only one request
   scrapes, and others wait for the result:

# Pseudocode

lock = get_lock(f"scrape:{book_id}:{chapter_num}")
if lock.acquired:
fetch_and_cache()
else:
wait_for_cache() # poll cache until available 9. Object storage for chapter text — move chapter content to S3/R2 (Cloudflare R2 is free egress). Serve directly via CDN. Database stores only metadata.

Priority order

┌──────────┬───────────────────────────────────┬────────┬────────────┐
│ Priority │ Action │ Effort │ Impact │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 1 │ Sitemap + SSR for crawlers │ Medium │ High (SEO) │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 2 │ Cache-Control headers on chapters │ Low │ High │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 3 │ Cloudflare CDN │ Low │ High │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 4 │ PostgreSQL migration │ Medium │ High │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 5 │ Multiple workers (gunicorn) │ Low │ Medium │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 6 │ Redis shared cache │ Medium │ Medium │
├──────────┼───────────────────────────────────┼────────┼────────────┤
│ 7 │ Scrape deduplication lock │ Medium │ Medium │
└──────────┴───────────────────────────────────┴────────┴────────────┘

The honest answer: for a novel reading site, CDN + cache headers + SEO will get you furthest. Most of your content is static text that changes rarely — the infrastructure should
reflect that. Don't over-engineer the backend until you actually see database contention in your analytics.
