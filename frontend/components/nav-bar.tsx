"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getUserInfo, isAdmin, isCarrierAdmin, isCarrierRole, isSupplier } from "@/lib/auth";

// ── Nav link definitions ───────────────────────────────────────────────────────
// exact: true means only highlight when path matches exactly (not prefix)

/** Full admin nav — CARRIER_ADMIN and SYSTEM_ADMIN */
const ADMIN_LINKS: { href: string; label: string; exact?: boolean }[] = [
  { href: "/admin",           label: "Dashboard",     exact: true },
  { href: "/admin/invoices",  label: "Invoice Queue" },
  { href: "/admin/suppliers", label: "Suppliers" },
  { href: "/admin/contracts", label: "Contracts" },
  { href: "/admin/mappings",  label: "Classification Review" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/team",      label: "Team" },
];

/** Focused auditor nav — CARRIER_REVIEWER only (no management pages) */
const REVIEWER_LINKS: { href: string; label: string; exact?: boolean }[] = [
  { href: "/admin",          label: "Dashboard",     exact: true },
  { href: "/admin/invoices", label: "Invoice Queue" },
  { href: "/admin/mappings", label: "Classification Review" },
];

// ── NavLink helper ─────────────────────────────────────────────────────────────

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded px-3 py-1.5 text-sm transition-colors ${
        active
          ? "bg-blue-50 text-blue-700 font-semibold"
          : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
      }`}
    >
      {children}
    </Link>
  );
}

// ── NavBar ─────────────────────────────────────────────────────────────────────

export function NavBar() {
  const router = useRouter();
  const pathname = usePathname();
  const user = getUserInfo();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  /** True when this link should be highlighted as active. */
  function isActive(href: string, exact?: boolean): boolean {
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  }

  // Pick which link set to render for carrier/admin roles
  const adminLinks = isCarrierRole() && !isCarrierAdmin()
    ? REVIEWER_LINKS   // CARRIER_REVIEWER — focused auditor nav
    : ADMIN_LINKS;     // CARRIER_ADMIN + SYSTEM_ADMIN — full nav

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="text-lg font-bold text-blue-700">Claims eBilling</span>
          {user?.carrier_name && (
            <span className="text-sm text-gray-400">· {user.carrier_name}</span>
          )}
          {user?.supplier_name && (
            <span className="text-sm text-gray-400">· {user.supplier_name}</span>
          )}
        </Link>

        {/* Links */}
        <div className="flex items-center gap-1">
          {/* Supplier nav */}
          {isSupplier() && (
            <>
              <NavLink href="/supplier" active={isActive("/supplier", true)}>
                Dashboard
              </NavLink>
              <NavLink href="/supplier/invoices" active={isActive("/supplier/invoices")}>
                My Invoices
              </NavLink>
              <NavLink href="/supplier/invoices/new" active={isActive("/supplier/invoices/new")}>
                + New Invoice
              </NavLink>
            </>
          )}

          {/* Carrier / admin nav (role-appropriate link set) */}
          {isAdmin() &&
            adminLinks.map((link) => (
              <NavLink
                key={link.href}
                href={link.href}
                active={isActive(link.href, link.exact)}
              >
                {link.label}
              </NavLink>
            ))}

          <div className="ml-3 flex items-center gap-3 border-l pl-4">
            {/* Role pill */}
            {user?.role && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                user.role === "CARRIER_REVIEWER"
                  ? "bg-blue-50 text-blue-600"
                  : user.role === "CARRIER_ADMIN"
                  ? "bg-violet-50 text-violet-600"
                  : user.role === "SYSTEM_ADMIN"
                  ? "bg-red-50 text-red-600"
                  : "bg-gray-100 text-gray-500"
              }`}>
                {user.role === "CARRIER_REVIEWER" ? "Auditor"
                  : user.role === "CARRIER_ADMIN" ? "Admin"
                  : user.role === "SYSTEM_ADMIN" ? "System"
                  : "Supplier"}
              </span>
            )}
            <span className="text-xs text-gray-400">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-200 transition-colors"
            >
              Log out
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
