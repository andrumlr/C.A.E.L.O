# backend/README.md

## Step 4 — Backend Responsibilities

---

# Backend Role

The backend is the intelligence orchestration layer.

It is responsible for:

* loading Caelo’s identity and behavior files
* selecting mode
* retrieving relevant memory
* building prompts
* calling the model provider
* storing conversations and memory results
* enforcing local-first and permission rules

---

# Required Backend Modules

* config
* api
* core
* db
* prompts
* memory
* providers
* services

---

# First Endpoints

* POST /chat
* GET /conversations
* GET /conversations/{id}
* GET /memory
* GET /settings
* POST /settings

---

# First Internal Services

* mode_selector
* prompt_builder
* memory_manager
* provider_router
* conversation_service

---

## END OF FILE
