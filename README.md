# 🛡️ RakshaAI — Merchant Risk Command Center
🚀 Live Demo: https://rakshaai-frontend.onrender.com

> **Stop fraud. Prevent chargebacks. Protect revenue.**

RakshaAI is an AI-powered merchant risk decisioning platform that evaluates payment transactions in real time, predicts both fraud and future chargeback risk, detects coordinated abuse patterns, and recommends the lowest-cost safe action — without turning legitimate customers away unnecessarily.

---

## 🚨 The Problem

Payment fraud is not simply a binary fraud / not-fraud problem.

A merchant has to balance multiple risks simultaneously:
- 💳 **fraudulent transactions**
- 🔄 **future chargebacks**
- 👤 **account takeover**
- 🧪 **card testing attacks**
- 🕸️ **coordinated fraud rings**
- 💰 **high-value fraudulent purchases**
- ⚠️ **false positives that reject genuine customers**

A system that only asks:

> *"Is this transaction fraudulent?"*

misses an important business question:

> *"What action should the merchant take right now, and what will that action cost?"*

- **Blocking everything suspicious** reduces fraud — but can also reject legitimate customers.
- **Allowing everything** improves conversion — but increases losses.

**RakshaAI approaches this as a risk + decision + economics problem.**

---

## 💡 The Solution

RakshaAI evaluates every transaction through a real-time risk pipeline:

```
Customer
   │
   ▼
Merchant / Payment Gateway
   │
   ▼
┌─────────────────────────────┐
│         RakshaAI            │
│                             │
│  Feature Enrichment         │
│          ↓                  │
│  Velocity Detection         │
│          ↓                  │
│  Fraud Model ──────┐        │
│                    ├──► Risk│
│  Chargeback Model ─┘        │
│          ↓                  │
│  Ring Detection             │
│          ↓                  │
│  Explainability             │
│          ↓                  │
│  Decision Engine             │
└──────────────┬──────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     ALLOW   STEP_UP   HOLD/BLOCK
       │       │        │
       └───────┼────────┘
               ▼
        Merchant System
               │
               ▼
       Risk Command Center
```

The platform provides both:

- ⚡ **Real-time decisioning**  
  Evaluate transactions and return an action immediately.

- 🧠 **AI-assisted investigation**  
  Ask natural-language questions about merchant transactions, risk decisions, trends, and money saved.

---

## 🎯 Core Decisioning

RakshaAI uses two separate ML models:

1. **Fraud Risk Model**  
   Predicts the probability that a transaction is fraudulent.

2. **Chargeback Risk Model**  
   Predicts the probability that the transaction may eventually result in a chargeback.

These signals are combined into a single business-oriented risk score:

$$\text{Risk Score} = (1 - w) \times \text{Fraud Score} + w \times \text{Chargeback Score}$$

> **Default:** $w = 0.35$

This allows the merchant's risk appetite to influence how aggressively the system responds.

---

## 💰 Risk Is Not Just Accuracy

A high-performing fraud model is not automatically a good business decision.

RakshaAI therefore estimates potential loss:

$$\text{Expected Loss} = \text{Fraud Score} \times (\text{Transaction Amount} + ₹1,500)$$

The **₹1,500** component represents the configured chargeback-related cost used by the decisioning system.

The decision engine then considers the mitigation impact of each action:

| Action | Mitigation |
| :--- | :--- |
| **ALLOW** | 0% |
| **STEP_UP** | 70% |
| **HOLD** | 100% |
| **BLOCK** | 100% |

This allows RakshaAI to optimize around:

> *"How much risk can we mitigate without unnecessarily hurting good customers?"*

---

## 🧠 Decision Engine

RakshaAI converts model predictions into operational actions:

```
                    Transaction
                         │
                         ▼
                  Risk Evaluation
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
        Low Risk      Medium Risk     High Risk
          │              │              │
          ▼              ▼              ▼
        ALLOW          STEP_UP      HOLD / BLOCK
```

The system also considers:
- merchant risk appetite
- transaction amount
- fraud probability
- chargeback probability
- velocity signals
- device activity
- card activity
- coordinated activity
- attack typology

---

## 🕸️ Fraud Ring Detection

Individual transaction scoring is not always enough.

