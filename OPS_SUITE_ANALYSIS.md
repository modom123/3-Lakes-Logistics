# 3 Lakes Logistics — Ops Suite (Command Center) Analysis

## Current State: 60% Built

The **backend infrastructure** is ~70% complete, but the **command center UI** doesn't exist yet. Here's what you have and what you need.

---

## 🎯 Vision: What You Want

A **single dashboard** where you can:

### **1. Carriers & Fleet**
- 🚛 View all carriers (active, suspended, churned)
- ✅ Pull up any carrier by ID or name
- 📊 See fleet status (how many trucks, condition, location)
- 📍 Real-time GPS location of trucks
- 🔧 Maintenance status
- ⚙️ Equipment details (VIN, year, make, model)

### **2. Operations**
- 🚗 Check that all trucks are running ("healthy" status)
- 📡 Verify automations (ELD sync, GPS, HOS compliance)
- ⚡ Active vs idle trucks
- 🚨 Alerts for out-of-service units
- 📋 Load assignments per truck

### **3. Financial**
- 💰 Money In: Revenue by carrier, by load, by month
- 💸 Money Out: Dispatch fees, insurance, payouts
- 📊 Profit margins by carrier
- 🧾 Invoicing status (paid, unpaid, overdue)
- 💳 Payment terms tracking

### **4. Business Intelligence**
- 📈 KPIs: MTD loads, MTD gross, avg $/mile, fleet utilization
- 🎯 Performance: Which carriers are most profitable
- 📊 Trends: Revenue growth, utilization rates
- ⚠️ Alerts: Compliance issues, failed automations, unpaid invoices

---

## ✅ What's Already Built (Backend)

### **Database Tables** (9 core tables)

| Table | Purpose | Data |
|-------|---------|------|
| `active_carriers` | Master carrier list | Company, DOT, MC, plan, status, stripe billing |
| `fleet_assets` | Trucks & trailers | VIN, make, model, trailer type, weight, status |
| `truck_telemetry` | Live GPS + ELD data | Location, speed, heading, fuel, odometer, engine hours |
| `eld_connections` | ELD provider links | Motive, Samsara, Geotab, Omnitracs API tokens |
| `insurance_compliance` | Compliance status | Insurance, policy #, expiry, COI, CSA flags |
| `banking_accounts` | Payment info | Routing #, account #, Stripe tokens |
| `loads` | Dispatch records | Broker, origin/dest, rate, status, assigned carrier |
| `invoices` | Billing records | Amount, status (paid/unpaid), due date |
| `driver_hos_status` | HOS compliance | Hours logged, available hours, violations |

### **API Endpoints** (existing)

**Carriers:**
- `GET /api/carriers/` — List all carriers (with filtering)
- `GET /api/carriers/{id}` — Get carrier detail
- `PATCH /api/carriers/{id}/status` — Update status

**Fleet:**
- `GET /api/fleet/` — List all trucks (by carrier or status)
- `GET /api/fleet/{id}` — Get truck detail
- `PATCH /api/fleet/{id}/status` — Update truck status

**Dashboard:**
- `GET /api/dashboard/kpis` — KPIs (carriers, loads, revenue, unpaid)
- `GET /api/dashboard/recent-loads` — Recent dispatch records

**Telemetry:**
- `GET /api/telemetry/` — GPS + ELD data for trucks

---

## ❌ What's Missing (Frontend)

### **No UI/Dashboard Exists**
There is **no web interface** for the command center. You have:
- ✅ Database with all the data
- ✅ APIs to fetch the data
- ❌ **No visual dashboard to see it**

### **Missing Command Center Pages**

| Page | Purpose | Status |
|------|---------|--------|
| **Home/Dashboard** | KPIs, alerts, quick stats | ❌ Not built |
| **Carriers** | List, search, drill-down, status change | ❌ Not built |
| **Fleet** | Trucks, real-time location, status | ❌ Not built |
| **Loads/Dispatch** | Active loads, assignments, status | ❌ Not built |
| **Financials** | Revenue, invoices, margins, payouts | ❌ Not built |
| **Compliance** | Insurance, HOS, automations, alerts | ❌ Not built |
| **Analytics** | Trends, performance metrics, reports | ❌ Not built |

### **Missing Data Points** (Need DB additions)

Some fields exist in the DB but aren't fully captured:

- ✅ Last load assigned to truck
- ✅ Current status (available/on-load/maintenance)
- ⚠️ **MISSING:** Automation health indicators (is ELD sync running?)
- ⚠️ **MISSING:** Automation failure alerts
- ⚠️ **MISSING:** Performance metrics per carrier (loads/month, utilization %)
- ⚠️ **MISSING:** Invoice aging (how long overdue)
- ⚠️ **MISSING:** HOS violations flagged in real-time

