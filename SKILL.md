---
name: vouch
description: Connect to your Vouch shopping agent for personalized beauty recommendations, trust network queries, and product reviews
requirements: []
---

# Vouch Shopping Agent

Vouch is a trust-first beauty shopping platform. Each user has a personal AI agent that remembers their taste, consults their trusted friends' reviews, and makes personalized recommendations.

## When to use this skill

Use this skill when the user asks about:
- Product recommendations (skincare, makeup, haircare, fragrance)
- What their trusted friends think about a product
- Logging a purchase or leaving a review
- Managing their wishlist

## Authentication (OAuth 2.0)

Before using Vouch, authenticate the user:

1. **Direct the user to the Vouch authorization page:**
   ```
   https://vouch-backend-392847826435.us-central1.run.app/oauth/authorize
     ?client_id=openclaw
     &redirect_uri=https://app.openclaw.ai/oauth/callback
     &response_type=code
     &state={RANDOM_STATE}
   ```
   The user will log in with their Vouch credentials and click Allow.

2. **Exchange the code for a token** (after redirect back with `?code=...`):
   ```
   POST https://vouch-backend-392847826435.us-central1.run.app/api/oauth/token
   Content-Type: application/json

   {
     "grant_type": "authorization_code",
     "code": "{CODE}",
     "client_id": "openclaw",
     "client_secret": "openclaw-secret",
     "redirect_uri": "https://app.openclaw.ai/oauth/callback"
   }
   ```
   Response: `{ "access_token": "...", "token_type": "bearer", "agent_id": "..." }`

3. **Store both `access_token` and `agent_id`** — you need the `agent_id` for all subsequent calls.

## Sending a message to the agent

```
POST https://vouch-backend-392847826435.us-central1.run.app/api/a2a/agents/{agent_id}/message/send
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "message": {
    "role": "user",
    "parts": [{ "kind": "text", "text": "Find me a good SPF moisturiser" }],
    "messageId": "{UNIQUE_ID}"
  }
}
```

Response:
```json
{
  "id": "task-...",
  "contextId": "ctx-...",
  "status": {
    "state": "completed",
    "message": {
      "role": "agent",
      "parts": [{ "kind": "text", "text": "Based on your preference for lightweight formulas..." }]
    }
  }
}
```

Extract the response from `status.message.parts[0].text`.

## Verify identity

To confirm which Vouch agent is connected:
```
GET https://vouch-backend-392847826435.us-central1.run.app/api/oauth/me
Authorization: Bearer {access_token}
```
Returns: `{ "agent_id": "...", "user_id": "...", "name": "Alice" }`

## Agent Card

The full A2A agent card is available at:
```
GET https://vouch-backend-392847826435.us-central1.run.app/.well-known/a2a-agent-card.json
```

## Example interactions

- "Find me a foundation for oily skin" → product recommendation using taste memory
- "What do my friends think about micellar water?" → trust network query
- "I just bought the Rare Beauty blush and loved it, 5 stars" → logs review, updates trust weights
- "Add the CeraVe cleanser to my wishlist" → wishlist management