Attackers can distribute activity across multiple cards while reusing infrastructure such as:
- devices
- IP addresses
- customer identities
- payment patterns

RakshaAI therefore calculates velocity and ring signals.

Examples include:
- **Distinct cards on device / 24h**
- **Device transaction velocity / 1h**

A concentrated cluster of payment activity can trigger additional risk treatment.

This enables RakshaAI to identify:

> *"These transactions may not be independent."*

---

## 🧨 Attack Typologies

RakshaAI's simulation and risk pipeline supports multiple attack patterns:

- 💳 **Card Testing**  
  Large numbers of low-value transactions designed to validate stolen cards.

- 👤 **Account Takeover**  
  A legitimate customer account is hijacked and used from a new device or location with unusual transaction behavior.

- 💰 **High-Value Bust-Out**  
  A suspicious customer attempts unusually large purchases to maximize fraudulent value.

- 🕸️ **Ring Risk**  
  Multiple transactions exhibit coordinated behavior across cards, devices, or other signals.

---

## 🔍 Explainable Risk

A risk score alone is not enough for a fraud analyst.

RakshaAI provides reason codes and supporting signals so analysts can understand:

> **Why was this transaction risky?**
>
> $$\downarrow$$
>
> - High transaction amount
> - New device
> - Shipping mismatch
> - Unusual velocity
> - Multiple cards on device
>
> $$\downarrow$$
>
> **Elevated fraud + chargeback risk**
>
> $$\downarrow$$
>
> **Recommended action: HOLD**

The goal is to make the system auditable and actionable, rather than a black box.

---

## 🤖 AI Analyst

RakshaAI includes an AI-powered merchant risk analyst.

Instead of manually filtering dashboards, merchants can ask questions such as:
- *"How much money did we save today?"*
- *"Why was transaction 1855 blocked?"*
- *"Show me suspicious transactions."*
- *"What happened with this customer?"*
- *"What are the biggest risk patterns we're seeing?"*
- *"Why is the blended risk score better than using only fraud probability?"*

The AI Analyst combines:

```
Merchant Data
      +
Risk Engine
      +
RAG Knowledge
      +
LLM
      ↓
Natural-language answer
```

### Important architectural principle

**The LLM does not make the core fraud decision.**

The deterministic risk pipeline remains responsible for:
- scoring
- decisioning
- thresholds
- expected loss
- policy enforcement

The LLM acts as an **investigation and intelligence layer** over those systems.

This makes the architecture more reliable and auditable.

---

## 🔐 SaaS Architecture

RakshaAI is designed as a multi-tenant SaaS platform.

```
                 ┌─────────────────────┐
                 │      Merchant A     │
                 └──────────┬──────────┘
                            │
                 ┌──────────▼──────────┐
                 │      RakshaAI       │
                 │                     │
                 │ Tenant Isolation    │
                 │ JWT Authentication  │
                 │ API Keys            │
                 │ Risk Engine         │
                 │ AI Analyst          │
                 └──────────┬──────────┘
                            │
                 ┌──────────▼──────────┐
                 │    PostgreSQL       │
                 └─────────────────────┘
```

Every organization operates within its own tenant boundary.

Tenant-scoped access is applied to:
- transactions
- cases
- analytics
- policies
- API keys
- webhooks
- AI conversations
- RAG data

---

## 🔑 Developer API

Merchants can integrate RakshaAI directly into their payment flow.

**Example Request:**

```http
POST /api/v1/risk/score
X-API-Key: <RAKSHA_API_KEY>
Content-Type: application/json
```

**The API returns:**

```json
{
  "transaction_id": "txn_123",
  "fraud_score": 0.91,
  "chargeback_score": 0.67,
  "risk_score": 0.826,
  "decision": "BLOCK",
  "reason_codes": [
    "HIGH_FRAUD_RISK",
    "DEVICE_VELOCITY",
    "RING_ACTIVITY"
  ],
  "model_version": "..."
}
```

API keys support:
- Sandbox / Live environments
- SHA-256 hashed storage
- one-time secret visibility
- tenant isolation
- revocation

---

## 🔔 Webhooks

RakshaAI can notify merchant systems after successful risk decisions.

Webhook security uses:
```
HMAC-SHA256
     +
X-RakshaAI-Signature
```

