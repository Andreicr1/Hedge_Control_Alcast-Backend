# Institutional realistic seeding

This project already includes baseline seed scripts (e.g. users and LME prices). This script adds a **high-volume, coherent** dataset designed to make:
- Deals / SO / PO trees non-empty
- Exposures (open/partial/hedged/closed) realistic
- Timeline populated with key events
- Workflow Inbox non-empty
- Cashflow / P&L screens meaningful (requires LME prices; this script ensures them)

## Run

From `Hedge_Control_Alcast-Backend/backend`:

```bash
python scripts/seed_realistic_data.py --company all --reset
```

Common options:

```bash
python scripts/seed_realistic_data.py --company alcast_trading --scale 1.0 --reset
python scripts/seed_realistic_data.py --company alcast_brasil --scale 1.2 --reset
python scripts/seed_realistic_data.py --company all --force
```

## Notes on multi-company separation

The current schema doesn’t expose a first-class `company_id` tenant field in the core domain models.

To keep datasets separated and resettable, this seeder uses deterministic prefixes:
- Deals: `AT • ...` / `AB • ...`
- Customers/Suppliers codes: `AT-CUST-...`, `AB-SUP-...`
- Orders: `AT-SO-...`, `AB-PO-...`
- RFQs: `AT-RFQ-...`
- Contracts: `AT-CT-...`

Once a real company/tenant dimension exists, this seeder should be updated to write that field and filter by it instead of prefixes.
