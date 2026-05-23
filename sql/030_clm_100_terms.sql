-- ─────────────────────────────────────────────────────────────────────────────
-- 030 · CLM 100-Term Schema — expanded contract metadata columns
--
-- Adds first-class columns for the most operationally critical of the 100
-- master metadata terms. The full 100-term payload is always available in
-- contracts.extracted_vars (JSONB). These columns enable fast indexed queries
-- on the highest-value fields without JSON parsing.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── New contract_type values ──────────────────────────────────────────────────
-- The contracts table uses a text column for contract_type; no enum change needed.
-- Supported values now include all 20 CON classes:
--   rate_confirmation, dedicated_lane_agreement, master_service_agreement,
--   broker_carrier_agreement, shipper_carrier_agreement, owner_operator_lease,
--   freight_brokerage_terms, co_brokerage_agreement, fuel_surcharge_addendum,
--   hazmat_transport_rider, cross_border_agreement, intermodal_agreement,
--   tpl_contract, warehouse_bailment, trailer_interchange_agreement,
--   freight_forwarding_agreement, yard_management_contract, logistics_tech_saas,
--   cargo_claim_settlement, nemt_contract, bol, pod, invoice

-- ── Temporal terms (Category 2) ──────────────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS execution_date          date;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS effective_date          date;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS auto_renewal_notice_days  integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS termination_for_convenience_days integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS claims_filing_time_bar_days      integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS overcharge_dispute_window_days   integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS spot_quote_validity_period       text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS rate_amendment_frequency_cap     text;

-- ── Rate & financial terms (Category 3) ──────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS base_linehaul_rate       numeric(12,4);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS fsc_matrix               jsonb;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS detention_rate_per_hour  numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS layover_fee              numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS multi_stop_drop_premium  numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS congestion_surcharge      numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS hazmat_premium            numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS liftgate_service_fee      numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS high_value_cargo_surcharge numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS reconsignment_fee         numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS quick_pay_discount_rate   numeric(6,4);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS late_payment_penalty_rate numeric(6,4);

-- ── Operational dispatch (Category 4) ────────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS free_time_pickup_hours            numeric(5,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS free_time_delivery_hours          numeric(5,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS min_tender_acceptance_rate_pct    numeric(5,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS spot_tendering_response_window_min integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS dedicated_equipment_quota          integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS eld_data_sharing_consent           boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS tracking_ping_frequency_min        integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS max_continuous_driving_hours       numeric(4,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS cross_docking_permissible          boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS drop_and_hook_consent              boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS blind_shipment_protection          boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS intermodal_authorization           boolean;

-- ── Liability & insurance (Category 5) ───────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS cargo_liability_cap               numeric(14,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS cgl_limit                         numeric(14,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS auto_liability_limit              numeric(14,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS workers_comp_mandate              boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS temperature_deviation_threshold   text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pre_cooling_verification          boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS slc_indicator                     boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS seal_integrity_protocol           text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS broken_seal_liability_presumption boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS waiver_of_subrogation             boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS indemnification_scope             text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pollution_liability_rider         numeric(14,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS trailer_interchange_cap           numeric(14,2);

-- ── SLAs & compliance (Category 6) ───────────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS otd_target_pct                    numeric(5,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS otp_target_pct                    numeric(5,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS service_level_failure_fine        numeric(10,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS consecutive_rejection_default_trigger integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS fmcsa_safety_rating_mandate       text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS driver_background_check_required  boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS drug_alcohol_clearinghouse_compliance boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS carb_compliance_required          boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ctpat_certification_required      boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS fsma_mandate                      boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS equipment_age_ceiling_years       integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS incident_notification_sla_min     integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS qbr_requirement                   boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS cap_response_window_days          integer;

-- ── Governance & legal (Category 7) ──────────────────────────────────────────
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS governing_law_jurisdiction        text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS dispute_resolution_forum          text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS mandatory_arbitration             boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS mediation_prerequisite_days       integer;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS prevailing_party_fee_shifting     boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS confidentiality_scope             text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS non_solicitation_window           text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS back_solicitation_liquidated_damages numeric(14,2);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS severability_clause               boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS assignment_restrictions           boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS esign_binding_consent             boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS api_edi_standards                 text;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS entirety_of_agreement             boolean;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS sovereign_immunity_waiver         boolean;

-- ── Performance indexes ───────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_contracts_effective_date   ON contracts (effective_date)  WHERE effective_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_execution_date   ON contracts (execution_date)  WHERE execution_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_otd_target       ON contracts (otd_target_pct)  WHERE otd_target_pct IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_cargo_liability  ON contracts (cargo_liability_cap) WHERE cargo_liability_cap IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_fsc_matrix       ON contracts USING gin (fsc_matrix) WHERE fsc_matrix IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contracts_gov_law          ON contracts (governing_law_jurisdiction) WHERE governing_law_jurisdiction IS NOT NULL;