The platform also records webhook delivery information and supports secret rotation.

---

## 📊 Risk Command Center

The frontend provides a merchant-facing control center for:

- **Overview**
  - transaction volume
  - fraud activity
  - risk trends
  - money saved
- **Transactions**
  - transaction-level risk
  - model scores
  - decision
  - reason codes
  - customer/payment information
- **Cases**
  - analyst investigation
  - resolution
  - overrides
  - decision history
- **Analytics**
  - fraud performance
  - chargeback risk
  - risk trends
  - attack activity
- **Policy**
  - merchant risk appetite
  - decision thresholds
- **Developer**
  - API keys
  - Sandbox / Live integration
- **AI Analyst**
  - natural-language investigation
  - RAG-grounded answers
  - persistent conversations

---

## 📈 Machine Learning

RakshaAI uses XGBoost classification models for fraud and chargeback prediction.

### Training approach

The models use a temporal train/test split rather than randomly mixing historical events.

```
Historical Transactions
          │
          ▼
    Feature Engineering
          │
          ▼
 ┌─────────────────────┐
 │ Temporal Split      │
 │                     │
 │ 80% → Training      │
 │ 20% → Holdout       │
 └─────────────────────┘
          │
          ▼
      XGBoost Models
          │
          ▼
       Evaluation
```

### Holdout performance

#### Fraud Model
| Metric | Result |
| :--- | :--- |
| **Precision** | 95.5% |
| **Recall** | 92.6% |
| **PR-AUC** | 0.947 |
| **ROC-AUC** | 0.966 |

#### Chargeback Model
| Metric | Result |
| :--- | :--- |
| **Precision** | 48.8% |
| **Recall** | 96.9% |

The chargeback model intentionally prioritizes **high recall** because missing a genuinely risky transaction can carry significant downstream cost.

---

## 🔬 Explainability

RakshaAI uses exact tree-based contribution analysis for the XGBoost models.

This enables the system to connect model output with interpretable contributing features.

The resulting signals feed the reason-code layer used by analysts and the dashboard.

---

## 🧱 Technology Stack

### Frontend
- React
- Vite
- JavaScript
- React Markdown
- REST API integration

### Backend
- Python
- FastAPI
- SQLAlchemy
- JWT authentication
- bcrypt password hashing

### Machine Learning
- XGBoost
- scikit-learn
- SHAP-style tree contributions
- shared feature engineering pipeline

### AI
- Groq
- RAG
- vector embeddings
- retrieval-based grounding

### Database
- PostgreSQL for production
- SQLite for local development

### Security
- JWT authentication
- tenant isolation
- SHA-256 API-key hashing
- HMAC-SHA256 webhook signatures
- encrypted webhook secrets
- CORS configuration
- production secret enforcement

---

## 🏗️ Project Structure

```
RakshaAi/
│
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── config.py
│   │   └── main.py
│   │
│   ├── ml/
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── lib/
│   │   └── App.jsx
│   │
│   └── package.json
│
├── README.md
└── .gitignore
```

---

## 🚀 Run Locally

### 1. Clone
```bash
git clone https://github.com/SudikshA-0/RakshaAi.git
cd RakshaAi
```

### 2. Backend
```bash
cd backend

python -m venv venv
```

**Windows:**
```powershell
venv\Scripts\activate
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Environment variables:**

Create `backend/.env`:

```env
RAKSHAII_SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///./rakshaai.db

GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b

ENVIRONMENT=development
CORS_ORIGINS=http://localhost:5173
```

> ⚠️ *Never commit `.env` files or API keys.*

**Start API:**
```bash
python -m uvicorn app.main:app --reload --port 8000
```

- **Backend:** `http://localhost:8000`
- **API documentation:** `http://localhost:8000/docs`

### 3. Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

- **Frontend:** `http://localhost:5173`

---

## 🧪 Testing

RakshaAI includes automated backend coverage across:
- authentication
- tenant isolation
- transaction APIs
- cases
- analytics
- API keys
- public risk scoring
- webhooks
- RAG
- AI Analyst
- Groq integration
- persistent conversations
- money-saved calculations
- transaction investigation

### Current validation:
- **Backend Tests:** `42/42 PASS`
- **Frontend Build:** `PASS`

---

