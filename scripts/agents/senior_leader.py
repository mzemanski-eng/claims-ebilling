"""
SeniorLeader agent — executive analytics insights.
Uses Claude (sonnet) for strategic narrative. Never writes to DB.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from scripts.agents.base import BaseAgent, RunContext

logger = logging.getLogger(__name__)

# Exception rate → letter grade thresholds
_GRADE_THRESHOLDS = [
    (0.05, "A"),
    (0.12, "B"),
    (0.20, "C"),
    (0.30, "D"),
]


def _grade(exception_rate: float) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if exception_rate <= threshold:
            return letter
    return "F"


class SeniorLeader(BaseAgent):
    DEFAULT_MODEL = "claude-sonnet-4-5"

    def run(self) -> None:
        logger.info("SeniorLeader starting (dry_run=%s)", self.dry_run)
        stats = self._gather_stats()
        narrative = self._generate_narrative(stats)
        self._print_report(stats, narrative)

    # ── Stats ────────────────────────────────────────────────────────────────

    def _gather_stats(self) -> dict:
        """Derive stats from RunContext (works for both dry-run and commit modes)."""
        domain_spend: dict[str, Decimal] = defaultdict(Decimal)
        domain_lines: dict[str, int] = defaultdict(int)
        domain_exc: dict[str, int] = defaultdict(int)

        for inv_spec in self.ctx.invoices:
            contract_spec = self.ctx.contracts[inv_spec.contract_idx_global]
            domain = contract_spec.domain
            for li in inv_spec.line_items:
                domain_spend[domain] += li.raw_amount
                domain_lines[domain] += 1
                if li.scenario != "clean":
                    domain_exc[domain] += 1

        supplier_scores: list[dict] = []
        for supplier_spec in self.ctx.suppliers:
            s_idx = self.ctx.suppliers.index(supplier_spec)
            s_invoices = [iv for iv in self.ctx.invoices if iv.supplier_idx == s_idx]
            all_lines = [li for iv in s_invoices for li in iv.line_items]
            n = len(all_lines)
            exc = sum(1 for li in all_lines if li.scenario != "clean")
            total = sum(li.raw_amount for li in all_lines)
            exc_rate = exc / max(n, 1)
            supplier_scores.append(
                {
                    "name": supplier_spec.name,
                    "domain": supplier_spec.primary_domain,
                    "invoices": len(s_invoices),
                    "lines": n,
                    "total_billed": total,
                    "exception_rate": exc_rate,
                    "grade": _grade(exc_rate),
                }
            )

        domain_ranking = sorted(
            domain_spend.keys(), key=lambda d: -float(domain_spend[d])
        )

        return {
            "domain_spend": domain_spend,
            "domain_lines": domain_lines,
            "domain_exc": domain_exc,
            "domain_ranking": domain_ranking,
            "supplier_scores": supplier_scores,
            "total_invoices": len(self.ctx.invoices),
            "total_billed": sum(domain_spend.values()),
        }

    # ── Claude call ──────────────────────────────────────────────────────────

    def _generate_narrative(self, stats: dict) -> str:
        """1 Claude call → 600-900 word executive insights."""
        top_domains = stats["domain_ranking"][:6]
        spend_lines = "\n".join(
            f"  {d}: ${float(stats['domain_spend'][d]):,.2f} "
            f"({stats['domain_exc'][d]/max(stats['domain_lines'][d],1)*100:.0f}% exc rate)"
            for d in top_domains
        )
        scorecard_lines = "\n".join(
            f"  {s['name'][:38]}: Grade {s['grade']} — "
            f"{s['exception_rate']*100:.1f}% exc, ${float(s['total_billed']):,.2f} billed"
            for s in sorted(stats["supplier_scores"], key=lambda x: x["grade"])
        )
        text = self._call_claude(
            system=(
                "You are the VP of Claims Operations at a P&C insurance carrier. "
                "You are reviewing analytics for your vendor expense management platform. "
                "Be strategic, direct, and focused on cost control and compliance. "
                "Write as if presenting to the CFO and Chief Claims Officer."
            ),
            user=(
                f"Write a 600-900 word executive insights report for this vendor spend data.\n\n"
                f"Overall: {stats['total_invoices']} invoices, "
                f"${float(stats['total_billed']):,.2f} total billed\n\n"
                f"Spend by domain (ranked):\n{spend_lines}\n\n"
                f"Supplier compliance scorecard:\n{scorecard_lines}\n\n"
                f"Cover: spend concentration risks, vendor compliance concerns, "
                f"contract optimization opportunities, and 3 strategic recommendations. "
                f"Be concise and actionable."
            ),
            max_tokens=1200,
        )
        return text

    # ── Preview ──────────────────────────────────────────────────────────────

    def _print_report(self, stats: dict, narrative: str) -> None:
        W = 80
        print("\n" + "=" * W)
        print("  AGENT 4 — SENIOR LEADER REPORT")
        print("=" * W)

        # Domain spend ranking
        print("\n  Vendor Spend by Domain (ranked):\n")
        total_spend = float(stats["total_billed"]) or 1.0
        for domain in stats["domain_ranking"]:
            spend = float(stats["domain_spend"][domain])
            pct = spend / total_spend * 100
            lines = stats["domain_lines"].get(domain, 0)
            exc = stats["domain_exc"].get(domain, 0)
            exc_rate = exc / max(lines, 1) * 100
            bar = "▓" * int(28 * pct / 100)
            print(
                f"  {domain:<8} {bar:<30} {pct:>5.1f}%  "
                f"${spend:>10,.0f}  exc: {exc_rate:.1f}%"
            )

        # Supplier scorecard
        print("\n  Supplier Compliance Scorecard:\n")
        hdr = f"  {'Supplier':<36} {'Domain':<8} {'Grade':>5} {'Exc%':>6} {'Billed':>12}"
        print(hdr)
        print("  " + "-" * 70)
        for s in sorted(stats["supplier_scores"], key=lambda x: x["grade"]):
            g = s["grade"]
            # ANSI color: A/B=green, C=yellow, D/F=red
            if g in ("A", "B"):
                colored = f"\033[92m{g}\033[0m"
            elif g == "C":
                colored = f"\033[93m{g}\033[0m"
            else:
                colored = f"\033[91m{g}\033[0m"
            print(
                f"  {s['name'][:35]:<36} {s['domain']:<8} {g:>5} "
                f"{s['exception_rate']*100:>5.1f}%  "
                f"${float(s['total_billed']):>10,.0f}"
            )

        print(
            f"\n  TOTAL: ${float(stats['total_billed']):,.2f} across "
            f"{stats['total_invoices']} invoices\n"
        )

        print("  " + "-" * (W - 2))
        print("\n  EXECUTIVE INSIGHTS\n")
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