---

## 📊 Example: What the Dashboard Would Show

### **Dashboard Home**
```
┌─────────────────────────────────────────────────────┐
│ 3 LAKES LOGISTICS — COMMAND CENTER                  │
│ May 10, 2026 — 2:34 PM                              │
├─────────────────────────────────────────────────────┤
│ QUICK STATS                                          │
│ ┌────────┬──────────┬─────────┬────────┐            │
│ │ 42     │ 38       │ 127     │ $48.2K │            │
│ │ Trucks │ On Load  │ Loads   │ MTD $  │            │
│ └────────┴──────────┴─────────┴────────┘            │
│                                                      │
│ ACTIVE TRUCKS                                        │
│ ├─ Truck #001 (Peterbilt) ................................. ON LOAD
│ ├─ Truck #002 (Peterbilt) ................................. AVAILABLE
│ ├─ Truck #003 (International) ........................... MAINTENANCE
│ └─ Truck #004 (Kenworth) .................................. WAITING
│                                                      │
│ ALERTS (3 issues)                                    │
│ ⚠️  ELD Sync Failed — Carrier ABC Transport (4hrs)
│ 🟡 Invoice Overdue — $2,500 from Freight Co
│ 🔴 HOS Violation — Driver TX-45 (reset needed)
│                                                      │
│ RECENT LOADS                                         │
│ LA → Chicago | $2,500 | Truck #001 | DELIVERED    │
│ TX → NY | $1,800 | Truck #004 | IN TRANSIT         │
└─────────────────────────────────────────────────────┘
```

### **Carrier Detail Page**
```
┌──────────────────────────────────────────────┐
│ SUNSHINE FREIGHT CORP                         │
│ DOT: 123456 | MC: 456789 | Founded: 2015    │
├──────────────────────────────────────────────┤
│ Status: ACTIVE | Plan: FULL SERVICE          │
│ Trucks: 8 | Available: 5 | On Load: 3       │
│                                              │
│ FLEET                                        │
│ ├─ Truck #101 (Peterbilt 579) — ON LOAD    │
│ │  Load: LA → Chicago, $2,500, ETA 6hrs    │
│ │  Location: 🔴 I-40, TX (35.1°N, 101.2°W) │
│ │  Status: Running, Fuel: 78%, Rpm: 1500   │
│ │                                            │
│ ├─ Truck #102 (Kenworth T680) — AVAILABLE  │
│ │  Location: 🟢 Terminal (Dallas)           │
│ │  Status: Idle, Fuel: 95%                  │
│ │                                            │
│ └─ Truck #103 (Volvo) — MAINTENANCE        │
│    Issue: Brake inspection overdue          │
│                                              │
│ COMPLIANCE                                   │
│ ✅ Insurance: Current (expires Dec 2026)   │
│ ✅ HOS: Compliant                           │
│ ✅ ELD: Syncing (last: 2 min ago)          │
│                                              │
│ FINANCIALS (MTD)                             │
│ Revenue: $18,500 | Loads: 7 | Avg $/mi: 2.1│
│ Dispatcher Fee: $1,850 | Payout: $16,650   │
│ Invoiced: $18,500 | Paid: $16,500 | Due: $2K
└──────────────────────────────────────────────┘
```

---

## 🛠️ What Needs to Be Built

### **Priority 1: Core Dashboard (Week 1-2)**
Build the main command center with:
- [ ] Home page with KPI tiles
- [ ] Carrier list + search
- [ ] Fleet status grid
- [ ] Real-time truck locations (map)
- [ ] Alert panel

**Tech Stack:**
- React or Vue (modern SPA)
- Tailwind CSS (styling)
- TanStack Query (data fetching from existing APIs)
- Recharts or Chart.js (charts for KPIs)

### **Priority 2: Drill-Down Pages (Week 2-3)**
- [ ] Carrier detail page (profile + fleet + financials)
- [ ] Truck detail page (specs + location history + load history)
- [ ] Load detail page (broker, driver, route, status)
- [ ] Invoice list + detail (payment tracking)

### **Priority 3: Financial Dashboard (Week 3-4)**
- [ ] Revenue tracking (by carrier, by month)
- [ ] Invoice aging (overdue alerts)
- [ ] Dispatch fee calculations
- [ ] Profit margin analysis

### **Priority 4: Automation Monitoring (Week 4-5)**
- [ ] ELD sync status per carrier
- [ ] GPS tracking health
- [ ] HOS compliance monitoring
- [ ] Automation failure alerts