## 🔒 Security Design

Security was treated as a core SaaS requirement rather than a final-stage addition.

- **Authentication**  
  JWT-based authentication with password hashing.

- **API Keys**  
  Raw API secrets are not persisted. Only hashed credentials are stored.

- **Tenant Isolation**  
  Database queries enforce organization ownership.

- **Webhooks**  
  HMAC-SHA256 signatures protect webhook authenticity.

- **Secrets**  
  Production deployments require explicit secret configuration.

- **Frontend**  
  LLM and backend secrets are never exposed to the React client.

---

## 💵 Measuring Business Impact

RakshaAI tracks money saved / loss prevented, rather than presenting model accuracy as the only business metric.

The calculation uses the same canonical loss-prevention logic throughout:

$$\text{Prevented Loss} = (\text{Fraud Transaction Amount} + \text{Chargeback Cost}) \times \text{Action Mitigation}$$

This allows the dashboard to answer a business-critical question:

> *"How much money did our risk system actually protect?"*

---

## 🧪 Sandbox & Threat Testing

RakshaAI includes a transaction simulator for testing risk behavior.

It can generate controlled scenarios such as:

```
Normal Payment
      │
      ├── Card Testing
      │
      ├── Account Takeover
      │
      ├── High-Value Bust-Out
      │
      └── Coordinated Ring Activity
```

This allows merchants and developers to observe how the risk engine responds before integrating real payment traffic.

---

## 🏆 Why RakshaAI?

Traditional fraud systems often optimize for:
- *Fraud detection accuracy*

RakshaAI expands the objective:
- **Risk detection + chargeback prediction + coordinated abuse detection + explainability + economic decisioning**

The result is a system designed around the merchant's actual objective:

> **Protect revenue while preserving legitimate payment conversion.**

---

## 🛣️ Roadmap

### Current
- [x] Real-time transaction scoring
- [x] Fraud model
- [x] Chargeback model
- [x] Blended risk score
- [x] Risk decision engine
- [x] Explainable reason codes
- [x] Ring detection
- [x] Merchant risk appetite
- [x] Cases and analyst overrides
- [x] Money-saved analytics
- [x] Multi-tenant SaaS architecture
- [x] JWT authentication
- [x] Tenant-scoped API keys
- [x] Public risk scoring API
- [x] Webhooks
- [x] RAG
- [x] AI Analyst
- [x] Persistent AI conversations
- [x] Groq integration
- [x] PostgreSQL production support

### Next
- [ ] Production cloud deployment
- [ ] Production monitoring
- [ ] Usage-based billing
- [ ] Advanced fraud graph
- [ ] More real-world payment signals
- [ ] Automated policy optimization
- [ ] Advanced merchant-level risk analytics

---

## 🎥 Buildathon Demo Flow

A recommended demonstration:

```
01 → Merchant Dashboard
       ↓
02 → Normal transaction → ALLOW
       ↓
03 → Card-testing attack → BLOCK
       ↓
04 → Show ring detection
       ↓
05 → Account takeover scenario
       ↓
06 → Explain why risk increased
       ↓
07 → Show Money Saved
       ↓
08 → Ask AI Analyst:
       "How much money did we save today?"
       ↓
09 → Show Developer API
       ↓
10 → Show webhook integration
```

The important story is not:
> *"Look at our dashboard."*

It is:
> **"RakshaAI observes payment risk, understands what is happening, chooses the safest economic action, explains that decision, and gives the merchant control."**

---

## ⚡ Razorpay Buildathon

RakshaAI is built around a payment-risk problem directly relevant to modern payment infrastructure:

> *How can payment platforms help merchants reduce fraud and chargeback losses without unnecessarily blocking legitimate customers?*

The project explores this through:
- real-time payment risk scoring
- fraud + chargeback prediction
- transaction-level decisioning
- coordinated abuse detection
- explainable AI
- merchant-specific risk policies
- API-first integration
- webhook-driven workflows
- merchant intelligence through an AI Analyst

---

## 👨‍💻 Project

**RakshaAI — Merchant Risk Command Center**  
*Built for the Razorpay Buildathon 2026.*

**Repository:** [github.com/SudikshA-0/RakshaAi](https://github.com/SudikshA-0/RakshaAi)
