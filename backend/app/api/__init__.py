from .routes_intake        import router as intake_router
from .routes_carriers      import router as carriers_router
from .routes_fleet         import router as fleet_router, public_router as fleet_public_router
from .routes_telemetry     import router as telemetry_router
from .routes_leads         import router as leads_router
from .routes_dashboard     import router as dashboard_router
from .routes_founders      import router as founders_router
from .routes_agents        import router as agents_router
from .routes_bond          import router as bond_router
from .routes_webhooks           import router as webhooks_router
from .routes_bland_webhooks     import router as bland_webhooks_router
from .routes_prospecting        import router as prospecting_router
from .routes_triggers      import router as triggers_router
from .routes_comms         import router as comms_public_router, router_auth as comms_router
from .routes_driver_auth   import router as driver_auth_router
from .routes_driver        import router as driver_router
from .routes_payout        import router as payout_router
from .routes_notifications import router as notifications_router
from .routes_health        import router as health_router
from .routes_executives    import router as executives_router
from .routes_email         import router as email_router
from .routes_migration     import router as migration_router
from .routes_adobe_webhooks import router as adobe_webhooks_router
from .routes_adobe_intake   import router as adobe_intake_router
from .routes_dat           import router as dat_router
from .routes_fmcsa         import router as fmcsa_router
from .routes_memory        import router as memory_router
from .routes_carrier_brain import router as carrier_brain_router
from .routes_revenue_brain import router as revenue_brain_router
from .routes_mailboxes     import router as mailboxes_router
from .routes_agreements    import router as agreements_router
from .routes_rate_confirmation import router as rate_confirmation_router
from .routes_settlements   import router as settlements_router
from .routes_shippers      import router as shippers_router
from .routes_ifta          import router as ifta_router

from ..clm             import clm_router
from ..email_ingest    import router as email_ingest_router
from ..execution_engine import execution_router
from ..atomic_ledger   import atomic_ledger_router
from ..compliance      import compliance_router
from ..studio          import studio_router

__all__ = [
    "intake_router",
    "carriers_router",
    "fleet_router",
    "fleet_public_router",
    "telemetry_router",
    "leads_router",
    "dashboard_router",
    "founders_router",
    "agents_router",
    "bond_router",
    "webhooks_router",
    "bland_webhooks_router",
    "prospecting_router",
    "triggers_router",
    "comms_router",
    "comms_public_router",
    "driver_auth_router",
    "driver_router",
    "payout_router",
    "notifications_router",
    "email_router",
    "email_ingest_router",
    "migration_router",
    "adobe_webhooks_router",
    "adobe_intake_router",
    "clm_router",
    "execution_router",
    "atomic_ledger_router",
    "compliance_router",
    "health_router",
    "executives_router",
    "dat_router",
    "fmcsa_router",
    "memory_router",
    "carrier_brain_router",
    "revenue_brain_router",
    "mailboxes_router",
    "agreements_router",
    "rate_confirmation_router",
    "settlements_router",
    "shippers_router",
    "ifta_router",
    "studio_router",
]
