# CS2 Data Export schema 2.11 — proposal

Status: **implemented** in CitiesAI 0.6 (vendored mod schema `2.11.0`). Healthcare/fire/police coverage fields remain optional until ECS probes land.

## Goals

Answer the two most common player questions CitiesAI still inferred instead of reading from ECS:

1. **Why is residential / commercial / industrial demand weak?** (RCI demand factors)
2. **Why are utilities or services failing?** (electricity, garbage, healthcare beds, etc.)

## Groups

### `demand_factors_semantics` (priority 1)

| Field | Type | Source |
|-------|------|--------|
| `residential_demand` | 0..1 | `ResidentialDemandSystem.householdDemand` normalized |
| `commercial_demand` | 0..1 | `CommercialDemandSystem.companyDemand` normalized |
| `industrial_demand` | 0..1 | `IndustrialDemandSystem.industrialCompanyDemand` normalized |
| `residential_factors` | object | medium-density factor array |
| `commercial_factors` | object | `GetDemandFactors` |
| `industrial_factors` | object | `GetIndustrialDemandFactors` |

**CitiesAI:** `analyze_demand_factors()`, issue `city_demand_weak`, Insights RCI card, Ask/MCP `get_demand_factors`.

### `utilities_services_semantics` (priority 2)

| Field | Type | Notes |
|-------|------|-------|
| `electricity_production` | number | `ElectricityStatisticsSystem.production` |
| `electricity_consumption` | number | |
| `electricity_capacity` | number | production + battery capacity when present |
| `garbage_accumulation` | number | `GarbageAccumulationSystem.garbageAccumulation` |
| `garbage_processing` | number | deferred |
| `healthcare_beds_total` | number | deferred |
| `healthcare_beds_used` | number | deferred |
| `fire_coverage_percent` | number | deferred |
| `police_coverage_percent` | number | deferred |

`utility_pressure_semantics.electricity` is also populated from `ElectricityStatisticsSystem` in 2.11.

**CitiesAI:** `analyze_utilities_services()`, dashboard **Power fulfillment** metric, Issues for blackout/garbage, Ask/MCP `get_utilities_services`.

## Risk

- Demand factor enum names may differ per game patch; unknown indices export as `factor_N`.
- District-level breakdown deferred to a future schema.
