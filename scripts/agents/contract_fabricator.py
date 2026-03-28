"""
ContractFabricator agent — creates suppliers, contracts, rate cards, and guidelines.
Uses Claude (haiku) for names and narrative text; rates and rules are deterministic.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from scripts.agents.base import (
    DOMAIN_CODES,
    SUPPLIER_DOMAIN_PLAN,
    BaseAgent,
    ContractSpec,
    GuidelineSpec,
    RateCardSpec,
    RunContext,
    SupplierSpec,
    pick_rate,
)
from app.models.supplier import Contract, GeographyScope, Guideline, RateCard, Supplier

logger = logging.getLogger(__name__)


class ContractFabricator(BaseAgent):
    """Agent 1: Creates suppliers, contracts, rate cards, and guidelines."""

    def run(self) -> None:
        logger.info("ContractFabricator starting (dry_run=%s)", self.dry_run)

        # Step 1: Generate all 6 supplier names in one Claude call
        names = self._generate_supplier_names()

        # Step 2: Build SupplierSpec + ContractSpec for each supplier
        for idx, plan_entry in enumerate(SUPPLIER_DOMAIN_PLAN):
            supplier_spec = SupplierSpec(
                name=names[idx],
                tax_id=plan_entry["tax_id"],
                primary_domain=plan_entry["primary"],
                domains=plan_entry["domains"],
            )

            for contract_idx, domain in enumerate(plan_entry["domains"]):
                # ENG supplier uses a different code set for each contract
                domain_key = (
                    "ENG_CONTRACT2"
                    if (domain == "ENG" and contract_idx == 1)
                    else domain
                )

                # Claude call: contract name + notes (1 per contract)
                details = self._generate_contract_details(
                    supplier_name=supplier_spec.name,
                    domain=domain,
                    contract_idx=contract_idx,
                )

                eff_from = date(2024, 1, 1) if contract_idx == 0 else date(2025, 1, 1)
                eff_to = date(2024, 12, 31) if contract_idx == 0 else None

                rate_cards = self._build_rate_cards(domain_key, contract_idx)
                rc_codes = [rc.taxonomy_code for rc in rate_cards]
                guidelines = self._build_guidelines(domain, contract_idx, rc_codes)

                # Claude call: generate narrative_source for each guideline (~2-3 per contract)
                for g in guidelines:
                    g.narrative_source = self._generate_guideline_narrative(
                        rule_type=g.rule_type,
                        rule_params=g.rule_params,
                        taxonomy_code=g.taxonomy_code,
                        domain=g.domain,
                    )

                contract_spec = ContractSpec(
                    supplier_idx=idx,
                    domain=domain,
                    contract_idx=contract_idx,
                    name=details["name"],
                    effective_from=eff_from,
                    effective_to=eff_to,
                    notes=details["notes"],
                    rate_cards=rate_cards,
                    guidelines=guidelines,
                )
                supplier_spec.contracts.append(contract_spec)
                self.ctx.contracts.append(contract_spec)

            self.ctx.suppliers.append(supplier_spec)

        # Step 3: Write to DB (commit mode only) then print preview
        if not self.dry_run:
            self._write_to_db()

        self._print_preview()

    # ── Claude calls ─────────────────────────────────────────────────────────

    def _generate_supplier_names(self) -> list[str]:
        """1 Claude call → 6 supplier names as a JSON array."""
        plan_info = "\n".join(
            f"  {i+1}. primary={p['primary']}, secondary={p['domains'][1]}, "
            f"id={p['tax_id']}"
            for i, p in enumerate(SUPPLIER_DOMAIN_PLAN)
        )
        text = self._call_claude(
            system=(
                "You are a vendor database administrator for a P&C insurance claims platform. "
                "You know the independent vendor ecosystem well."
            ),
            user=(
                "Generate 6 realistic US insurance vendor company names for these specialties.\n"
                "Return ONLY a JSON array of exactly 6 strings. No explanation.\n\n"
                f"{plan_info}\n\n"
                "Domain reference: IA=Independent Adjusting, ENG=Engineering/Forensic, "
                "CR=Court Reporting, INV=Investigation, DRNE=Drone/Aerial, "
                "INSP=Property Inspection, LA=Ladder Assist, VIRT=Virtual Inspection, "
                "REC=Record Retrieval, APPR=Appraisal, XDOMAIN=Cross-Domain\n\n"
                "Good examples: 'Pinnacle Field Services LLC', 'Summit Engineering Group', "
                "'Capital Court Reporting Inc'. Return only the JSON array."
            ),
            max_tokens=512,
        )
        try:
            result = self._parse_json_response(text)
            if isinstance(result, list) and len(result) == 6:
                return [str(n) for n in result]
        except Exception:
            pass
        # Fallback names
        return [
            "Pinnacle Field Services LLC",
            "Summit Forensic Engineering Group",
            "Capital Court Reporting Inc",
            "AeroView Drone Solutions LLC",
            "RoofReach Ladder Services LLC",
            "MedSource Record Retrieval Inc",
        ]

    def _generate_contract_details(
        self, supplier_name: str, domain: str, contract_idx: int
    ) -> dict:
        """1 Claude call → {"name": "...", "notes": "..."}."""
        era = "legacy/expired 2024" if contract_idx == 0 else "current/active 2025+"
        text = self._call_claude(
            system=(
                "You are a vendor account manager at a P&C insurance carrier "
                "annotating vendor service agreements."
            ),
            user=(
                f"Supplier: {supplier_name}\nService domain: {domain}\nContract: {era}\n\n"
                "Write a realistic contract name and a 1-2 sentence admin note. "
                'Return ONLY valid JSON: {"name": "...", "notes": "..."}'
            ),
            max_tokens=256,
        )
        try:
            result = self._parse_json_response(text)
            if isinstance(result, dict) and "name" in result and "notes" in result:
                return {"name": str(result["name"]), "notes": str(result["notes"])}
        except Exception:
            pass
        year = "2024" if contract_idx == 0 else "2025"
        return {
            "name": f"{supplier_name} — {domain} Services Agreement {year}",
            "notes": f"Standard vendor services agreement for {domain} operations.",
        }

    def _generate_guideline_narrative(
        self,
        rule_type: str,
        rule_params: dict,
        taxonomy_code: Optional[str],
        domain: Optional[str],
    ) -> str:
        """1 Claude call → one sentence of original contract language."""
        scope = taxonomy_code or f"all {domain} services"
        params = ", ".join(f"{k}={v}" for k, v in rule_params.items())
        text = self._call_claude(
            system=(
                "You are a carrier contract administrator drafting vendor agreement language. "
                "Write in formal contractual style."
            ),
            user=(
                f"Write one sentence of original contract language for this billing rule:\n"
                f"  rule_type: {rule_type}\n  applies_to: {scope}\n  params: {params}\n\n"
                "Sound like a real vendor services agreement. Return only the contract sentence."
            ),
            max_tokens=128,
        )
        return text.strip().strip('"')

    # ── Deterministic builders ────────────────────────────────────────────────

    def _build_rate_cards(self, domain_key: str, contract_idx: int) -> list[RateCardSpec]:
        """Build rate cards from DOMAIN_CODES using pick_rate()."""
        codes = DOMAIN_CODES.get(domain_key, [])
        eff_from = date(2024, 1, 1) if contract_idx == 0 else date(2025, 1, 1)
        result = []
        for code in codes:
            rate, rate_type = pick_rate(code, contract_idx)
            # IA all-inclusive: field/cat assignment bundles travel
            is_all_inclusive = code in (
                "IA.FIELD_ASSIGN.PROF_FEE",
                "IA.CAT_ASSIGN.PROF_FEE",
            )
            result.append(
                RateCardSpec(
                    taxonomy_code=code,
                    contracted_rate=rate,
                    rate_type=rate_type,
                    max_units=None,
                    is_all_inclusive=is_all_inclusive,
                    effective_from=eff_from,
                    notes="",
                )
            )
        return result

    def _build_guidelines(
        self, domain: str, contract_idx: int, rc_codes: list[str]
    ) -> list[GuidelineSpec]:
        """Return domain-specific GuidelineSpecs. narrative_source is filled in later."""
        guidelines: list[GuidelineSpec] = []

        def _add(
            taxonomy_code: Optional[str],
            domain_scope: Optional[str],
            rule_type: str,
            rule_params: dict,
            severity: str = "ERROR",
        ) -> None:
            # Only add if the referenced code is in this contract's rate cards
            if taxonomy_code and taxonomy_code not in rc_codes:
                return
            guidelines.append(
                GuidelineSpec(
                    taxonomy_code=taxonomy_code,
                    domain=domain_scope,
                    rule_type=rule_type,
                    rule_params=rule_params,
                    severity=severity,
                    narrative_source="",
                )
            )

        if domain == "IA":
            _add("IA.FIELD_ASSIGN.PROF_FEE", None, "max_units",
                 {"max": 10, "period": "per_invoice"})
            _add("IA.FIELD_ASSIGN.TRAVEL_LODGING", None, "cap_amount",
                 {"max_amount": 195.00})
            _add("IA.CAT_ASSIGN.PROF_FEE", None, "max_units",
                 {"max": 14, "period": "per_invoice"})

        elif domain == "ENG":
            # AOS.L6 is in both ENG contracts
            _add("ENG.AOS.L6", None, "max_units",
                 {"max": 10, "period": "per_invoice"})
            # EWD.L1 is only in contract 0 (legacy service mix)
            if contract_idx == 0:
                _add("ENG.EWD.L1", None, "max_units",
                     {"max": 8, "period": "per_claim"})

        elif domain == "CR":
            _add("CR.DEPO.TRANSCRIPT", None, "max_units",
                 {"max": 300, "period": "per_claim"})
            _add("CR.DEPO.COPY_FEE", None, "bundling_prohibition",
                 {"prohibited_components": ["CR.DEPO.TRANSCRIPT"]})
            _add(None, "CR", "billing_increment",
                 {"min_increment": 0.25, "unit": "hour"}, severity="WARNING")

        elif domain == "INV":
            _add("INV.SURVEILLANCE.PROF_FEE", None, "max_units",
                 {"max": 20, "period": "per_claim"})
            _add("INV.AOE_COE.PROF_FEE", None, "requires_auth",
                 {"required": True, "auth_field": "auth_number"})

        elif domain == "DRNE":
            _add("DRNE.ROOF_SURVEY.FLAT_FEE", None, "max_units",
                 {"max": 1, "period": "per_claim"})
            _add("DRNE.THERMAL.FLAT_FEE", None, "cap_amount",
                 {"max_amount": 350.00})

        elif domain == "INSP":
            _add("INSP.BASIC.FLAT_FEE", None, "max_units",
                 {"max": 1, "period": "per_claim"})
            _add("INSP.TRIP_CHARGE.TRIP_FEE", None, "bundling_prohibition",
                 {"prohibited_components": ["INSP.CANCEL.CANCEL_FEE"]})

        elif domain == "LA":
            _add("LA.LADDER_ACCESS.FLAT_FEE", None, "max_units",
                 {"max": 2, "period": "per_invoice"})
            _add("LA.CANCEL.CANCEL_FEE", None, "max_units",
                 {"max": 1, "period": "per_claim"})

        elif domain == "VIRT":
            _add("VIRT.GUIDED.FLAT_FEE", None, "max_units",
                 {"max": 1, "period": "per_claim"})

        elif domain == "REC":
            _add("REC.MED_RECORDS.RUSH_PREMIUM", None, "cap_amount",
                 {"max_amount": 75.00})
            # 200 pages per_claim is the realistic midrange; complex bodily injury
            # claims routinely run 200-500 pages of records.
            _add("REC.MED_RECORDS.COPY_REPRO", None, "max_units",
                 {"max": 200, "period": "per_claim"})

        elif domain == "APPR":
            _add("APPR.UMPIRE.PROF_FEE", None, "cap_amount",
                 {"max_amount": 3500.00})
            _add("APPR.SITE_VISIT.FLAT_FEE", None, "max_units",
                 {"max": 2, "period": "per_claim"})

        elif domain == "XDOMAIN":
            _add("XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST", None, "cap_amount",
                 {"max_amount": 500.00})

        return guidelines

    # ── DB write ─────────────────────────────────────────────────────────────

    def _write_to_db(self) -> None:
        """Idempotently write suppliers, contracts, rate cards, and guidelines."""
        from app.models.supplier import Carrier

        carrier = self.db.query(Carrier).filter(
            Carrier.id == self.ctx.carrier_id
        ).first()
        if not carrier:
            raise RuntimeError(f"Carrier {self.ctx.carrier_id} not found in DB")

        for supplier_spec in self.ctx.suppliers:
            # Skip-if-exists on tax_id
            existing = (
                self.db.query(Supplier)
                .filter(Supplier.tax_id == supplier_spec.tax_id)
                .first()
            )
            if existing:
                logger.info("Supplier %s already exists — skipping", supplier_spec.tax_id)
                supplier_spec.db_id = existing.id
            else:
                s = Supplier(
                    name=supplier_spec.name,
                    tax_id=supplier_spec.tax_id,
                    is_active=True,
                )
                self.db.add(s)
                self.db.flush()
                supplier_spec.db_id = s.id
                logger.info("Created supplier %s (%s)", supplier_spec.name, supplier_spec.tax_id)

            for contract_spec in supplier_spec.contracts:
                contract_spec.supplier_db_id = supplier_spec.db_id

                # Skip-if-exists on (supplier_id, carrier_id, effective_from) unique constraint
                existing_c = (
                    self.db.query(Contract)
                    .filter(
                        Contract.supplier_id == supplier_spec.db_id,
                        Contract.carrier_id == self.ctx.carrier_id,
                        Contract.effective_from == contract_spec.effective_from,
                    )
                    .first()
                )
                if existing_c:
                    logger.info("Contract '%s' already exists — skipping", contract_spec.name)
                    contract_spec.db_id = existing_c.id
                    continue

                c = Contract(
                    supplier_id=supplier_spec.db_id,
                    carrier_id=self.ctx.carrier_id,
                    name=contract_spec.name,
                    effective_from=contract_spec.effective_from,
                    effective_to=contract_spec.effective_to,
                    geography_scope=GeographyScope.NATIONAL,
                    notes=contract_spec.notes,
                    is_active=contract_spec.effective_to is None,
                )
                self.db.add(c)
                self.db.flush()
                contract_spec.db_id = c.id
                logger.info("Created contract '%s'", contract_spec.name)

                for rc_spec in contract_spec.rate_cards:
                    rc = RateCard(
                        contract_id=c.id,
                        taxonomy_code=rc_spec.taxonomy_code,
                        rate_type=rc_spec.rate_type,
                        contracted_rate=rc_spec.contracted_rate,
                        rate_tiers=None,
                        max_units=rc_spec.max_units,
                        is_all_inclusive=rc_spec.is_all_inclusive,
                        effective_from=rc_spec.effective_from,
                        notes=rc_spec.notes if rc_spec.notes else None,
                    )
                    self.db.add(rc)
                    self.db.flush()
                    rc_spec.db_id = rc.id

                for g_spec in contract_spec.guidelines:
                    g = Guideline(
                        contract_id=c.id,
                        taxonomy_code=g_spec.taxonomy_code,
                        domain=g_spec.domain,
                        rule_type=g_spec.rule_type,
                        rule_params=g_spec.rule_params,
                        severity=g_spec.severity,
                        narrative_source=g_spec.narrative_source,
                        is_active=True,
                    )
                    self.db.add(g)
                    self.db.flush()
                    g_spec.db_id = g.id

    # ── Preview ──────────────────────────────────────────────────────────────

    def _print_preview(self) -> None:
        W = 80
        print("\n" + "=" * W)
        print("  AGENT 1 — CONTRACT FABRICATOR")
        print("=" * W)
        header = (
            f"  {'Supplier':<36} {'Domain':<7} {'Contr':>5} "
            f"{'RC':>5} {'Guide':>6}  Dates"
        )
        print(header)
        print("  " + "-" * 74)
        for s in self.ctx.suppliers:
            rc_total = sum(len(c.rate_cards) for c in s.contracts)
            g_total = sum(len(c.guidelines) for c in s.contracts)
            dates = " | ".join(
                f"{c.effective_from.year}–"
                f"{'now' if c.effective_to is None else c.effective_to.year}"
                for c in s.contracts
            )
            print(
                f"  {s.name[:35]:<36} {s.primary_domain:<7} {len(s.contracts):>5} "
                f"{rc_total:>5} {g_total:>6}  {dates}"
            )
        print("  " + "-" * 74)
        tc = sum(len(s.contracts) for s in self.ctx.suppliers)
        trc = sum(len(c.rate_cards) for c in self.ctx.contracts)
        tg = sum(len(c.guidelines) for c in self.ctx.contracts)
        print(
            f"  TOTALS → {len(self.ctx.suppliers)} suppliers  "
            f"{tc} contracts  {trc} rate cards  {tg} guidelines"
        )
        print("=" * W + "\n")