### **Priority 5: Analytics & Reporting (Week 5-6)**
- [ ] Performance trends
- [ ] Utilization rates
- [ ] Carrier comparison
- [ ] Export reports (PDF, CSV)

---

## 💾 Database Additions Needed

Small additions to enhance the command center:

```sql
-- Add to truck_telemetry tracking
ALTER TABLE truck_telemetry ADD COLUMN
  eld_sync_status TEXT DEFAULT 'syncing',  -- syncing | ok | failed | outdated
  eld_sync_last_success TIMESTAMPTZ,
  eld_sync_error TEXT;

-- Add to fleet_assets for tracking
ALTER TABLE fleet_assets ADD COLUMN
  current_load_id UUID REFERENCES loads(id),
  last_completed_load_at TIMESTAMPTZ,
  health_status TEXT DEFAULT 'healthy',  -- healthy | warning | alert
  automation_errors JSONB DEFAULT '[]';

-- Add to invoices for aging
ALTER TABLE invoices ADD COLUMN
  days_overdue INT GENERATED ALWAYS AS (
    CASE WHEN status = 'Unpaid' 
      THEN (CURRENT_DATE - due_date)::int 
      ELSE 0 
    END
  ) STORED;

-- New: Automation health log
CREATE TABLE automation_health (
  id UUID PRIMARY KEY,
  carrier_id UUID REFERENCES active_carriers(id),
  automation_type TEXT,  -- eld_sync, gps_tracking, hos_check
  status TEXT,  -- ok | warning | failed
  last_check TIMESTAMPTZ,
  error_message TEXT
);
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│ Command Center Dashboard (React/Vue)            │
│ ─────────────────────────────────────────────── │
│ Components:                                     │
│ • KPI Dashboard                                 │
│ • Carrier Management                            │
│ • Fleet Monitor (map + grid)                    │
│ • Financials & Invoicing                        │
│ • Automation Status                             │
│ • Analytics & Reports                           │
└────────────────┬────────────────────────────────┘
                 │ (API calls)
┌────────────────▼────────────────────────────────┐
│ FastAPI Backend (existing)                      │
│ ─────────────────────────────────────────────── │
│ Routes:                                         │
│ • /api/carriers/                                │
│ • /api/fleet/                                   │
│ • /api/dashboard/                               │
│ • /api/telemetry/                               │
│ • /api/invoices/  (need to build)               │
│ • /api/automations/  (need to build)            │
└────────────────┬────────────────────────────────┘
                 │ (Supabase queries)
┌────────────────▼────────────────────────────────┐
│ Supabase Database (PostgreSQL)                  │
│ ─────────────────────────────────────────────── │
│ Tables:                                         │
│ ✅ active_carriers                              │
│ ✅ fleet_assets                                 │
│ ✅ truck_telemetry                              │
│ ✅ loads                                        │
│ ✅ invoices                                     │
│ ✅ eld_connections                              │
│ ✅ insurance_compliance                         │
│ ⚠️  automation_health (needs creation)           │
└─────────────────────────────────────────────────┘
```

---

## 📈 What This Enables

Once built, your ops suite will let you:

✅ **Instant Visibility**
- Pull up any carrier/truck in seconds
- See real-time location of fleet
- Know which trucks are idle vs active

✅ **Operational Control**
- Monitor all automation health
- Get alerts when systems fail
- Change truck status on demand

✅ **Financial Intelligence**
- Know exact revenue per carrier
- Track unpaid invoices
- Calculate dispatcher margins
- Forecast cash flow

✅ **Business Decisions**
- Which carriers are most profitable
- Whether to add more trucks
- Which loads to prioritize
- Growth opportunities

---

## 🚀 Next Steps

### **Option A: I Build It** (Recommended)
Let me build the React dashboard + missing APIs + database additions
- Estimated time: 4-5 weeks (1 page per week)
- Result: Full-featured command center

### **Option B: You Customize Existing Tools**
Use your current data with:
- Metabase (open-source BI tool) → connect to Supabase
- Superset (data visualization) → charts + dashboards
- Looker Studio → Google Sheets integration
- Result: Basic dashboard in days, not weeks

### **Option C: Hybrid**
I build core UI, you integrate with your preferred BI tool for advanced analytics

---

## Summary

**Your ops suite BACKEND is 70% done.**
- All the data is there
- All the APIs exist
- Just missing the **visual interface**

**You need a command center UI** to:
- See what's happening in your business
- Make decisions based on real data
- Monitor automations
- Track finances

Would you like me to start building the React command center dashboard?

---

**Last Updated:** 2026-05-10
