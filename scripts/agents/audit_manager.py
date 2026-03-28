"""
AuditManager agent — read-only dataset coverage and quality analysis.
Uses Claude (sonnet) for the audit narrative. Never writes to DB.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from scripts.agents.base import BaseAgent, RunContext

logger = logging.getLogger(__name__)


class AuditManager(BaseAgent):
    DEFAULT_MODEL = "claude-sonnet-4-5"

    def run(self) -> None:
        logger.info("AuditManager starting (dry_run=%s)", self.dry_run)
        stats = self._gather_stats()
        narrative = self._generate_narrative(stats)
        self._print_report(stats, narrative)

    # ── Stats ────────────────────────────────────────────────────────────────

    def _gather_stats(self) -> dict:
        """Derive stats from RunContext (works for both dry-run and commit modes)."""
        domain_stats: dict[str, dict] = defaultdict(
            lambda: {
                "contracts": 0,
                "rate_cards": 0,
                "guidelines": 0,
                "invoices": 0,
                "lines": 0,
                "exceptions": 0,
                "billed": Decimal("0"),
            }
        )

        for contract_spec in self.ctx.contracts:
            d = contract_spec.domain
            domain_stats[d]["contracts"] += 1
            domain_stats[d]["rate_cards"] += len(contract_spec.rate_cards)
            domain_stats[d]["guidelines"] += len(contract_spec.guidelines)

        for inv_spec in self.ctx.invoices:
            contract_spec = self.ctx.contracts[inv_spec.contract_idx_global]
            d = contract_spec.domain
            domain_stats[d]["invoices"] += 1
            for li in inv_spec.line_items:
                domain_stats[d]["lines"] += 1
                domain_stats[d]["billed"] += li.raw_amount
                if li.scenario != "clean":
                    domain_stats[d]["exceptions"] += 1

        supplier_stats: list[dict] = []
        for supplier_spec in self.ctx.suppliers:
            s_idx = self.ctx.suppliers.index(supplier_spec)
            s_invoices = [iv for iv in self.ctx.invoices if iv.supplier_idx == s_idx]
            all_lines = [li for iv in s_invoices for li in iv.line_items]
            n = len(all_lines)
            exc = sum(1 for li in all_lines if li.scenario != "clean")
            total = sum(li.raw_amount for li in all_lines)
            supplier_stats.append(
                {
                    "name": supplier_spec.name,
                    "domain": supplier_spec.primary_domain,
                    "invoices": len(s_invoices),
                    "lines": n,
                    "total_billed": total,
                    "exception_rate": exc / max(n, 1),
                }
            )

        all_domains = {c.domain for c in self.ctx.contracts}
        covered_domains = {
            d for d, s in domain_stats.items() if s["invoices"] > 0
        }

        return {
            "domain_stats": dict(domain_stats),
            "supplier_stats": supplier_stats,
            "all_domains": all_domains,
            "covered_domains": covered_domains,
            "total_invoices": len(self.ctx.invoices),
            "total_lines": sum(len(iv.line_items) for iv in self.ctx.invoices),
            "total_billed": sum(
                li.raw_amount
                for iv in self.ctx.invoices
                for li in iv.line_items
            ),
        }

    # ── Claude call ──────────────────────────────────────────────────────────

    def _generate_narrative(self, stats: dict) -> str:
        """1 Claude call → 500-800 word audit assessment."""
        domains_covered = len(stats["covered_domains"])
        total_domains = len(stats["all_domains"])
        exc_lines = "\n".join(
            f"  {s['name'][:40]}: {s['exception_rate']*100:.0f}% exception rate "
            f"({s['invoices']} invoices, {s['lines']} lines)"
            for s in stats["supplier_stats"]
        )
        domain_lines = "\n".join(
            f"  {d}: {s['invoices']} invoices, {s['lines']} lines, "
            f"${float(s['billed']):,.0f} billed, "
            f"{s['exceptions']/max(s['lines'],1)*100:.0f}% exc rate"
            for d, s in sorted(
                stats["domain_stats"].items(),
                key=lambda x: -float(x[1]["billed"]),
            )
        )
        text = self._call_claude(
            system=(
                "You are a QA/compliance manager reviewing a synthetic dataset "
                "generated for a P&C insurance claims eBilling platform. "
                "Assess dataset quality, coverage gaps, and testing readiness. "
                "Be direct and specific."
            ),
            user=(
                f"Write a 500-800 word audit assessment of this synthetic dataset.\n\n"
                f"Summary:\n"
                f"  {stats['total_invoices']} invoices, {stats['total_lines']} line items\n"
                f"  Total billed: ${float(stats['total_billed']):,.2f}\n"
                f"  Domains covered: {domains_covered}/{total_domains}\n\n"
                f"Domain breakdown:\n{domain_lines}\n\n"
                f"Supplier exception rates:\n{exc_lines}\n\n"
                f"Assess: data realism, coverage adequacy, exception rate distribution, "
                f"scenario variety, and readiness for end-to-end platform testing."
            ),
            max_tokens=1100,
        )
        return text

    # ── Preview ──────────────────────────────────────────────────────────────

    def _print_report(self, stats: dict, narrative: str) -> None:
        W = 80
        print("\n" + "=" * W)
        print("  AGENT 3 — AUDIT MANAGER REPORT")
        print("=" * W)

        print("\n  Domain Coverage (by spend):\n")
        sorted_domains = sorted(
            stats["domain_stats"].keys(),
            key=lambda d: -float(stats["domain_stats"][d]["billed"]),
        )
        max_billed = max(
            (float(s["billed"]) for s in stats["domain_stats"].values()),
            default=1.0,
        )
        for domain in sorted_domains:
            s = stats["domain_stats"][domain]
            bar_width = int(36 * float(s["billed"]) / max_billed) if max_billed > 0 else 0
            bar = "█" * bar_width
            exc_rate = s["exceptions"] / max(s["lines"], 1) * 100
            covered = "✓" if s["invoices"] > 0 else "○"
            print(
                f"  {covered} {domain:<8} {bar:<38} "
                f"${float(s['billed']):>10,.0f}  "
                f"{s['invoices']:>3}inv  "
                f"{exc_rate:>5.1f}%exc"
            )

        print(
            f"\n  TOTALS: {stats['total_invoices']} invoices | "
            f"{stats['total_lines']} lines | "
            f"${float(stats['total_billed']):,.2f}\n"
        )

        print("  " + "-" * (W - 2))
        print("\n  AUDIT NARRATIVE\n")
        _word_wrap(narrative, indent="  ", width=76)
        print("=" * W + "\n")


def _word_wrap(text: str, indent: str = "  ", width: int = 76) -> None:
    """Simple word-wrap printer."""
    for para in text.split("\n"):
        if para.strip():
            words = para.split()
            line = indent
            for word in words:
                if len(line) + len(word) + 1 > width:
                    print(line)
                    line = indent + word
                else:
                    line += (" " if line.strip() else "") + word
            if line.strip():
                print(line)
        else:
            print()
